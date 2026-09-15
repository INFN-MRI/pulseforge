"""The built-in Cartesian FFT, recording the interval it ran over where asked.

A config carrying a ``trace`` directory makes the reconstruction hold its slot
long enough for a second series to overlap it, and write
``<trace>/<pid>.json`` with the interval it held it for.
"""

import json
import os
import time
from pathlib import Path

from pulserver.recon.handlers.simplefft import SimpleFftRecon

HOLD_SECONDS = 0.5


class TracedFft(SimpleFftRecon):
    def startup(self, context):
        super().startup(context)
        self.trace = _trace(context.config)
        self.started = time.time()
        if self.trace is not None:
            time.sleep(HOLD_SECONDS)

    def recon(self, branch, context):
        result = super().recon(branch, context)
        if self.trace is not None:
            path = self.trace / f"{os.getpid()}.json"
            path.write_text(json.dumps({"start": self.started, "end": time.time()}))
        return result


PLUGIN = TracedFft()


def _trace(config):
    parameters = config.get("parameters") if isinstance(config, dict) else None
    directory = parameters.get("trace") if isinstance(parameters, dict) else None
    return None if directory is None else Path(directory)
