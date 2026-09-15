"""Enrichment of an MRD stream from the sequence that produced it.

The sequence chain is tabulated once, one row per readout in play order, and
acquisitions are matched to rows in stream order.
"""

from __future__ import annotations

__all__ = [
    "FOV_OFFSET_PARAMETER",
    "SequenceTable",
    "TableSpace",
    "enrich_acquisition",
    "enrich_header",
    "fov_offset_m",
]

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ismrmrd.xsd as xsd
import numpy as np
import pypulseqpp as pp

from .._labels import MRD_COUNTERS, MRD_FLAGS
from ..ir import chain
from ..mrd._acquisitions import AcquisitionFlag
from ..mrd._metadata import user_parameter

#: Header user parameter holding the prescription centre: a string of three
#: numbers in mm, along the sequence's x, y and z gradient axes.
FOV_OFFSET_PARAMETER = "pulserver_fov_offset_mm"

_F = AcquisitionFlag

#: Counter label, its first and last boundary flags, and whether it selects a
#: whole image rather than a position within one.
_BOUNDARY_COUNTERS = (
    ("SLC", _F.FIRST_IN_SLICE, _F.LAST_IN_SLICE, True),
    ("ECO", _F.FIRST_IN_CONTRAST, _F.LAST_IN_CONTRAST, True),
    ("PHS", _F.FIRST_IN_PHASE, _F.LAST_IN_PHASE, True),
    ("REP", _F.FIRST_IN_REPETITION, _F.LAST_IN_REPETITION, True),
    ("AVG", _F.FIRST_IN_AVERAGE, _F.LAST_IN_AVERAGE, True),
    ("SET", _F.FIRST_IN_SET, _F.LAST_IN_SET, True),
    ("LIN", _F.FIRST_IN_ENCODE_STEP1, _F.LAST_IN_ENCODE_STEP1, False),
    ("PAR", _F.FIRST_IN_ENCODE_STEP2, _F.LAST_IN_ENCODE_STEP2, False),
    ("SEG", _F.FIRST_IN_SEGMENT, _F.LAST_IN_SEGMENT, False),
)

#: Flag labels copied from the sequence, as bit masks. Boundary flags are
#: derived from the counters instead.
_SEQUENCE_FLAGS = {
    name: _F[constant.removeprefix("ACQ_")].value
    for name, constant in MRD_FLAGS.items()
    if not name.startswith(("FIRST", "LAST"))
}

#: Counter label to its ``encodingLimits`` field.
_LIMIT_FIELDS = {
    name: field.replace("encode_step", "encoding_step")
    for name, field in MRD_COUNTERS.items()
}

#: Counters every encoding space states limits for, written or not.
_STANDARD_LIMITS = ("LIN", "PAR", "AVG", "SLC", "ECO", "PHS", "REP", "SET", "SEG")

#: Samples per chunk when readouts are processed in bulk.
_CHUNK_SAMPLES = 1 << 22

#: Range of an axis, relative to the widest, below which a readout does not
#: sweep it; rotation rounding alone stays below it.
_SWEEP_FLOOR = 1e-9

#: Echo-index tie tolerance, in mean sample steps along the swept axes.
_ECHO_TIE = 1e-2

#: Largest deviation from a straight line, in mean sample steps, of a readout
#: still read as a line.
_LINE_TOLERANCE = 1e-3

#: Magnitude, relative to the readout's largest, below which a trailing
#: trajectory axis is dropped.
_AXIS_FLOOR = 1e-6


@dataclass(frozen=True)
class TableSpace:
    """One encoding space of a :class:`SequenceTable`.

    Attributes
    ----------
    subsequence
        Index of the chain file the space belongs to.
    navigator
        Whether the space holds the subsequence's ``NAV`` readouts.
    matrix
        ``(x, y, z)`` from ``Matrix``, or ``NavMatrix`` for a navigator;
        ``None`` when undefined.
    fov_mm
        ``(x, y, z)`` from ``FOV``, or ``NavFOV`` for a navigator, in mm;
        ``None`` when undefined.
    trajectory
        Whether acquisitions of the space carry a trajectory: some readout is
        not a straight line in k, or the block rotations of its readouts
        differ.
    """

    subsequence: int
    navigator: bool
    matrix: tuple[int, int, int] | None
    fov_mm: tuple[float, float, float] | None
    trajectory: bool


@dataclass(frozen=True)
class SequenceTable:
    """Per-readout description of a sequence chain, in play order.

    Attributes
    ----------
    counters : dict of str to ndarray
        Every label of ``MRD_COUNTERS``, one ``int32`` value per readout; 0
        where the sequence never writes it.
    flags : ndarray
        ``uint64`` ISMRMRD flag masks: the non-boundary flags the sequence
        sets, first/last flags of every counter the sequence writes, and
        ``LAST_IN_MEASUREMENT`` on the final readout of the chain. A boundary
        is read within its encoding space and the other image-selecting
        counters, so a slice closes once per echo.
    center_sample : ndarray
        ``int32`` echo index in the readout as acquired, -1 where k does not
        move. The sample nearest the subsequence's closest approach to k = 0,
        measured along the axes the readout sweeps in the sequence frame; a
        tie within 1% of a sample step goes to increasing k along the
        direction of travel, so reversed lines mirror onto forward ones.
    sample_time_us : ndarray
        ``float32`` dwell, in µs.
    encoding_space : ndarray
        ``int32`` index into :attr:`spaces`.
    num_samples, sample_offset : ndarray
        Samples of each readout and the column of its first sample in
        :attr:`k`.
    k : ndarray
        ``float32``, ``(3, samples)``: absolute k-space position of every
        sample, in 1/m, with block rotations applied.
    spaces : tuple of TableSpace
        Numbered in chain order: each subsequence's primary space, then its
        navigator space when it has ``NAV`` readouts.
    sequence_parameters : dict of str to list of float
        Over the chain's definitions: the ``TR`` and ``TI`` minima and every
        distinct ``TE`` in ascending order, in ms, and the ``FlipAngle``
        maximum, in degrees. Keys no file defines are absent.
    """

    counters: dict[str, np.ndarray]
    flags: np.ndarray
    center_sample: np.ndarray
    sample_time_us: np.ndarray
    encoding_space: np.ndarray
    num_samples: np.ndarray
    sample_offset: np.ndarray
    k: np.ndarray
    spaces: tuple[TableSpace, ...]
    sequence_parameters: dict[str, list[float]]

    def __len__(self) -> int:
        return int(self.num_samples.size)

    @classmethod
    def read(cls, path: Path | str) -> SequenceTable:
        """Tabulate the ``NextSequence`` chain starting at a sequence file.

        Raises
        ------
        ValueError
            If a file of the chain cannot be read, or the chain does not end.
        """
        parts: list[dict[str, Any]] = []
        spaces: list[TableSpace] = []
        definitions: dict[str, list[float]] = {
            "TR": [],
            "TE": [],
            "TI": [],
            "FlipAngle": [],
        }
        for subsequence, file in enumerate(chain(path)):
            seq = pp.Sequence()
            seq.read(file)
            part, part_spaces = _tabulate(seq, subsequence, len(spaces))
            parts.append(part)
            spaces.extend(part_spaces)
            for key, values in definitions.items():
                values.extend(_numbers(seq.get_definition(key)))

        offset = 0
        for part in parts:
            part["sample_offset"] = part["sample_offset"] + offset
            offset += int(part["num_samples"].sum())

        def joined(name: str, dtype: Any) -> np.ndarray:
            return np.concatenate([part[name] for part in parts]).astype(dtype)

        flags = joined("flags", np.uint64)
        if flags.size:
            flags[-1] |= np.uint64(_F.LAST_IN_MEASUREMENT.value)

        parameters: dict[str, list[float]] = {}
        if definitions["TR"]:
            parameters["TR"] = [1e3 * min(definitions["TR"])]
        if definitions["TE"]:
            parameters["TE"] = [1e3 * value for value in sorted(set(definitions["TE"]))]
        if definitions["TI"]:
            parameters["TI"] = [1e3 * min(definitions["TI"])]
        if definitions["FlipAngle"]:
            parameters["FlipAngle"] = [max(definitions["FlipAngle"])]

        return cls(
            counters={
                name: np.concatenate([part["counters"][name] for part in parts]).astype(
                    np.int32
                )
                for name in MRD_COUNTERS
            },
            flags=flags,
            center_sample=joined("center_sample", np.int32),
            sample_time_us=joined("sample_time_us", np.float32),
            encoding_space=joined("encoding_space", np.int32),
            num_samples=joined("num_samples", np.int32),
            sample_offset=joined("sample_offset", np.int64),
            k=np.concatenate([part["k"] for part in parts], axis=1).astype(np.float32),
            spaces=tuple(spaces),
            sequence_parameters=parameters,
        )


def fov_offset_m(header: Any) -> np.ndarray:
    """Return the prescription centre a header asks readouts to be demodulated to.

    Read from the :data:`FOV_OFFSET_PARAMETER` user parameter.

    Returns
    -------
    ndarray
        ``(3,)`` in metres along the sequence's x, y and z gradient axes;
        zeros when the header carries no offset.

    Raises
    ------
    ValueError
        If the parameter is not three numbers.
    """
    value = user_parameter(header, FOV_OFFSET_PARAMETER)
    if value in (None, ""):
        return np.zeros(3)
    parts = str(value).split()
    if len(parts) != 3:
        raise ValueError(
            f"{FOV_OFFSET_PARAMETER} must be three numbers in mm, got {value!r}"
        )
    return 1e-3 * np.array([float(part) for part in parts])


def enrich_header(header: Any, table: SequenceTable) -> None:
    """Describe the table's encoding spaces and sequence parameters in an MRD header.

    For every space, sets ``encodedSpace`` and ``reconSpace`` from the
    sequence's matrix and field of view when defined, ``encodingLimits`` from
    the counters of its readouts (minimum 0, centre half the maximum), and
    ``trajectory`` to ``OTHER`` or ``CARTESIAN``. Other fields of an existing
    encoding are kept; missing encodings are appended. Sequence parameters the
    table holds replace the header's.
    """
    parameters = header.sequenceParameters
    if table.sequence_parameters and parameters is None:
        parameters = xsd.sequenceParametersType()
        header.sequenceParameters = parameters
    for key, field in (
        ("TR", "TR"),
        ("TE", "TE"),
        ("TI", "TI"),
        ("FlipAngle", "flipAngle_deg"),
    ):
        if key in table.sequence_parameters:
            setattr(parameters, field, list(table.sequence_parameters[key]))

    encodings = list(header.encoding or ())
    for index, space in enumerate(table.spaces):
        members = table.encoding_space == index
        written = [
            name
            for name in MRD_COUNTERS
            if name in _STANDARD_LIMITS or table.counters[name][members].any()
        ]
        limits = xsd.encodingLimitsType(
            **{
                _LIMIT_FIELDS[name]: _limit(table.counters[name][members])
                for name in written
            }
        )
        trajectory = (
            xsd.trajectoryType.OTHER
            if space.trajectory
            else xsd.trajectoryType.CARTESIAN
        )
        if index < len(encodings):
            encoding = encodings[index]
            if space.matrix is not None or space.fov_mm is not None:
                encoding.encodedSpace = _encoding_space(space, encoding.encodedSpace)
                encoding.reconSpace = _encoding_space(space, encoding.reconSpace)
            encoding.encodingLimits = limits
            encoding.trajectory = trajectory
        else:
            encodings.append(
                xsd.encodingType(
                    encodedSpace=_encoding_space(space, None),
                    reconSpace=_encoding_space(space, None),
                    encodingLimits=limits,
                    trajectory=trajectory,
                )
            )
    header.encoding = encodings


def enrich_acquisition(
    acquisition: Any,
    table: SequenceTable,
    index: int,
    fov_offset: np.ndarray | None = None,
) -> None:
    """Stamp row ``index`` of the table on one acquisition, in place.

    Sets the encoding counters, flags, ``sample_time_us`` and
    ``encoding_space_ref``, and ``center_sample`` unless k does not move
    across the readout. Acquisitions of a trajectory space get the readout's
    absolute k as ``traj``, trailing axes with no k dropped. With
    ``fov_offset``, every channel is multiplied by ``exp(+i 2 pi d . k)``,
    which moves an object at ``d`` to the centre of the field of view; the
    trajectory is not changed.

    Parameters
    ----------
    fov_offset
        ``(3,)`` in metres along the sequence's gradient axes; see
        :func:`fov_offset_m`.

    Raises
    ------
    ValueError
        If the acquisition's sample count differs from the row's.
    """
    count = int(table.num_samples[index])
    if int(acquisition.number_of_samples) != count:
        raise ValueError(
            f"acquisition {index} has {acquisition.number_of_samples} samples; "
            f"the sequence plays {count}"
        )

    counters = acquisition.idx
    for name, field in MRD_COUNTERS.items():
        value = int(table.counters[name][index])
        if name.startswith("USER"):
            counters.user[int(name.removeprefix("USER"))] = value
        else:
            setattr(counters, field, value)
    acquisition.flags = int(table.flags[index])
    if table.center_sample[index] >= 0:
        acquisition.center_sample = int(table.center_sample[index])
    acquisition.sample_time_us = float(table.sample_time_us[index])
    space = int(table.encoding_space[index])
    acquisition.encoding_space_ref = space

    start = int(table.sample_offset[index])
    k = table.k[:, start : start + count]

    data = np.array(acquisition.data)
    if fov_offset is not None and np.any(fov_offset):
        cycles = np.asarray(fov_offset, dtype=np.float64) @ k.astype(np.float64)
        data = data * np.exp(2j * np.pi * cycles).astype(np.complex64)

    if table.spaces[space].trajectory:
        dimensions = _dimensions(k)
        channels = int(acquisition.active_channels)
        acquisition.resize(count, channels, dimensions)
        if dimensions:
            acquisition.traj[:] = k[:dimensions].T
    acquisition.data[:] = data


# %% private module subroutines


def _tabulate(
    seq: Any, subsequence: int, first_space: int
) -> tuple[dict[str, Any], list[TableSpace]]:
    """Rows and encoding spaces of one subsequence, spaces numbered from ``first_space``."""
    adc = seq.waveforms_and_times(compat=False).adc
    count = int(np.size(adc.block))
    num_samples = np.asarray(adc.num_samples, dtype=np.int64).reshape(count)
    sample_offset = np.zeros(count, dtype=np.int64)
    if count:
        sample_offset[1:] = np.cumsum(num_samples)[:-1]
        k = np.asarray(seq.calculate_kspace()[0], dtype=np.float64)
    else:
        k = np.zeros((3, 0))

    labels = seq.evaluate_labels(evolution="adc") if count else {}
    values = {name: _per_readout(value, count) for name, value in labels.items()}
    counters = {
        name: values.get(name, np.zeros(count, dtype=np.int64)) for name in MRD_COUNTERS
    }

    flags = np.zeros(count, dtype=np.uint64)
    for name, bit in _SEQUENCE_FLAGS.items():
        if name in values:
            flags[values[name] != 0] |= np.uint64(bit)
    navigator = (flags & np.uint64(_F.IS_NAVIGATION_DATA.value)) != 0
    local_space = navigator.astype(np.int64)
    flags |= _boundary_flags(counters, local_space, set(values))

    blocks = np.asarray(adc.block, dtype=np.int64).reshape(count)
    events = seq.block_events
    adc_ids = np.fromiter(
        (events[int(b)][5] for b in blocks), dtype=np.int64, count=count
    )
    ext_ids = np.fromiter(
        (events[int(b)][6] for b in blocks), dtype=np.int64, count=count
    )
    dwell = _per_event(
        adc_ids, blocks, lambda block: float(seq.get_block(block).adc.dwell)
    )
    quaternions = _per_event(
        ext_ids, blocks, lambda block: _quaternion(seq.get_block(block))
    )
    rotations = np.array([_rotation_matrix(q) for q in quaternions]).reshape(
        count, 3, 3
    )

    center_sample, line = _echo_indices_and_lines(
        k, sample_offset, num_samples, rotations
    )

    spaces = []
    for local, is_navigator in ((0, False), (1, True)):
        if is_navigator and not navigator.any():
            break
        members = local_space == local
        rotated = np.unique(np.round(quaternions[members], 9), axis=0).shape[0] > 1
        prefix = "Nav" if is_navigator else ""
        spaces.append(
            TableSpace(
                subsequence=subsequence,
                navigator=is_navigator,
                matrix=_triple(seq.get_definition(prefix + "Matrix"), int, 1.0),
                fov_mm=_triple(seq.get_definition(prefix + "FOV"), float, 1e3),
                trajectory=bool(rotated or not line[members].all()),
            )
        )

    part = {
        "counters": counters,
        "flags": flags,
        "center_sample": center_sample,
        "sample_time_us": 1e6 * dwell,
        "encoding_space": first_space + local_space,
        "num_samples": num_samples,
        "sample_offset": sample_offset,
        "k": k,
    }
    return part, spaces


def _per_readout(value: Any, count: int) -> np.ndarray:
    """Return a label record as one value per readout; ``evaluate_labels`` gives a scalar for one readout."""
    return np.broadcast_to(np.asarray(value, dtype=np.int64), (count,)).copy()


def _per_event(ids: np.ndarray, blocks: np.ndarray, value_of: Any) -> np.ndarray:
    """Evaluate ``value_of(block)`` once per distinct event id and spread it over the readouts."""
    if not ids.size:
        return np.zeros(0)
    _, first, inverse = np.unique(ids, return_index=True, return_inverse=True)
    values = np.array([value_of(int(blocks[at])) for at in first])
    return values[inverse.reshape(-1)]


def _quaternion(block: Any) -> np.ndarray:
    rotation = block.rotation
    if rotation is None:
        return np.array([1.0, 0.0, 0.0, 0.0])
    return np.asarray(rotation.quaternion, dtype=np.float64)


def _rotation_matrix(q: np.ndarray) -> np.ndarray:
    """Row-major rotation matrix of a scalar-first unit quaternion."""
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def _boundary_flags(
    counters: dict[str, np.ndarray], space: np.ndarray, written: set[str]
) -> np.ndarray:
    """First and last flags of every written counter, keyed by space and the other written image counters."""
    count = space.size
    flags = np.zeros(count, dtype=np.uint64)
    if not count:
        return flags
    for name, first, last, _ in _BOUNDARY_COUNTERS:
        if name not in written:
            continue
        enclosing = [
            other
            for other, _, _, selects_image in _BOUNDARY_COUNTERS
            if selects_image and other != name and other in written
        ]
        keys = np.stack(
            [space, *(counters[other] for other in enclosing), counters[name]], axis=1
        )
        _, first_at = np.unique(keys, axis=0, return_index=True)
        _, last_from_end = np.unique(keys[::-1], axis=0, return_index=True)
        flags[first_at] |= np.uint64(first.value)
        flags[count - 1 - last_from_end] |= np.uint64(last.value)
    return flags


def _chunks(num_samples: np.ndarray) -> list[tuple[np.ndarray, int]]:
    """Readout indices grouped by sample count, split to at most ``_CHUNK_SAMPLES`` samples."""
    out = []
    for n in np.unique(num_samples):
        rows = np.flatnonzero(num_samples == n)
        size = max(1, _CHUNK_SAMPLES // max(int(n), 1))
        out.extend((rows[at : at + size], int(n)) for at in range(0, rows.size, size))
    return out


def _nearest_along_travel(
    distance: np.ndarray, tolerance: np.ndarray, forward: np.ndarray
) -> np.ndarray:
    """Per row, the index of the smallest distance, ties toward increasing k along the direction of travel.

    A sample within ``tolerance`` of the running minimum ties with it; a tie
    takes the later sample on a forward readout and keeps the earlier one on a
    reverse readout.
    """
    before = np.minimum.accumulate(distance, axis=1)
    before = np.concatenate(
        [np.full((distance.shape[0], 1), np.inf), before[:, :-1]], axis=1
    )
    margin = tolerance[:, None]
    takes = np.where(
        forward[:, None], distance <= before + margin, distance < before - margin
    )
    return distance.shape[1] - 1 - np.argmax(takes[:, ::-1], axis=1)


def _echo_indices_and_lines(
    k: np.ndarray,
    sample_offset: np.ndarray,
    num_samples: np.ndarray,
    rotations: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Echo index of every readout, and whether each is a straight line in k.

    Works in the sequence frame, undoing each block's rotation, so rotated
    copies of one readout share an echo index.
    """
    count = sample_offset.size
    swept = np.zeros((count, 3), dtype=bool)
    tolerance = np.zeros(count)
    forward = np.ones(count, dtype=bool)
    nearest = np.zeros(count)
    nearest_at = np.zeros(count, dtype=np.int64)
    static_sq = np.zeros(count)
    line = np.ones(count, dtype=bool)
    chunks = [(rows, n) for rows, n in _chunks(num_samples) if n > 0]

    def sequence_frame(rows: np.ndarray, n: int) -> np.ndarray:
        rotated = k[:, sample_offset[rows, None] + np.arange(n)].transpose(1, 0, 2)
        return np.einsum("rji,rjn->rin", rotations[rows], rotated)

    for rows, n in chunks:
        kk = sequence_frame(rows, n)
        span = kk.max(axis=2) - kk.min(axis=2)
        mask = span > _SWEEP_FLOOR * span.max(axis=1, keepdims=True)
        swept[rows] = mask
        on_swept = kk * mask[:, :, None]
        step = (
            np.sqrt((np.diff(on_swept, axis=2) ** 2).sum(axis=1)).mean(axis=1)
            if n > 1
            else np.zeros(rows.size)
        )
        tolerance[rows] = _ECHO_TIE * step
        travel = (kk[:, :, -1] - kk[:, :, 0]) * mask
        dominant = np.abs(travel).argmax(axis=1)
        forward[rows] = travel[np.arange(rows.size), dominant] >= 0
        distance = np.sqrt((on_swept**2).sum(axis=1))
        nearest[rows] = distance.min(axis=1)
        nearest_at[rows] = _nearest_along_travel(
            distance, tolerance[rows], forward[rows]
        )
        static_sq[rows] = ((kk[:, :, 0] * ~mask) ** 2).sum(axis=1)
        if n > 2:
            t = np.arange(n) - (n - 1) / 2
            slope = (kk * t).sum(axis=2) / (t**2).sum()
            fit = kk.mean(axis=2, keepdims=True) + slope[:, :, None] * t
            deviation = np.abs(kk - fit).max(axis=(1, 2))
            line[rows] = (deviation <= _LINE_TOLERANCE * step) | ~mask.any(axis=1)

    # The subsequence's closest approach to k = 0; ties between readouts
    # prefer a forward one, whose indices need no mirroring.
    best = -1
    best_total = 0.0
    for i in np.flatnonzero(num_samples > 0):
        total = float(np.sqrt(nearest[i] ** 2 + static_sq[i]))
        if best < 0:
            best, best_total = int(i), total
            continue
        margin = max(tolerance[i], tolerance[best])
        if total < best_total - margin:
            best, best_total = int(i), total
        elif total <= best_total + margin:
            best_total = min(best_total, total)
            if forward[i] and not forward[best]:
                best = int(i)

    center = np.full(count, -1, dtype=np.int32)
    if best < 0:
        return center, line
    centre_k = sequence_frame(np.array([best]), int(num_samples[best]))[0][
        :, nearest_at[best]
    ]

    for rows, n in chunks:
        kk = sequence_frame(rows, n)
        mask = swept[rows]
        distance = np.sqrt(
            (((kk - centre_k[None, :, None]) * mask[:, :, None]) ** 2).sum(axis=1)
        )
        at = _nearest_along_travel(distance, tolerance[rows], forward[rows])
        center[rows] = np.where(mask.any(axis=1), at, -1)
    return center, line


def _dimensions(k: np.ndarray) -> int:
    """Trajectory axes of one readout, trailing axes with no k dropped."""
    largest = float(np.abs(k).max()) if k.size else 0.0
    dimensions = 3
    while (
        dimensions
        and float(np.abs(k[dimensions - 1]).max(initial=0.0)) <= _AXIS_FLOOR * largest
    ):
        dimensions -= 1
    return dimensions


def _numbers(value: Any) -> list[float]:
    if value in ("", None):
        return []
    return [float(v) for v in np.atleast_1d(value)]


def _triple(value: Any, kind: type, scale: float) -> tuple | None:
    numbers = _numbers(value)
    if len(numbers) < 3:
        return None
    return tuple(kind(round(scale * v, 9)) for v in numbers[:3])


def _limit(values: np.ndarray) -> Any:
    maximum = int(values.max()) if values.size else 0
    return xsd.limitType(minimum=0, maximum=maximum, center=maximum // 2)


def _encoding_space(space: TableSpace, current: Any) -> Any:
    """Return an ``encodingSpaceType`` from the space's definitions, falling back to ``current`` per field."""
    if space.matrix is not None:
        matrix = xsd.matrixSizeType(
            x=space.matrix[0], y=space.matrix[1], z=space.matrix[2]
        )
    elif current is not None:
        matrix = current.matrixSize
    else:
        matrix = xsd.matrixSizeType()
    if space.fov_mm is not None:
        fov = xsd.fieldOfViewMm(x=space.fov_mm[0], y=space.fov_mm[1], z=space.fov_mm[2])
    elif current is not None:
        fov = current.fieldOfView_mm
    else:
        fov = xsd.fieldOfViewMm(x=0.0, y=0.0, z=0.0)
    return xsd.encodingSpaceType(matrixSize=matrix, fieldOfView_mm=fov)
