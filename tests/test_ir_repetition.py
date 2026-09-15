"""The repeating unit pypulseqpp detects against the one the C converter detects."""

from pathlib import Path

import pypulseqpp as pp
import pytest

from pulserver import _ext

FIXTURES = Path(__file__).parent / "fixtures" / "sequences"
# The limits the fixtures convert under; the period does not depend on them.
LIMITS = (
    42576000.0,
    3.0,
    40.0e3 * 42.576,
    150.0e3 * 42.576,
    2.0,
    20.0,
    2.0,
    20.0,
)


def fixtures():
    return sorted(p.name for p in FIXTURES.glob("*.seq"))


def detected(path):
    """Blocks per repetition, as the C converter and as pypulseqpp see it."""
    summary = _ext.summary_from_parse(str(path), *LIMITS, [0, 1, 2])
    sequence = pp.Sequence()
    sequence.read(path)
    return (
        [part["tr_size"] for part in summary["subsequences"]],
        [sequence._native.repetition()[0]],
    )


def written(tmp_path, name, build):
    sequence = pp.Sequence(pp.Opts())
    build(sequence)
    path = tmp_path / name
    sequence.write(path)
    return path


def alternating_delays(sequence):
    for _ in range(6):
        sequence.add_block(pp.make_delay(1e-3))
        sequence.add_block(pp.make_delay(2e-3))


def alternating_delays_around_a_gradient(sequence):
    gradient = pp.make_trapezoid("x", flat_area=1000, flat_time=1e-3)
    for _ in range(6):
        sequence.add_block(pp.make_delay(1e-3))
        sequence.add_block(gradient)
        sequence.add_block(pp.make_delay(2e-3))


@pytest.mark.parametrize("name", fixtures())
def test_a_fixture_repeats_over_the_same_blocks_either_way(name):
    theirs, ours = detected(FIXTURES / name)
    assert ours == theirs[:1]


def test_a_delay_of_any_length_is_one_definition_so_delays_alone_repeat_every_block(
    tmp_path,
):
    path = written(tmp_path, "all_delays.seq", alternating_delays)
    theirs, ours = detected(path)
    # The C detection keys a block on its duration, so it reads the two
    # lengths as a period of two; every pure delay being one definition makes
    # the same sequence one block played twelve times.
    assert theirs == [2]
    assert ours == [1]


def test_a_block_that_plays_something_restores_the_period_delays_alone_lose(tmp_path):
    path = written(
        tmp_path, "delays_and_a_gradient.seq", alternating_delays_around_a_gradient
    )
    theirs, ours = detected(path)
    assert ours == theirs[:1] == [3]
