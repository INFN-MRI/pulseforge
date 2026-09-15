"""Per-readout facts of a Pulseq sequence, read through pypulseqpp.

Each wrapper takes a ``pypulseqpp.Sequence`` and returns arrays in the
sequence's units; nothing here depends on MRD.
"""

from __future__ import annotations

__all__ = ["ReadoutTable", "SequenceDefinitions", "read_chain"]

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

#: Range of an axis over a readout, relative to its widest axis, at or below
#: which the axis is constant.
_CONSTANT = 1e-6

#: Echo tie tolerance, as a fraction of the k step at the nearest sample.
_ECHO_TIE = 1e-2

#: Samples per chunk when readouts are processed in bulk.
_CHUNK_SAMPLES = 1 << 22


def read_chain(path: Path | str) -> list[tuple[Path, Any]]:
    """Read a sequence file and every file its ``NextSequence`` definitions name, in play order.

    A ``NextSequence`` name is relative to the directory of the file naming it.

    Returns
    -------
    list of (Path, pypulseqpp.Sequence)

    Raises
    ------
    FileNotFoundError
        If a file of the chain does not exist.
    ValueError
        If the chain names a file it has already played.
    """
    import pypulseqpp as pp

    chain: list[tuple[Path, Any]] = []
    played: set[Path] = set()
    current = Path(path)
    while True:
        if not current.is_file():
            raise FileNotFoundError(f"sequence chain file not found: {current}")
        resolved = current.resolve()
        if resolved in played:
            raise ValueError(f"the NextSequence chain returns to {current}")
        played.add(resolved)
        seq = pp.Sequence()
        seq.read(current)
        chain.append((current, seq))
        following = seq.get_definition("NextSequence")
        if following in ("", None):
            return chain
        current = current.parent / str(following)


@dataclass(frozen=True)
class SequenceDefinitions:
    """Definitions describing what a sequence acquires, in Pulseq units.

    Attributes
    ----------
    matrix, navigator_matrix : tuple of int or None
        ``Matrix`` and ``NavMatrix`` as ``(x, y, z)``; ``None`` when undefined.
    fov, navigator_fov : tuple of float or None
        ``FOV`` and ``NavFOV`` as ``(x, y, z)``, in metres; ``None`` when
        undefined.
    tr, te, ti : tuple of float
        ``TR``, ``TE`` and ``TI`` values, in seconds; empty when undefined.
    flip_angle : tuple of float
        ``FlipAngle`` values, in degrees; empty when undefined.
    """

    matrix: tuple[int, int, int] | None
    fov: tuple[float, float, float] | None
    navigator_matrix: tuple[int, int, int] | None
    navigator_fov: tuple[float, float, float] | None
    tr: tuple[float, ...]
    te: tuple[float, ...]
    ti: tuple[float, ...]
    flip_angle: tuple[float, ...]

    @classmethod
    def from_sequence(cls, seq: Any) -> SequenceDefinitions:
        """Read the definitions of a ``pypulseqpp.Sequence``."""
        return cls(
            matrix=_triple(seq.get_definition("Matrix"), int),
            fov=_triple(seq.get_definition("FOV"), float),
            navigator_matrix=_triple(seq.get_definition("NavMatrix"), int),
            navigator_fov=_triple(seq.get_definition("NavFOV"), float),
            tr=tuple(_numbers(seq.get_definition("TR"))),
            te=tuple(_numbers(seq.get_definition("TE"))),
            ti=tuple(_numbers(seq.get_definition("TI"))),
            flip_angle=tuple(_numbers(seq.get_definition("FlipAngle"))),
        )


@dataclass(frozen=True)
class ReadoutTable:
    """Every ADC readout of one sequence, in play order.

    Attributes
    ----------
    block : ndarray
        ``int64``, 1-based index of the block holding each readout.
    num_samples : ndarray
        ``int32`` samples per readout.
    sample_offset : ndarray
        ``int64`` column of each readout's first sample in :attr:`k`.
    dwell : ndarray
        ``float64`` dwell time, in seconds.
    labels : dict of str to ndarray
        Every label the sequence writes, with the ``int64`` value in force at
        each readout. Labels the sequence never writes are absent.
    k : ndarray
        ``(3, samples)``: absolute k-space position of every ADC sample, in
        1/m, with block rotations applied, as ``Sequence.calculate_kspace``
        returns it.
    center_sample : ndarray
        ``int32`` echo index: the sample of smallest ``|k|`` over the axes
        that vary across the readout. Samples within 1% of the k step at that
        sample tie, and a tie goes to the later sample, or to the earlier one
        on a readout labelled ``REV``, so reversed lines mirror onto forward
        ones. -1 when no axis varies.
    trajectory_dimensions : ndarray
        ``int8`` axes of :attr:`k` a readout keeps once the trailing axes
        constant across it are dropped; 0 when no axis varies.

    Examples
    --------
    >>> import pypulseqpp as pp
    >>> from pulserver.mrd import ReadoutTable
    >>> seq = pp.Sequence(pp.Opts())
    >>> gx = pp.make_trapezoid("x", flat_area=160.0, flat_time=3.2e-3)
    >>> adc = pp.make_adc(num_samples=32, duration=3.2e-3, delay=gx.rise_time)
    >>> rewinder = pp.make_trapezoid("x", area=-gx.area / 2, duration=1e-3)
    >>> for events in ((rewinder,), (gx, adc), (rewinder,)):
    ...     _ = seq.add_block(*events)
    >>> table = ReadoutTable.from_sequence(seq)
    >>> int(table.center_sample[0]), int(table.trajectory_dimensions[0])
    (16, 1)
    """

    block: np.ndarray
    num_samples: np.ndarray
    sample_offset: np.ndarray
    dwell: np.ndarray
    labels: dict[str, np.ndarray]
    k: np.ndarray
    center_sample: np.ndarray
    trajectory_dimensions: np.ndarray

    def __len__(self) -> int:
        return int(self.num_samples.size)

    @classmethod
    def from_sequence(cls, seq: Any) -> ReadoutTable:
        """Tabulate the readouts of a ``pypulseqpp.Sequence``."""
        adc = seq.waveforms_and_times(compat=False).adc
        count = int(np.size(adc.block))
        block = np.asarray(adc.block, dtype=np.int64).reshape(count)
        num_samples = np.asarray(adc.num_samples, dtype=np.int32).reshape(count)
        sample_offset = np.zeros(count, dtype=np.int64)
        sample_offset[1:] = np.cumsum(num_samples, dtype=np.int64)[:-1]

        if count:
            k = np.asarray(seq.calculate_kspace()[0], dtype=np.float64)
            labels = {
                name: np.broadcast_to(
                    np.asarray(value, dtype=np.int64), (count,)
                ).copy()
                for name, value in seq.evaluate_labels(evolution="adc").items()
            }
        else:
            k = np.zeros((3, 0))
            labels = {}

        dwell = np.zeros(count)
        if count:
            events = seq.block_events
            adc_ids = np.fromiter(
                (events[int(index)][5] for index in block), dtype=np.int64, count=count
            )
            _, first, inverse = np.unique(
                adc_ids, return_index=True, return_inverse=True
            )
            per_id = np.array(
                [float(seq.get_block(int(block[at])).adc.dwell) for at in first]
            )
            dwell = per_id[inverse.reshape(-1)]

        reverse = labels.get("REV", np.zeros(count, dtype=np.int64)) != 0
        center_sample, dimensions = _echo_and_dimensions(
            k, sample_offset, num_samples, reverse
        )
        return cls(
            block=block,
            num_samples=num_samples,
            sample_offset=sample_offset,
            dwell=dwell,
            labels=labels,
            k=k,
            center_sample=center_sample,
            trajectory_dimensions=dimensions,
        )

    def readout_k(self, index: int) -> np.ndarray:
        """Return the ``(3, num_samples)`` view of :attr:`k` for one readout."""
        start = int(self.sample_offset[index])
        return self.k[:, start : start + int(self.num_samples[index])]


# %% private module subroutines


def _echo_and_dimensions(
    k: np.ndarray,
    sample_offset: np.ndarray,
    num_samples: np.ndarray,
    reverse: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    count = sample_offset.size
    center = np.full(count, -1, dtype=np.int32)
    dimensions = np.zeros(count, dtype=np.int8)
    for n in (int(n) for n in np.unique(num_samples)):
        if n == 0:
            continue
        rows_of_size = np.flatnonzero(num_samples == n)
        chunk = max(1, _CHUNK_SAMPLES // n)
        for start in range(0, rows_of_size.size, chunk):
            rows = rows_of_size[start : start + chunk]
            kk = k[:, sample_offset[rows, None] + np.arange(n)].transpose(1, 0, 2)
            span = np.ptp(kk, axis=2)
            varying = span > _CONSTANT * span.max(axis=1, keepdims=True)
            moving = varying.any(axis=1)
            last_varying = 2 - np.argmax(varying[:, ::-1], axis=1)
            dimensions[rows] = np.where(moving, last_varying + 1, 0)
            if n < 2:
                continue

            swept = kk * varying[:, :, None]
            distance = np.sqrt((swept**2).sum(axis=1))
            nearest = distance.argmin(axis=1)
            steps = np.sqrt((np.diff(swept, axis=2) ** 2).sum(axis=1))
            index = np.arange(rows.size)
            step = np.maximum(
                steps[index, np.clip(nearest - 1, 0, n - 2)],
                steps[index, np.clip(nearest, 0, n - 2)],
            )
            tied = distance <= (distance[index, nearest] + _ECHO_TIE * step)[:, None]
            earliest = tied.argmax(axis=1)
            latest = n - 1 - tied[:, ::-1].argmax(axis=1)
            chosen = np.where(reverse[rows], earliest, latest)
            center[rows] = np.where(moving, chosen, -1)
    return center, dimensions


def _numbers(value: Any) -> list[float]:
    if value in ("", None):
        return []
    return [float(number) for number in np.atleast_1d(value)]


def _triple(value: Any, kind: type) -> tuple | None:
    numbers = _numbers(value)
    return tuple(kind(number) for number in numbers[:3]) if len(numbers) >= 3 else None
