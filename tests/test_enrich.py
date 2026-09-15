from pathlib import Path

import ismrmrd
import ismrmrd.xsd
import numpy as np
import pypulseqpp as pp
import pytest

from pulserver.mrd import AcquisitionFlag, EncodingSpace
from pulserver.vre._enrich import (
    FOV_OFFSET_PARAMETER,
    SequenceTable,
    enrich_acquisition,
    enrich_header,
    fov_offset_m,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sequences"
SAMPLES = 32
DELTA_K = 5.0  # 1/m: a 0.2 m field of view

HEADER = """<?xml version="1.0"?>
<ismrmrdHeader xmlns="http://www.ismrm.org/ISMRMRD">
  <experimentalConditions><H1resonanceFrequency_Hz>63500000</H1resonanceFrequency_Hz></experimentalConditions>
  <encoding>
    <encodedSpace><matrixSize><x>1</x><y>1</y><z>1</z></matrixSize><fieldOfView_mm><x>1</x><y>1</y><z>1</z></fieldOfView_mm></encodedSpace>
    <reconSpace><matrixSize><x>1</x><y>1</y><z>1</z></matrixSize><fieldOfView_mm><x>1</x><y>1</y><z>1</z></fieldOfView_mm></reconSpace>
    <encodingLimits/>
    <trajectory>cartesian</trajectory>
  </encoding>
</ismrmrdHeader>
"""


def header():
    return ismrmrd.xsd.CreateFromDocument(HEADER)


def add_readout(seq, *labels, rotation=None):
    system = pp.Opts()
    gx = pp.make_trapezoid(
        "x", flat_area=SAMPLES * DELTA_K, flat_time=3.2e-3, system=system
    )
    adc = pp.make_adc(
        num_samples=SAMPLES, duration=3.2e-3, delay=gx.rise_time, system=system
    )
    rewinder = pp.make_trapezoid("x", area=-gx.area / 2, duration=1e-3, system=system)
    extra = () if rotation is None else (rotation,)
    seq.add_block(rewinder, *extra)
    seq.add_block(gx, adc, *labels, *extra)
    seq.add_block(rewinder, *extra)


def written(seq, tmp_path):
    path = tmp_path / "synthetic.seq"
    seq.write(path)
    return SequenceTable.read(path)


def fixture(name):
    return SequenceTable.read(FIXTURES / name)


def reference(name):
    seq = pp.Sequence()
    seq.read(FIXTURES / name)
    return seq


def acquisitions(table, data=None):
    return [
        ismrmrd.Acquisition.from_array(
            np.ones((2, int(table.num_samples[index])), np.complex64)
            if data is None
            else data(index)
        )
        for index in range(len(table))
    ]


def readout_k(k, table, index):
    start = int(table.sample_offset[index])
    return k[:, start : start + int(table.num_samples[index])]


def has(table, flag):
    return (table.flags & np.uint64(flag.value)) != 0


@pytest.mark.parametrize(
    "name", ["gre_2d_3sl.seq", "epi_2d_main.seq", "mprage_stack_of_spirals_3d.seq"]
)
def test_counters_are_the_labels_each_readout_sees(name):
    table = fixture(name)
    labels = reference(name).evaluate_labels(evolution="adc")
    for label in ("LIN", "PAR", "SLC", "SEG", "REP"):
        expected = np.broadcast_to(labels.get(label, 0), (len(table),))
        np.testing.assert_array_equal(table.counters[label], expected)


def test_a_slice_closes_once_per_echo(tmp_path):
    seq = pp.Sequence(pp.Opts())
    for slc in range(2):
        for lin in range(3):
            for eco in range(2):
                add_readout(
                    seq,
                    pp.make_label("SLC", "SET", slc),
                    pp.make_label("LIN", "SET", lin),
                    pp.make_label("ECO", "SET", eco),
                )
    table = written(seq, tmp_path)
    closes = has(table, AcquisitionFlag.LAST_IN_SLICE)
    slc, eco, lin = (table.counters[name] for name in ("SLC", "ECO", "LIN"))
    assert closes.sum() == 4
    assert set(zip(slc[closes], eco[closes], strict=True)) == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    }
    assert (lin[closes] == 2).all()


def test_only_the_last_readout_of_a_chain_ends_the_measurement():
    table = fixture("dedup_gre_pair.seq")
    ends = np.flatnonzero(has(table, AcquisitionFlag.LAST_IN_MEASUREMENT))
    assert ends.tolist() == [len(table) - 1]
    assert [space.subsequence for space in table.spaces] == [0, 1]


def test_navigator_readouts_form_their_own_encoding_space(tmp_path):
    seq = pp.Sequence(pp.Opts())
    seq.set_definition("Matrix", [32, 3, 1])
    seq.set_definition("NavMatrix", [32, 1, 1])
    for lin in range(3):
        add_readout(
            seq, pp.make_label("LIN", "SET", lin), pp.make_label("NAV", "SET", 0)
        )
        add_readout(seq, pp.make_label("NAV", "SET", 1))
    table = written(seq, tmp_path)
    assert table.encoding_space.tolist() == [0, 1] * 3
    assert has(table, AcquisitionFlag.IS_NAVIGATION_DATA).tolist() == [False, True] * 3
    enriched = header()
    enrich_header(enriched, table)
    assert [encoding.encodedSpace.matrixSize.y for encoding in enriched.encoding] == [
        3,
        1,
    ]


def test_a_cartesian_line_carries_no_trajectory():
    table = fixture("gre_2d_3sl.seq")
    assert not table.spaces[0].trajectory
    acquisition = acquisitions(table)[0]
    enrich_acquisition(acquisition, table, 0)
    assert acquisition.trajectory_dimensions == 0
    enriched = header()
    enrich_header(enriched, table)
    assert enriched.encoding[0].trajectory == ismrmrd.xsd.trajectoryType.CARTESIAN


@pytest.mark.parametrize(
    "name", ["zte_3d.seq", "mprage_stack_of_spirals_3d.seq", "epi_2d_main.seq"]
)
def test_a_non_cartesian_readout_carries_its_absolute_k(name):
    table = fixture(name)
    k_adc = reference(name).calculate_kspace()[0]
    assert all(space.trajectory for space in table.spaces)
    for index, acquisition in enumerate(acquisitions(table)):
        enrich_acquisition(acquisition, table, index)
        k = readout_k(k_adc, table, index)
        dimensions = acquisition.trajectory_dimensions
        assert dimensions >= 1
        np.testing.assert_allclose(
            acquisition.traj, k[:dimensions].T, rtol=1e-5, atol=1e-3
        )
        assert np.abs(k[dimensions:]).max(initial=0.0) <= 1e-6 * np.abs(k).max()


def test_a_rotated_flat_readout_still_carries_a_trajectory(tmp_path):
    seq = pp.Sequence(pp.Opts())
    for angle in (0.0, np.pi / 2):
        add_readout(seq, rotation=pp.make_rotation(angle))
    assert written(seq, tmp_path).spaces[0].trajectory


def test_one_rotation_shared_by_every_readout_is_not_an_encoding(tmp_path):
    seq = pp.Sequence(pp.Opts())
    rotation = pp.make_rotation(np.pi / 2)
    for _ in range(2):
        add_readout(seq, rotation=rotation)
    assert not written(seq, tmp_path).spaces[0].trajectory


def test_a_rotated_readout_keeps_the_echo_index_of_its_unrotated_copy(tmp_path):
    seq = pp.Sequence(pp.Opts())
    for angle in (0.0, np.pi / 2):
        add_readout(seq, rotation=pp.make_rotation(angle))
    assert written(seq, tmp_path).center_sample.tolist() == [SAMPLES // 2] * 2


def test_the_echo_index_is_the_design_centre_sample():
    table = fixture("gre_2d_3sl.seq")
    design = int(
        np.atleast_1d(reference("gre_2d_3sl.seq").get_definition("kSpaceCenterSample"))[
            0
        ]
    )
    assert set(table.center_sample.tolist()) == {design}


def test_reversed_lines_meet_the_echo_at_the_mirrored_sample():
    table = fixture("epi_2d_main.seq")
    reverse = has(table, AcquisitionFlag.IS_REVERSE)
    assert reverse.any() and (~reverse).any()
    forward_centre = set(table.center_sample[~reverse].tolist())
    reverse_centre = set(table.center_sample[reverse].tolist())
    assert len(forward_centre) == len(reverse_centre) == 1
    assert forward_centre.pop() + reverse_centre.pop() == int(table.num_samples[0]) - 1


@pytest.mark.parametrize("name", ["gre_2d_3sl.seq", "zte_3d.seq"])
def test_fov_demodulation_recentres_an_offset_point(name):
    table = fixture(name)
    k_adc = reference(name).calculate_kspace()[0]
    offset = np.array([0.012, -0.034, 0.005])

    def point(index):
        phase = np.exp(-2j * np.pi * (offset @ readout_k(k_adc, table, index)))
        return np.tile(phase, (2, 1)).astype(np.complex64)

    for index, acquisition in enumerate(acquisitions(table, point)):
        enrich_acquisition(acquisition, table, index, offset)
        np.testing.assert_allclose(acquisition.data, 1.0, atol=1e-4)


def test_the_fov_offset_is_read_in_millimetres():
    enriched = header()
    enriched.userParameters = ismrmrd.xsd.userParametersType(
        userParameterString=[
            ismrmrd.xsd.userParameterStringType(
                name=FOV_OFFSET_PARAMETER, value="12 -34 5"
            )
        ]
    )
    np.testing.assert_allclose(fov_offset_m(enriched), [0.012, -0.034, 0.005])
    assert not fov_offset_m(header()).any()


def test_the_header_describes_each_encoding_space():
    table = fixture("gre_2d_3sl.seq")
    enriched = header()
    enrich_header(enriched, table)
    encoding = enriched.encoding[0]
    size = encoding.encodedSpace.matrixSize
    assert (size.x, size.y, size.z) == (64, 8, 3)
    fov = encoding.reconSpace.fieldOfView_mm
    assert (fov.x, fov.y, fov.z) == pytest.approx((220.0, 220.0, 15.0))
    assert encoding.encodingLimits.slice.maximum == 2
    assert encoding.encodingLimits.kspace_encoding_step_1.maximum == 7
    assert pytest.approx([30.0]) == enriched.sequenceParameters.TR
    assert pytest.approx([5.0]) == enriched.sequenceParameters.TE
    reparsed = ismrmrd.xsd.CreateFromDocument(ismrmrd.xsd.ToXML(enriched))
    space = EncodingSpace.from_header(reparsed)
    assert space.loops == ("slice",)
    assert space.phase_encodes == 8


def test_an_acquisition_of_the_wrong_length_is_refused():
    table = fixture("gre_2d_3sl.seq")
    samples = np.ones((2, int(table.num_samples[0]) + 1), np.complex64)
    with pytest.raises(ValueError, match="samples"):
        enrich_acquisition(ismrmrd.Acquisition.from_array(samples), table, 0)
