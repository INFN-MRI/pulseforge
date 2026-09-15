"""The IR cache built through pypulseqpp against the one the C parser builds."""

import shutil
import struct

import numpy as np
import pypulseqpp as pp
import pytest
from _host import FIXTURE_LIMITS, FIXTURES
from pypulseqpp import _ext as core

from pulserver import _ext
from pulserver.ir import cache_path, chain, convert, summary
from pulserver.ir._convert import convert_sequence, read_sequence
from pulserver.ir._source import sequence_libraries

SECTIONS = {0: "COMMON", 1: "INSTANCES", 2: "ROTATIONS", 3: "SHAPES", 4: "SCANLOOP"}


def fixtures():
    return sorted(p.name for p in FIXTURES.glob("*.seq"))


@pytest.fixture
def system():
    return pp.Opts(**FIXTURE_LIMITS)


@pytest.fixture
def copied(tmp_path):
    """The fixtures in a directory of their own, so a chain still resolves."""
    for path in FIXTURES.glob("*.seq"):
        shutil.copy(path, tmp_path / path.name)
    return tmp_path


def caches(path, system):
    """The cache each path writes for one sequence."""
    parsed = convert(path, system).read_bytes()
    cache_path(path).unlink()
    read = convert_sequence(path, system).read_bytes()
    return parsed, read


def sections(cache):
    entries = struct.unpack("<18i", cache[28:100])
    return {
        SECTIONS.get(entries[3 * i], entries[3 * i]): cache[
            entries[3 * i + 1] : entries[3 * i + 1] + entries[3 * i + 2]
        ]
        for i in range(6)
        if entries[3 * i + 2]
    }


def decompressed(entries):
    return [
        np.asarray(core.decompress_shape(np.asarray(samples), count))
        for count, samples in entries
    ]


def faithful(path):
    """Whether the whole chain gives the conversion nothing to drop or renumber.

    A library row no block plays is not readable through pypulseqpp and is
    dropped, and shape ids are minted in first-use order rather than read, so
    a file whose shapes are stored in another order is renumbered.
    """
    for part in chain(path):
        reference = _ext.parse_libraries(str(part))
        libraries = sequence_libraries(read_sequence(part))
        blocks = reference["blocks"]
        for library, columns in (("rf", (1,)), ("grad", (2, 3, 4)), ("adc", (5,))):
            played = {int(v) for c in columns for v in blocks[:, c]} - {0}
            if played != set(range(1, len(reference[library]) + 1)):
                return False
        ours = decompressed(
            [(s.num_uncompressed_samples, s.samples) for s in libraries.shapes]
        )
        theirs = decompressed(reference["shapes"])
        if len(ours) != len(theirs):
            return False
        if any(
            a.size != b.size or not np.allclose(a, b, rtol=1e-6, atol=1e-6)
            for a, b in zip(ours, theirs, strict=True)
        ):
            return False
    return True


@pytest.mark.parametrize("name", fixtures())
def test_a_sequence_read_through_pypulseqpp_segments_into_the_same_scan(
    name, copied, system
):
    path = copied / name
    convert(path, system)
    parsed = summary(path, system, cache_ext=".pseg")
    cache_path(path).unlink()
    convert_sequence(path, system)
    assert summary(path, system, cache_ext=".pseg") == parsed


@pytest.mark.parametrize("name", fixtures())
def test_the_execution_stream_and_rotations_are_the_ones_the_parser_writes(
    name, copied, system
):
    parsed, read = caches(copied / name, system)
    for section in ("ROTATIONS", "SCANLOOP"):
        assert sections(parsed).get(section) == sections(read).get(section), section


@pytest.mark.parametrize("name", fixtures())
def test_a_cache_is_the_parser_s_byte_for_byte_unless_a_row_was_dropped_or_renumbered(
    name, copied, system
):
    path = copied / name
    expected = faithful(path)
    parsed, read = caches(path, system)
    assert (parsed == read) == expected


@pytest.mark.parametrize("name", fixtures())
def test_dropping_a_row_no_block_plays_only_shortens_the_instance_tables(
    name, copied, system
):
    parsed, read = caches(copied / name, system)
    sizes = {
        section: (len(sections(parsed)[section]), len(sections(read)[section]))
        for section in sections(parsed)
    }
    for section, (before, after) in sizes.items():
        if section == "INSTANCES":
            assert after <= before, section
        else:
            assert after == before, section
