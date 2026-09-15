"""The built-in Cartesian FFT, held and timed where the client's config asks.

``gate`` names a file the reconstruction waits for before it starts, so a test
decides when a slot frees; it touches ``<gate>.waiting`` once it is holding.
``trace`` names a directory it writes ``<pid>.json`` into, with the interval it
held its slot for.
"""

import json
import os
import time
from pathlib import Path

from pulserver.recon.handlers.simplefft import SimpleFftRecon

HOLD_SECONDS = 0.5
GATE_TIMEOUT = 60.0


class TracedFft(SimpleFftRecon):
    def startup(self, context):
        super().startup(context)
        self.trace = _path(context.config, "trace")
        self.gate = _path(context.config, "gate")
        self.started = time.time()
        if self.gate is not None:
            _wait_for(self.gate)
        elif self.trace is not None:
            time.sleep(HOLD_SECONDS)

    def recon(self, branch, context):
        result = super().recon(branch, context)
        if self.trace is not None:
            path = self.trace / f"{os.getpid()}.json"
            path.write_text(json.dumps({"start": self.started, "end": time.time()}))
        return result


PLUGIN = TracedFft()


def _path(config, name):
    parameters = config.get("parameters") if isinstance(config, dict) else None
    value = parameters.get(name) if isinstance(parameters, dict) else None
    return None if value is None else Path(value)


def _wait_for(gate):
    gate.with_name(gate.name + ".waiting").touch()
    deadline = time.monotonic() + GATE_TIMEOUT
    while not gate.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
