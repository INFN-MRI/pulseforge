"""A plugin whose design kills the worker process."""

import os

from pypulseqpp import sequences

from pulserver.design import FloatParam, ScannerSequence


class CrashApp(sequences.SequenceApp):
    MAX_GRAD = 40.0
    MAX_SLEW = 150.0

    def init_sequence(self, te: float = 8e-3) -> None:
        os._exit(1)

    def loop(self) -> None:
        pass

    def kernel(self) -> None:
        pass


class Crash(ScannerSequence):
    app = CrashApp
    ui = {"TE": FloatParam("te", unit="ms", scale=1e-3, range_min=1.0, range_max=80.0)}
