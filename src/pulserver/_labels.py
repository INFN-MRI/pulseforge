"""Sequence label names and the ISMRMRD counters and flags they map to.

Canonical spellings are the ``.seq`` label names (``LIN``, ``SLC``,
``LASTSLC``). ISMRMRD and MRPro spellings are translated by
:func:`canonical_label`.
"""

from __future__ import annotations

__all__ = [
    "COUNTER_LABELS",
    "ENCODING_COUNTERS",
    "FLAG_LABELS",
    "FRAME_COUNTERS",
    "MRD_COUNTERS",
    "MRD_FLAGS",
    "SCANNER_FLAGS",
    "canonical_label",
]

#: Counter labels: one integer index per acquisition.
COUNTER_LABELS = (
    "SLC",
    "SEG",
    "REP",
    "AVG",
    "SET",
    "ECO",
    "PHS",
    "LIN",
    "PAR",
    "ACQ",
    "USER0",
    "USER1",
    "USER2",
    "USER3",
    "USER4",
    "USER5",
    "USER6",
    "USER7",
)

#: Counters selecting the image an acquisition belongs to.
FRAME_COUNTERS = ("SLC", "ECO", "PHS", "REP", "AVG", "SET")

#: Counters locating an acquisition within its image.
ENCODING_COUNTERS = ("LIN", "PAR", "SEG")

#: Counter label to ISMRMRD ``EncodingCounters`` field. ``ACQ`` has no MRD
#: field. ``USERn`` is ``user_n`` in ``encodingLimits`` and ``idx.user[n]`` on
#: an acquisition.
MRD_COUNTERS = {
    "LIN": "kspace_encode_step_1",
    "PAR": "kspace_encode_step_2",
    "AVG": "average",
    "SLC": "slice",
    "ECO": "contrast",
    "PHS": "phase",
    "REP": "repetition",
    "SET": "set",
    "SEG": "segment",
    "USER0": "user_0",
    "USER1": "user_1",
    "USER2": "user_2",
    "USER3": "user_3",
    "USER4": "user_4",
    "USER5": "user_5",
    "USER6": "user_6",
    "USER7": "user_7",
}

#: Flag label to ISMRMRD acquisition-flag constant, for every ISMRMRD flag.
#: Boundary flags follow from the counters and the acquisition order;
#: classifying flags come only from the sequence; transport flags come from
#: whatever packs the data.
MRD_FLAGS = {
    # boundary
    "FIRSTLIN": "ACQ_FIRST_IN_ENCODE_STEP1",
    "LASTLIN": "ACQ_LAST_IN_ENCODE_STEP1",
    "FIRSTPAR": "ACQ_FIRST_IN_ENCODE_STEP2",
    "LASTPAR": "ACQ_LAST_IN_ENCODE_STEP2",
    "FIRSTAVG": "ACQ_FIRST_IN_AVERAGE",
    "LASTAVG": "ACQ_LAST_IN_AVERAGE",
    "FIRSTSLC": "ACQ_FIRST_IN_SLICE",
    "LASTSLC": "ACQ_LAST_IN_SLICE",
    "FIRSTECO": "ACQ_FIRST_IN_CONTRAST",
    "LASTECO": "ACQ_LAST_IN_CONTRAST",
    "FIRSTPHS": "ACQ_FIRST_IN_PHASE",
    "LASTPHS": "ACQ_LAST_IN_PHASE",
    "FIRSTREP": "ACQ_FIRST_IN_REPETITION",
    "LASTREP": "ACQ_LAST_IN_REPETITION",
    "FIRSTSET": "ACQ_FIRST_IN_SET",
    "LASTSET": "ACQ_LAST_IN_SET",
    "FIRSTSEG": "ACQ_FIRST_IN_SEGMENT",
    "LASTSEG": "ACQ_LAST_IN_SEGMENT",
    "LASTSCAN": "ACQ_LAST_IN_MEASUREMENT",
    # classifying
    "NOISE": "ACQ_IS_NOISE_MEASUREMENT",
    "REF": "ACQ_IS_PARALLEL_CALIBRATION",
    "IMA": "ACQ_IS_PARALLEL_CALIBRATION_AND_IMAGING",
    "REV": "ACQ_IS_REVERSE",
    "NAV": "ACQ_IS_NAVIGATION_DATA",
    "PHASECORR": "ACQ_IS_PHASECORR_DATA",
    "HPFEEDBACK": "ACQ_IS_HPFEEDBACK_DATA",
    "DUMMYSCAN": "ACQ_IS_DUMMYSCAN_DATA",
    "RTFEEDBACK": "ACQ_IS_RTFEEDBACK_DATA",
    "COILCORR": "ACQ_IS_SURFACECOILCORRECTIONSCAN_DATA",
    "PHSTABREF": "ACQ_IS_PHASE_STABILIZATION_REFERENCE",
    "PHSTAB": "ACQ_IS_PHASE_STABILIZATION",
    # transport
    "COMPRESS1": "ACQ_COMPRESSION1",
    "COMPRESS2": "ACQ_COMPRESSION2",
    "COMPRESS3": "ACQ_COMPRESSION3",
    "COMPRESS4": "ACQ_COMPRESSION4",
    # free
    "USERFLAG1": "ACQ_USER1",
    "USERFLAG2": "ACQ_USER2",
    "USERFLAG3": "ACQ_USER3",
    "USERFLAG4": "ACQ_USER4",
    "USERFLAG5": "ACQ_USER5",
    "USERFLAG6": "ACQ_USER6",
    "USERFLAG7": "ACQ_USER7",
    "USERFLAG8": "ACQ_USER8",
}

#: Flag labels the scanner interpreter consumes; they have no MRD counterpart.
SCANNER_FLAGS = ("PMC", "NOROT", "NOPOS", "NOSCL", "OFF", "ONCE", "TRID")

#: Every flag label. ``SMS`` carries a multiband group index, for which ISMRMRD
#: has no field; a band index a reconstruction needs travels in a ``USER*``
#: counter.
FLAG_LABELS = (*MRD_FLAGS, "SMS", *SCANNER_FLAGS)

_CANONICAL = frozenset(COUNTER_LABELS) | frozenset(FLAG_LABELS)

#: Non-canonical spellings. ``K1`` and ``K2`` are MRPro's ``AcqIdx`` names.
_ALIASES = {
    **{mrd.upper(): name for name, mrd in MRD_COUNTERS.items()},
    **{mrd: name for name, mrd in MRD_FLAGS.items()},
    **{mrd[len("ACQ_") :]: name for name, mrd in MRD_FLAGS.items()},
    "K1": "LIN",
    "K2": "PAR",
}

#: Names that read as labels but are none, with the reason they are refused.
_REFUSED = {
    "K0": (
        "k0 is the readout direction, the samples within one acquisition, and "
        "no counter indexes it; the readout extent is "
        "encodingLimits.kspace_encoding_step_0"
    ),
}


def canonical_label(name: str) -> str:
    """Return the canonical spelling of a label name.

    Accepts the canonical name, an ISMRMRD counter field or flag constant name
    (with or without ``ACQ_``), or MRPro's ``k1``/``k2``, in any case. An
    unrecognised name is returned unchanged, so custom labels pass through.

    Raises
    ------
    ValueError
        If the name is ``k0``, which reads as a label but indexes nothing.

    Examples
    --------
    >>> from pulserver._labels import canonical_label
    >>> canonical_label("kspace_encode_step_1")
    'LIN'
    >>> canonical_label("k1"), canonical_label("k2")
    ('LIN', 'PAR')
    >>> canonical_label("ACQ_LAST_IN_SLICE"), canonical_label("LAST_IN_SLICE")
    ('LASTSLC', 'LASTSLC')
    >>> canonical_label("LIN"), canonical_label("BIN")
    ('LIN', 'BIN')
    """
    upper = name.upper()
    if upper in _CANONICAL:
        return upper
    if upper in _REFUSED:
        raise ValueError(f"{name!r} is not a label: {_REFUSED[upper]}")
    return _ALIASES.get(upper, name)
