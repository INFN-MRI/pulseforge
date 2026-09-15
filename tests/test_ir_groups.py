"""The safety groups a sequence's TRID labels cut it into."""

from pathlib import Path

import pypulseqpp as pp
import pytest

from pulserver.ir import convert, summary

FIXTURES = Path(__file__).parent / "fixtures" / "sequences"
SYSTEM = pp.Opts(
    max_grad=40.0,
    grad_unit="mT/m",
    max_slew=170.0,
    slew_unit="T/m/s",
    B0=3.0,
    rf_raster_time=1e-6,
    grad_raster_time=1e-5,
    adc_raster_time=1e-7,
    block_duration_raster=1e-5,
)


def labelled(path, ids):
    """A delay and a gradient per unit, with ``ids[i]`` set at the head of unit i.

    A ``None`` entry leaves the unit unlabelled, so it continues the group the
    unit before it opened.
    """
    sequence = pp.Sequence(pp.Opts())
    gradient = pp.make_trapezoid("x", flat_area=1000, flat_time=1e-3)
    for trid in ids:
        delay = pp.make_delay(1e-3)
        if trid is None:
            sequence.add_block(delay)
        else:
            sequence.add_block(
                pp.make_label(type="SET", label="TRID", value=trid), delay
            )
        sequence.add_block(gradient)
    sequence.write(path)
    return path


def groups(path, **kwargs):
    return summary(path, SYSTEM, **kwargs)["subsequences"][0]["tr_groups"]


def test_a_label_opens_an_occurrence_even_where_the_id_does_not_change(tmp_path):
    counted = groups(labelled(tmp_path / "four.seq", [1, 1, 1, 1]))
    assert [(g["trid"], g["num_instances"]) for g in counted] == [(1, 4)]


def test_an_occurrence_runs_to_the_next_label_not_to_the_next_detected_period(
    tmp_path,
):
    path = labelled(tmp_path / "every_other.seq", [1, None, 1, None])
    whole = summary(path, SYSTEM)["subsequences"][0]
    # The sequence repeats every delay-and-gradient pair, but the labels name a
    # unit of two pairs, and the labels are what a group is cut on.
    assert (whole["tr_size"], whole["num_trs"]) == (2, 4)
    counted = whole["tr_groups"]
    assert [(g["trid"], g["num_instances"]) for g in counted] == [(1, 2)]
    assert counted[0]["one_instance_duration_us"] == 2 * 2280


def test_each_distinct_id_is_its_own_group(tmp_path):
    counted = groups(labelled(tmp_path / "two_ids.seq", [1, 2, 1, 2]))
    assert [(g["trid"], g["num_instances"]) for g in counted] == [(1, 2), (2, 2)]


def test_a_group_reports_what_all_its_occurrences_last(tmp_path):
    counted = groups(labelled(tmp_path / "total.seq", [3, 3, 3]))
    assert counted[0]["total_duration_us"] == 3 * counted[0]["one_instance_duration_us"]


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("*.seq")))
def test_a_sequence_that_labels_nothing_is_one_ungrouped_whole(name):
    assert groups(FIXTURES / name) == []


def test_the_cache_carries_the_groups_it_was_written_from(tmp_path):
    path = labelled(tmp_path / "cached.seq", [1, 1, 2, 2])
    convert(path, SYSTEM)
    assert groups(path, cache_ext=".pseg") == groups(path)
