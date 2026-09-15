"""A minimal scanner sequence: one delay per repetition, with a shortest TE."""

import pypulseqpp as pp
from pypulseqpp import sequences

from pulserver.design import FloatParam, IntParam, ScannerSequence
from pulserver.protocol import TEPreset


class TinyApp(sequences.SequenceApp):
    MAX_GRAD = 40.0
    MAX_SLEW = 150.0
    SHORTEST_TE = 2.5e-3

    def init_sequence(self, te: float | None = 8e-3, n_repetitions: int = 4) -> None:
        if te is not None and te < self.SHORTEST_TE:
            raise ValueError(
                f"the requested TE of {te * 1e3:.3f} ms is shorter than "
                f"{self.SHORTEST_TE * 1e3:.3f} ms"
            )
        self.te = self.SHORTEST_TE if te is None else te
        self.n_repetitions = n_repetitions

    def loop(self) -> None:
        for _ in range(self.n_repetitions):
            self.kernel()

    def kernel(self) -> None:
        self.seq.add_block(pp.make_delay(self.te))


class Tiny(ScannerSequence):
    app = TinyApp
    ui = {
        "TE": FloatParam(
            "te",
            unit="ms",
            scale=1e-3,
            range_min=1.0,
            range_max=80.0,
            range_incr=0.1,
            presets={TEPreset.MINIMUM: None},
        ),
        "nx": IntParam("n_repetitions", range_min=1, range_max=64),
    }
