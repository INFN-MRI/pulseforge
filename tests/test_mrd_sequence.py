from pathlib import Path

import numpy as np
import pypulseqpp as pp
import pytest
from _synthetic import SAMPLES, add_readout

from pulserver.mrd import ReadoutTable, SequenceDefinitions, read_chain

FIXTURES = Path(__file__).parent / "fixtures" / "sequences"


def fixture(name):
    seq = pp.Sequence()
    seq.read(FIXTURES / name)
    return seq, ReadoutTable.from_sequence(seq)


def synthetic(*readouts):
    seq = pp.Sequence(pp.Opts())
    for keywords in readouts:
        add_readout(seq, **keywords)
    return ReadoutTable.from_sequence(seq)


def test_readouts_follow_the_adc_windows_in_play_order():
    seq, table = fixture("gre_2d_3sl.seq")
    adc = seq.waveforms_and_times(compat=False).adc
    np.testing.assert_array_equal(table.block, adc.block)
    assert table.num_samples.tolist() == [64] * 24
    assert table.sample_offset.tolist() == list(range(0, 64 * 24, 64))
    assert table.k.shape == (3, 64 * 24)
    np.testing.assert_allclose(table.dwell, 1e-5)


def test_labels_are_the_values_in_force_at_each_readout():
    seq, table = fixture("epi_2d_main.seq")
    expected = seq.evaluate_labels(evolution="adc")
    assert set(table.labels) == set(expected)
    for name, values in expected.items():
        np.testing.assert_array_equal(
            table.labels[name], np.broadcast_to(values, (len(table),))
        )


def test_the_echo_index_is_the_design_centre_sample():
    seq, table = fixture("gre_2d_3sl.seq")
    design = int(np.atleast_1d(seq.get_definition("kSpaceCenterSample"))[0])
    assert set(table.center_sample.tolist()) == {design}


def test_reversed_lines_meet_the_echo_at_the_mirrored_sample():
    _, table = fixture("epi_2d_main.seq")
    reverse = table.labels["REV"] != 0
    assert reverse.any() and (~reverse).any()
    forward_centre = set(table.center_sample[~reverse].tolist())
    reverse_centre = set(table.center_sample[reverse].tolist())
    assert len(forward_centre) == len(reverse_centre) == 1
    assert forward_centre.pop() + reverse_centre.pop() == int(table.num_samples[0]) - 1


def test_a_spiral_out_echo_is_its_first_sample():
    _, table = fixture("mprage_stack_of_spirals_3d.seq")
    assert table.center_sample.tolist() == [0] * len(table)


def test_a_rotated_readout_keeps_the_echo_index_of_its_unrotated_copy():
    table = synthetic(
        {"rotation": pp.make_rotation(0.0)}, {"rotation": pp.make_rotation(np.pi / 2)}
    )
    assert table.center_sample.tolist() == [SAMPLES // 2] * 2


def test_a_readout_whose_k_does_not_move_has_no_echo_and_no_trajectory():
    table = synthetic({"moving": False})
    assert table.center_sample.tolist() == [-1]
    assert table.trajectory_dimensions.tolist() == [0]


@pytest.mark.parametrize(
    ("name", "dimensions"),
    [
        ("gre_2d_3sl.seq", 1),
        ("epi_2d_main.seq", 1),
        ("mprage_stack_of_spirals_3d.seq", 2),
        ("zte_3d.seq", 3),
    ],
)
def test_trailing_constant_axes_are_dropped(name, dimensions):
    _, table = fixture(name)
    assert set(table.trajectory_dimensions.tolist()) == {dimensions}


def test_a_leading_constant_axis_stays():
    table = synthetic(
        {"rotation": pp.make_rotation(0.0)}, {"rotation": pp.make_rotation(np.pi / 2)}
    )
    assert table.trajectory_dimensions.tolist() == [1, 2]


def test_a_chain_is_read_in_play_order():
    chain = read_chain(FIXTURES / "dedup_gre_pair.seq")
    assert [path.name for path, _ in chain] == [
        "dedup_gre_pair.seq",
        "dedup_gre_pair_b.seq",
    ]


def test_a_chain_that_returns_to_a_played_file_is_refused(tmp_path):
    seq = pp.Sequence(pp.Opts())
    add_readout(seq)
    seq.set_definition("NextSequence", "loop.seq")
    seq.write(tmp_path / "loop.seq")
    with pytest.raises(ValueError, match="returns to"):
        read_chain(tmp_path / "loop.seq")


def test_a_missing_chain_file_is_refused(tmp_path):
    seq = pp.Sequence(pp.Opts())
    add_readout(seq)
    seq.set_definition("NextSequence", "absent.seq")
    seq.write(tmp_path / "first.seq")
    with pytest.raises(FileNotFoundError, match=r"absent\.seq"):
        read_chain(tmp_path / "first.seq")


def test_definitions_are_read_in_pulseq_units():
    seq, _ = fixture("gre_2d_3sl.seq")
    definitions = SequenceDefinitions.from_sequence(seq)
    assert definitions.matrix == (64, 8, 3)
    assert definitions.fov == pytest.approx((0.22, 0.22, 0.015))
    assert definitions.te == pytest.approx((0.005,))
    assert definitions.tr == pytest.approx((0.03,))
    assert definitions.navigator_matrix is None
    assert definitions.ti == ()
