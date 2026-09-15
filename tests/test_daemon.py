import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from pulserver.host import SessionKey
from pulserver.host.client import HostClient, HostError
from pulserver.protocol import TEPreset

PLUGINS = Path(__file__).parent / "plugins"
FIXTURES = Path(__file__).parent / "fixtures" / "sequences"
# The limits the IR fixtures convert under.
FIXTURE_LIMITS = {
    "max_grad": 40.0,
    "grad_unit": "mT/m",
    "max_slew": 170.0,
    "slew_unit": "T/m/s",
    "B0": 3.0,
    "rf_raster_time": 1e-6,
    "grad_raster_time": 1e-5,
    "adc_raster_time": 1e-7,
    "block_duration_raster": 1e-5,
}
GE_IR = {"ir_vendor": 2, "ir_label_column_map": "8 0 6", "ir_cache_ext": ".pge"}
LIMITS = {
    "max_grad": 40.0,
    "grad_unit": "mT/m",
    "max_slew": 150.0,
    "slew_unit": "T/m/s",
}


class Daemon:
    def __init__(self, base: Path) -> None:
        self.base = base
        self._socket_dir = Path(tempfile.mkdtemp(prefix="ps"))
        self.socket = self._socket_dir / "s"
        self._process = None

    def start(self) -> None:
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pulserver.host",
                "--base",
                str(self.base),
                "--socket",
                str(self.socket),
                "--plugins",
                str(PLUGINS),
                "--workers",
                "1",
            ]
        )
        deadline = time.monotonic() + 30
        while not self.socket.exists():
            if self._process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("the host daemon did not start")
            time.sleep(0.05)

    def stop(self) -> None:
        self._process.terminate()
        self._process.wait(timeout=30)
        self.socket.unlink(missing_ok=True)

    def client(self, pid: int) -> HostClient:
        return HostClient(self.socket, SessionKey(pid=pid, day=20711))

    def cleanup(self) -> None:
        if self._process.poll() is None:
            self.stop()
        shutil.rmtree(self._socket_dir, ignore_errors=True)


@pytest.fixture
def daemon(tmp_path):
    running = Daemon(tmp_path / "base")
    running.start()
    yield running
    running.cleanup()


def _session_dir(daemon, client):
    return daemon.base / "bucket" / str(client.session)


def test_repeated_predownloads_generate_one_revision(daemon):
    client = daemon.client(pid=101)
    client.open("tiny", LIMITS)
    assert client.list_protocol()["TE"].value == 8000
    assert client.validate({"TE": TEPreset.MINIMUM}).values["TE"] == 2500
    revisions = [client.generate({"TE": TEPreset.MINIMUM}) for _ in range(3)]
    assert revisions == [1, 1, 1]
    assert client.generate({"TE": 10000}) == 2
    directory = _session_dir(daemon, client)
    assert (directory / "current").readlink().as_posix() == "rev/2"
    assert sorted(p.name for p in (directory / "rev" / "1").iterdir()) == [
        "meta.json",
        "resolved.protocol",
        "sequence.pseg",
        "sequence.seq",
    ]
    assert "TE: 2500" in (directory / "rev" / "1" / "resolved.protocol").read_text()


def test_two_sessions_interleave_without_sharing_state(daemon):
    first, second = daemon.client(pid=201), daemon.client(pid=202)
    first.open("tiny", LIMITS)
    second.open("tiny", LIMITS)
    assert first.generate({"TE": 8000}) == 1
    assert second.validate({"TE": 12000}).values["TE"] == 12000
    assert second.generate({"TE": 12000}) == 1
    assert first.generate({"TE": 8000}) == 1
    first_protocol = _session_dir(daemon, first) / "current" / "resolved.protocol"
    second_protocol = _session_dir(daemon, second) / "current" / "resolved.protocol"
    assert "TE: 8000" in first_protocol.read_text()
    assert "TE: 12000" in second_protocol.read_text()


def test_a_crashing_plugin_fails_only_its_command(daemon):
    crashing, healthy = daemon.client(pid=301), daemon.client(pid=302)
    crashing.open("crash", LIMITS)
    healthy.open("tiny", LIMITS)
    with pytest.raises(HostError, match="worker exited"):
        crashing.validate({"TE": 8000})
    assert healthy.validate({"TE": 8000}).valid


def test_a_restarted_daemon_serves_an_open_session(daemon):
    client = daemon.client(pid=401)
    client.open("tiny", LIMITS)
    assert client.generate({"TE": 9000}) == 1
    daemon.stop()
    daemon.start()
    assert client.validate({"TE": 9000}).valid
    assert client.generate({"TE": 9000}) == 1


def test_an_invalid_protocol_generates_nothing(daemon):
    client = daemon.client(pid=501)
    client.open("tiny", LIMITS)
    with pytest.raises(HostError, match="shorter than"):
        client.generate({"TE": 1000})
    assert not (_session_dir(daemon, client) / "rev").exists()


def test_a_command_for_a_session_never_opened_is_an_error(daemon):
    with pytest.raises(HostError, match="not open"):
        daemon.client(pid=601).list_protocol()


def test_a_generated_revision_carries_its_cache(daemon):
    client = daemon.client(pid=701)
    client.open("tiny", {**LIMITS, **GE_IR})
    assert client.generate({"TE": 8000}) == 1
    revision = _session_dir(daemon, client) / "rev" / "1"
    assert sorted(p.name for p in revision.iterdir()) == [
        "meta.json",
        "resolved.protocol",
        "sequence.pge",
        "sequence.seq",
    ]
    vendor = struct.unpack("<6i", (revision / "sequence.pge").read_bytes()[:24])[4]
    assert vendor == 2


def test_an_imported_chain_is_staged_and_converted(daemon):
    client = daemon.client(pid=801)
    client.open(None, FIXTURE_LIMITS)
    assert client.import_sequence(FIXTURES / "dedup_gre_pair.seq") == 1
    current = _session_dir(daemon, client) / "current"
    assert sorted(p.name for p in current.iterdir()) == [
        "dedup_gre_pair.seq",
        "dedup_gre_pair_b.seq",
        "meta.json",
        "sequence.pseg",
        "sequence.seq",
    ]
    assert (current / "sequence.seq").readlink().as_posix() == "dedup_gre_pair.seq"


def test_importing_the_same_file_reuses_its_revision(daemon):
    client = daemon.client(pid=802)
    client.open(None, FIXTURE_LIMITS)
    first = client.import_sequence(FIXTURES / "dedup_gre_pair.seq")
    assert client.import_sequence(FIXTURES / "dedup_gre_pair.seq") == first == 1


def test_a_session_without_a_plugin_refuses_design_commands(daemon):
    client = daemon.client(pid=803)
    client.open(None, FIXTURE_LIMITS)
    with pytest.raises(HostError, match="no plugin"):
        client.list_protocol()
