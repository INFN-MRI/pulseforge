"""pypulseqpp's 2D gradient echo bound to the scanner UI."""

from pypulseqpp.sequences.sequence.gre2D_sequence import Gre2DApp

from pulserver.design import FloatParam, IntParam, ScannerSequence
from pulserver.protocol import TEPreset, TRPreset


class Gre2D(ScannerSequence):
    app = Gre2DApp
    ui = {
        "TE": FloatParam(
            "te",
            unit="ms",
            scale=1e-3,
            range_min=1.0,
            range_max=80.0,
            range_incr=0.01,
            options=(5.0, 8.0),
            presets={TEPreset.MINIMUM: None},
        ),
        "TR": FloatParam(
            "tr",
            unit="ms",
            scale=1e-3,
            range_min=1.0,
            range_max=5000.0,
            presets={TRPreset.MINIMUM: None},
        ),
        "bandwidth": FloatParam(
            "readout_bandwidth_hz", unit="Hz", range_min=1e3, range_max=1e6
        ),
        "fov": FloatParam(
            "fov", unit="mm", scale=1e-3, range_min=50.0, range_max=500.0
        ),
        "nx": IntParam("n_x", range_min=32, range_max=512, range_incr=2),
        "ny": IntParam("n_y", range_min=32, range_max=512, range_incr=2),
    }

    def resolved(self, app):
        return {
            "te": app.ro.echo_time,
            "tr": app.repetition_time,
            "readout_bandwidth_hz": app.ro.bandwidth_hz,
        }
