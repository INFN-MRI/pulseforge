"""Block extensions resolved through pypulseqpp against the ones the C parser resolves."""

from pathlib import Path

import numpy as np
import pypulseqpp as pp
import pytest

from pulserver import _ext
from pulserver.ir._source import COUNTER_LABELS, FLAG_LABELS, block_extensions

FIXTURES = Path(__file__).parent / "fixtures" / "sequences"
SPECIFICATIONS = ("rotation", "rf_shim", "trigger", "soft_delay")


def fixtures():
    return sorted(p.name for p in FIXTURES.glob("*.seq"))


def compare(path):
    sequence = pp.Sequence()
    sequence.read(path)
    ours = block_extensions(sequence)
    theirs = _ext.parse_block_extensions(str(path))
    for name in COUNTER_LABELS:
        np.testing.assert_array_equal(
            ours.labelset[name], theirs["labelset"][name], err_msg=f"LABELSET {name}"
        )
        np.testing.assert_array_equal(
            ours.labelinc[name], theirs["labelinc"][name], err_msg=f"LABELINC {name}"
        )
    for name in FLAG_LABELS:
        np.testing.assert_array_equal(
            ours.flags[name], theirs["flags"][name], err_msg=f"flag {name}"
        )
    for name in SPECIFICATIONS:
        np.testing.assert_array_equal(
            getattr(ours, name), theirs["indices"][name], err_msg=name
        )


@pytest.fixture
def extended(tmp_path):
    """A sequence playing every extension a block can carry."""
    sequence = pp.Sequence(pp.Opts())
    quarter_turn = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    shim = pp.make_rf_shim([(1.0, 0.0), (0.5, np.pi / 2)])
    sequence.add_block(pp.make_delay(2e-3), pp.make_trigger("physio1", duration=1e-3))
    sequence.add_block(pp.make_delay(1e-3), pp.make_rotation(quarter_turn))
    sequence.add_block(pp.make_delay(1e-3), pp.make_rotation(np.eye(3)))
    sequence.add_block(pp.make_delay(1e-3), pp.make_trigger("physio1", duration=2e-3))
    sequence.add_block(
        pp.make_delay(1e-3), pp.make_label(label="TRID", type="SET", value=5)
    )
    sequence.add_block(
        pp.make_delay(1e-3),
        pp.make_label(label="LIN", type="INC", value=1),
        pp.make_label(label="NAV", type="SET", value=1),
    )
    sequence.add_block(
        pp.make_delay(1e-3), pp.make_sinc_pulse(flip_angle=0.1, duration=1e-3), shim
    )
    sequence.add_block(
        pp.make_delay(2e-3), pp.make_soft_delay("fill", offset=0.0, factor=1.0)
    )
    path = tmp_path / "extended.seq"
    sequence.write(path)
    return path


@pytest.mark.parametrize("name", fixtures())
def test_every_label_a_fixture_sets_is_the_one_the_parser_resolves(name):
    compare(FIXTURES / name)


def test_every_specification_a_block_points_at_is_the_one_the_parser_resolves(extended):
    compare(extended)


def test_the_extended_sequence_plays_one_of_every_extension(extended):
    sequence = pp.Sequence()
    sequence.read(extended)
    resolved = block_extensions(sequence)
    for name in SPECIFICATIONS:
        assert (getattr(resolved, name) >= 0).any(), f"no block points at a {name}"
    assert (resolved.flags["TRID"] >= 0).any()
    assert (resolved.flags["NAV"] >= 0).any()
    assert resolved.labelinc["LIN"].any()
