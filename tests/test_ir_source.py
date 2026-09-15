"""The libraries read through pypulseqpp against the ones the C parser reads.

The text fixtures only. ``se_propeller_2d.bin`` frames a binary definition
name as a NUL-terminated string, which is what ``src/c/pulseq`` reads;
pypulseqpp writes and reads an int32 length before the name and refuses the
file at the first one.
"""

from pathlib import Path

import numpy as np
import pypulseqpp as pp
import pytest
from pypulseqpp import _ext as core

from pulserver import _ext
from pulserver.ir._source import sequence_libraries

FIXTURES = Path(__file__).parent / "fixtures" / "sequences"
# The C parser holds its cells as float32; pypulseqpp holds doubles, so every
# comparison is to single precision against the largest value in hand.
SINGLE = 1e-6


def shape_columns(library, row):
    """Columns of a row holding a shape id; a trapezoid carries times in its."""
    if library == "rf":
        return (1, 2, 3)
    if library == "adc":
        return (7,)
    return (4, 5) if row[0] == 1 else ()


def fixtures():
    return sorted(p.name for p in FIXTURES.glob("*.seq"))


def parsed(name):
    return _ext.parse_libraries(str(FIXTURES / name))


def read(name):
    sequence = pp.Sequence()
    sequence.read(FIXTURES / name)
    return sequence_libraries(sequence)


def decompressed(entries):
    """Every shape of a library as its samples, keyed by id."""
    return {
        index + 1: np.asarray(core.decompress_shape(np.asarray(samples), count))
        for index, (count, samples) in enumerate(entries)
    }


def close(ours, theirs):
    """Whether two arrays agree to single precision, scaled by what they hold."""
    ours, theirs = np.asarray(ours, float), np.asarray(theirs, float)
    scale = max(float(np.max(np.abs(theirs))) if theirs.size else 0.0, 1.0)
    return np.allclose(ours, theirs, rtol=SINGLE, atol=SINGLE * scale)


def shape_map(libraries, reference):
    """Map each read shape id onto the parsed shape holding the same samples."""
    ours = decompressed(
        [(shape.num_uncompressed_samples, shape.samples) for shape in libraries.shapes]
    )
    theirs = decompressed(reference["shapes"])
    mapping = {0: 0}
    for identifier, samples in ours.items():
        matches = [
            other
            for other, candidate in theirs.items()
            if candidate.size == samples.size and close(samples, candidate)
        ]
        assert matches, f"shape {identifier} is in no parsed shape"
        mapping[identifier] = matches[0]
    return mapping


def played(reference, column):
    """Ids of ``column`` of the block table that some block plays."""
    blocks = reference["blocks"]
    columns = column if isinstance(column, tuple) else (column,)
    return sorted({int(v) for c in columns for v in blocks[:, c]} - {0})


def compare(name, library, column):
    reference = parsed(name)
    libraries = read(name)
    mapping = shape_map(libraries, reference)
    ours = getattr(libraries, library)
    theirs = reference[library]
    for identifier in played(reference, column):
        mine = np.array(ours[identifier - 1], dtype=np.float64)
        for index in shape_columns(library, mine):
            mine[index] = mapping[int(mine[index])]
        assert close(mine, theirs[identifier - 1]), (
            f"{library} {identifier} of {name}: {mine} != {theirs[identifier - 1]}"
        )


@pytest.mark.parametrize("name", fixtures())
def test_the_block_table_is_the_one_the_parser_reads(name):
    reference = parsed(name)
    libraries = read(name)
    np.testing.assert_array_equal(
        libraries.blocks.astype(np.int64), reference["blocks"].astype(np.int64)
    )


@pytest.mark.parametrize("name", fixtures())
def test_every_played_rf_event_is_the_one_the_parser_reads(name):
    compare(name, "rf", 1)


@pytest.mark.parametrize("name", fixtures())
def test_every_played_gradient_is_the_one_the_parser_reads(name):
    compare(name, "grad", (2, 3, 4))


@pytest.mark.parametrize("name", fixtures())
def test_every_played_readout_is_the_one_the_parser_reads(name):
    compare(name, "adc", 5)


@pytest.mark.parametrize("name", fixtures())
def test_the_rf_use_tags_are_the_ones_the_parser_reads(name):
    reference = parsed(name)
    libraries = read(name)
    for identifier in played(reference, 1):
        assert int(libraries.rf_use[identifier - 1]) == int(
            reference["rf_use"][identifier - 1]
        ), f"rf {identifier} of {name}"


@pytest.mark.parametrize("name", fixtures())
def test_every_shape_a_played_event_names_is_a_shape_the_parser_read(name):
    reference = parsed(name)
    libraries = read(name)
    shape_map(libraries, reference)
    assert libraries.shapes
