"""Small synthetic sequences for tests that need one readout geometry exactly."""

import pypulseqpp as pp

SAMPLES = 32
DELTA_K = 5.0  # 1/m: a 0.2 m field of view


def add_readout(seq, *labels, rotation=None, moving=True):
    """Append a symmetric readout along x, rewound on both sides so k returns to zero."""
    system = pp.Opts()
    gx = pp.make_trapezoid(
        "x", flat_area=SAMPLES * DELTA_K, flat_time=3.2e-3, system=system
    )
    adc = pp.make_adc(
        num_samples=SAMPLES, duration=3.2e-3, delay=gx.rise_time, system=system
    )
    if not moving:
        seq.add_block(adc, *labels)
        return
    rewinder = pp.make_trapezoid("x", area=-gx.area / 2, duration=1e-3, system=system)
    extra = () if rotation is None else (rotation,)
    seq.add_block(rewinder, *extra)
    seq.add_block(gx, adc, *labels, *extra)
    seq.add_block(rewinder, *extra)
