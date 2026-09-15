import shutil
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
    assert client.list_protocol()["TE"].value == 8.0
    assert client.validate({"TE": TEPreset.MINIMUM}).values["TE"] == 2.5
    revisions = [client.generate({"TE": TEPreset.MINIMUM}) for _ in range(3)]
    assert revisions == [1, 1, 1]
    assert client.generate({"TE": 10.0}) == 2
    directory = _session_dir(daemon, client)
    assert (directory / "current").readlink().as_posix() == "rev/2"
    assert sorted(p.name for p in (directory / "rev" / "1").iterdir()) == [
        "meta.json",
        "resolved.protocol",
        "sequence.seq",
    ]
    assert "TE: 2.5" in (directory / "rev" / "1" / "resolved.protocol").read_text()


def test_two_sessions_interleave_without_sharing_state(daemon):
    first, second = daemon.client(pid=201), daemon.client(pid=202)
    first.open("tiny", LIMITS)
    second.open("tiny", LIMITS)
    assert first.generate({"TE": 8.0}) == 1
    assert second.validate({"TE": 12.0}).values["TE"] == 12.0
    assert second.generate({"TE": 12.0}) == 1
    assert first.generate({"TE": 8.0}) == 1
    first_protocol = _session_dir(daemon, first) / "current" / "resolved.protocol"
    second_protocol = _session_dir(daemon, second) / "current" / "resolved.protocol"
    assert "TE: 8.0" in first_protocol.read_text()
    assert "TE: 12.0" in second_protocol.read_text()


def test_a_crashing_plugin_fails_only_its_command(daemon):
    crashing, healthy = daemon.client(pid=301), daemon.client(pid=302)
    crashing.open("crash", LIMITS)
    healthy.open("tiny", LIMITS)
    with pytest.raises(HostError, match="worker exited"):
        crashing.validate({"TE": 8.0})
    assert healthy.validate({"TE": 8.0}).valid


def test_a_restarted_daemon_serves_an_open_session(daemon):
    client = daemon.client(pid=401)
    client.open("tiny", LIMITS)
    assert client.generate({"TE": 9.0}) == 1
    daemon.stop()
    daemon.start()
    assert client.validate({"TE": 9.0}).valid
    assert client.generate({"TE": 9.0}) == 1


def test_an_invalid_protocol_generates_nothing(daemon):
    client = daemon.client(pid=501)
    client.open("tiny", LIMITS)
    with pytest.raises(HostError, match="shorter than"):
        client.generate({"TE": 1.0})
    assert not (_session_dir(daemon, client) / "rev").exists()


def test_a_command_for_a_session_never_opened_is_an_error(daemon):
    with pytest.raises(HostError, match="not open"):
        daemon.client(pid=601).list_protocol()
