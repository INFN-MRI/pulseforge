"""The reconstruction proxy: a series streamed in, images streamed back."""

import json
import socket
import threading
from dataclasses import dataclass
from pathlib import Path

import ismrmrd
import ismrmrd.xsd
import numpy as np
import pytest
from _host import DAY, LIMITS, Daemon

from pulserver.recon._runtime.connection import Connection
from pulserver.vre import ReconProxy, SequenceTable

RECON_PLUGINS = Path(__file__).parent / "recon_plugins"
MATRIX = {"nx": 32, "ny": 16, "TE": 5000}
CHANNELS = 2
# Long enough that a stall fails the run instead of hanging it.
DEADLINE = 180.0

HEADER = """<?xml version="1.0"?>
<ismrmrdHeader xmlns="http://www.ismrm.org/ISMRMRD">
  <acquisitionSystemInformation><receiverChannels>{channels}</receiverChannels></acquisitionSystemInformation>
  <experimentalConditions><H1resonanceFrequency_Hz>63500000</H1resonanceFrequency_Hz></experimentalConditions>
  <encoding>
    <encodedSpace><matrixSize><x>1</x><y>1</y><z>1</z></matrixSize><fieldOfView_mm><x>1</x><y>1</y><z>1</z></fieldOfView_mm></encodedSpace>
    <reconSpace><matrixSize><x>1</x><y>1</y><z>1</z></matrixSize><fieldOfView_mm><x>1</x><y>1</y><z>1</z></fieldOfView_mm></reconSpace>
    <encodingLimits/>
    <trajectory>cartesian</trajectory>
  </encoding>
  <userParameters>
    <userParameterLong><name>pulserver_revision</name><value>{revision}</value></userParameterLong>
    <userParameterString><name>pulserver_session</name><value>{session}</value></userParameterString>
  </userParameters>
</ismrmrdHeader>
"""


@dataclass(frozen=True)
class Series:
    """A generated revision and the readouts a client of it plays."""

    session: str
    revision: int
    table: SequenceTable


@pytest.fixture(scope="module")
def bucket(tmp_path_factory):
    """A bucket holding one revision bound to a reconstruction and one unbound."""
    base = tmp_path_factory.mktemp("vre") / "base"
    daemon = Daemon(base)
    daemon.start()
    try:
        series = {}
        for pid, plugin, name in ((901, "gre2d", "bound"), (902, "gre2d_raw", "raw")):
            client = daemon.client(pid=pid)
            client.open(plugin, LIMITS)
            revision = client.generate(MATRIX)
            session = f"{pid}-{DAY}"
            table = SequenceTable.read(
                base / "bucket" / session / "rev" / str(revision) / "sequence.seq"
            )
            series[name] = Series(session, revision, table)
    finally:
        daemon.cleanup()
    return base, series


@pytest.fixture
def start_proxy(bucket):
    """Start proxies serving the bucket; every one is closed when the test ends."""
    base, _ = bucket
    running = []

    def start(**options):
        proxy = ReconProxy(base, RECON_PLUGINS, **options)
        proxy.bind(0)
        thread = threading.Thread(target=proxy.serve, daemon=True)
        thread.start()
        running.append((proxy, thread))
        return proxy

    yield start
    for proxy, thread in running:
        proxy.close()
        thread.join(timeout=DEADLINE)


def stream(port, series, *, config=""):
    """Play one series' readouts as the scanner client does; return what came back."""
    stream = socket.create_connection(("127.0.0.1", port), timeout=DEADLINE)
    connection = Connection(stream)
    stream.settimeout(DEADLINE)
    connection.send_config(config)
    connection.send_header(
        HEADER.format(
            channels=CHANNELS, session=series.session, revision=series.revision
        )
    )
    for index in range(len(series.table)):
        samples = int(series.table.num_samples[index])
        connection.send(
            ismrmrd.Acquisition.from_array(
                np.ones((CHANNELS, samples), dtype=np.complex64)
            )
        )
    connection.send_close()
    received = list(connection)
    connection.shutdown_close()
    return received


def images(received):
    return [item for item in received if isinstance(item, ismrmrd.Image)]


def closed(received):
    return any(
        isinstance(item, ismrmrd.Acquisition)
        and item.isFlagSet(ismrmrd.ACQ_LAST_IN_MEASUREMENT)
        for item in received
    )


def test_a_series_returns_images_then_closes(start_proxy, bucket):
    _, series = bucket
    proxy = start_proxy(slots=1)
    received = stream(proxy.port, series["bound"])
    assert closed(received)
    assert [np.squeeze(image.data).shape for image in images(received)] == [
        (MATRIX["ny"], MATRIX["nx"])
    ]


def test_a_second_series_waits_for_a_slot_and_still_returns_images(
    start_proxy, bucket, tmp_path
):
    _, series = bucket
    proxy = start_proxy(slots=1)
    trace = tmp_path / "trace"
    trace.mkdir()
    config = json.dumps({"parameters": {"config": "gre2d", "trace": str(trace)}})
    received = {}

    def play(name):
        received[name] = stream(proxy.port, series["bound"], config=config)

    threads = [threading.Thread(target=play, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=DEADLINE)

    assert set(received) == {"a", "b"}
    assert all(len(images(items)) == 1 for items in received.values())
    first, second = sorted(
        (json.loads(path.read_text()) for path in trace.glob("*.json")),
        key=lambda run: run["start"],
    )
    assert first["end"] <= second["start"]


def test_a_crashing_plugin_closes_its_series_and_frees_the_slot(start_proxy, bucket):
    _, series = bucket
    proxy = start_proxy(slots=1)
    crashed = stream(proxy.port, series["raw"], config="crash")
    assert closed(crashed)
    assert not images(crashed)
    assert any(isinstance(item, str) and "always fails" in item for item in crashed)
    assert len(images(stream(proxy.port, series["bound"]))) == 1


def test_the_spare_worker_is_replaced_after_each_series(start_proxy, bucket):
    _, series = bucket
    proxy = start_proxy(slots=1, spares=1)
    warm = proxy.workers.spare_pids()
    assert len(warm) == 1
    assert len(images(stream(proxy.port, series["bound"]))) == 1
    replaced = proxy.workers.spare_pids()
    assert len(replaced) == 1
    assert replaced != warm
    assert len(images(stream(proxy.port, series["bound"]))) == 1
    assert proxy.workers.spare_pids() not in (warm, replaced)
