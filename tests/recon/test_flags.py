from types import SimpleNamespace

import ismrmrd
import pytest

from pulserver.mrd import AcquisitionFlag, has_acquisition_flag


@pytest.mark.parametrize(
    "member", list(AcquisitionFlag), ids=lambda member: member.name
)
def test_acquisition_flags_are_the_ismrmrd_bits(member):
    assert member.position == getattr(ismrmrd, member.flag)


@pytest.mark.parametrize(
    "flag",
    [
        "ACQ_LAST_IN_SLICE",
        "LAST_IN_SLICE",
        "LASTSLC",
        AcquisitionFlag.LAST_IN_SLICE,
        ismrmrd.ACQ_LAST_IN_SLICE,
    ],
)
def test_every_spelling_of_a_flag_reaches_the_same_bit(flag):
    flagged = ismrmrd.Acquisition()
    flagged.setFlag(ismrmrd.ACQ_LAST_IN_SLICE)
    assert has_acquisition_flag(flagged, flag)
    assert not has_acquisition_flag(ismrmrd.Acquisition(), flag)


def test_an_integer_flag_is_a_bit_position_on_any_acquisition():
    position = ismrmrd.ACQ_LAST_IN_SLICE
    plain = SimpleNamespace(flags=1 << (position - 1))
    assert has_acquisition_flag(plain, position)
    assert not has_acquisition_flag(plain, position - 1)


def test_an_unknown_flag_name_is_refused():
    with pytest.raises(ValueError, match="Unknown ISMRMRD acquisition flag"):
        has_acquisition_flag(ismrmrd.Acquisition(), "NOT_A_FLAG")
