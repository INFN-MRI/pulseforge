"""The event and shape libraries of a sequence, as the IR conversion reads them."""

from __future__ import annotations

__all__ = ["SequenceLibraries", "Shape", "sequence_libraries"]

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from pypulseqpp import _ext as _core

#: Use tag of an RF event, as a Pulseq file writes it.
_RF_USE = {
    "": 0,
    "excitation": 1,
    "refocusing": 2,
    "inversion": 3,
    "saturation": 4,
    "preparation": 5,
    "other": 6,
}

_TRAPEZOID = 0
_ARBITRARY = 1


@dataclass(frozen=True)
class Shape:
    """One entry of the shape library.

    Attributes
    ----------
    num_uncompressed_samples
        Samples :attr:`samples` decompresses to.
    samples
        Run-length encoded on the derivative, as Pulseq stores a shape.
    """

    num_uncompressed_samples: int
    samples: NDArray[np.float64]


@dataclass(frozen=True)
class SequenceLibraries:
    """The libraries of one sequence, in the layout the IR conversion keys on.

    Event ids are the file's own, so a row's position is the id a block names
    and row 0 is id 1. A library entry no block plays is not recoverable and
    is absent: the rows reach as far as the largest id in use.

    Shape ids are minted here in first-use order. pypulseqpp hands a decoded
    event its samples but not the shape it is stored under, so what survives
    is which events share a shape, not the number the file gave it; shapes a
    file left duplicated are one here.

    Attributes
    ----------
    blocks : NDArray[np.float64]
        ``(N, 7)``: duration in block-duration rasters, then the rf, gx, gy,
        gz, adc and extension ids, 0 for an event the block does not play.
    rf : NDArray[np.float64]
        ``(R, 10)``: amplitude in Hz; the magnitude, phase and time shape ids;
        centre and delay in µs; the frequency and phase ppm offsets; the
        frequency offset in Hz and the phase offset in rad.
    rf_use : NDArray[np.int32]
        ``(R,)``: 0 unknown, 1 excitation, 2 refocusing, 3 inversion,
        4 saturation, 5 preparation, 6 other.
    grad : NDArray[np.float64]
        ``(G, 7)``, by type in column 0. A trapezoid (0): amplitude in Hz/m,
        rise, flat and fall times in µs, delay in µs. An arbitrary gradient
        (1): amplitude in Hz/m, the waveform's first and last values in Hz/m,
        the waveform and time shape ids, delay in µs.
    adc : NDArray[np.float64]
        ``(A, 8)``: sample count; dwell in ns; delay in µs; the frequency and
        phase ppm offsets; the frequency offset in Hz; the phase offset in
        rad; the phase modulation shape id.
    shapes : tuple[Shape, ...]
        Indexed by shape id minus one.
    """

    blocks: NDArray[np.float64]
    rf: NDArray[np.float64]
    rf_use: NDArray[np.int32]
    grad: NDArray[np.float64]
    adc: NDArray[np.float64]
    shapes: tuple[Shape, ...]


def sequence_libraries(sequence: Any) -> SequenceLibraries:
    """Read one ``pypulseqpp.Sequence`` into the libraries the IR conversion keys on.

    Each event id is decoded once, from the first block that plays it.

    Raises
    ------
    ValueError
        If an event id is played on no block the sequence can decode.
    """
    core = sequence._native
    events = np.asarray(core.block_events(), dtype=np.int64)
    durations = np.asarray(core.block_durations(), dtype=np.float64)

    blocks = np.zeros((durations.size, 7), dtype=np.float64)
    blocks[:, 0] = np.rint(durations / core.block_duration_raster())
    blocks[:, 1:] = events

    shapes = _ShapeTable()
    rf, rf_use = _rf_library(core, events, shapes)
    grad = _grad_library(core, events, shapes)
    adc = _adc_library(core, events, shapes)
    return SequenceLibraries(blocks, rf, rf_use, grad, adc, shapes.entries())


# %% private module subroutines


class _ShapeTable:
    """Interns decompressed waveforms, handing out 1-based ids in first-use order."""

    def __init__(self) -> None:
        self._ids: dict[bytes, int] = {}
        self._entries: list[Shape] = []

    def intern(self, samples: NDArray[np.float64]) -> int:
        samples = np.ascontiguousarray(samples, dtype=np.float64)
        key = samples.tobytes()
        if key not in self._ids:
            self._entries.append(
                Shape(int(samples.size), np.asarray(_core.compress_shape(samples)))
            )
            self._ids[key] = len(self._entries)
        return self._ids[key]

    def entries(self) -> tuple[Shape, ...]:
        return tuple(self._entries)


def _decoded(
    core: Any, events: NDArray[np.int64], column: int | tuple[int, ...]
) -> Any:
    """Yield ``(id, event)`` for every id played in ``column``, in id order.

    ``column`` is an index into the block table's event columns, or several
    when one library serves more than one, as the three gradient axes do.
    """
    columns = (column,) if isinstance(column, int) else column
    names = {0: "rf", 1: "gx", 2: "gy", 3: "gz", 4: "adc"}
    first: dict[int, tuple[int, str]] = {}
    for index, row in enumerate(events):
        for which in columns:
            identifier = int(row[which])
            if identifier > 0 and identifier not in first:
                first[identifier] = (index + 1, names[which])
    for identifier in sorted(first):
        block, name = first[identifier]
        event = core.decode_block(block)[name]
        if event is None:
            raise ValueError(f"block {block} does not decode the {name} it names")
        yield identifier, event


def _rows(decoded: list[tuple[int, Any]], width: int) -> NDArray[np.float64]:
    """Rows reaching the largest id played; an id no block plays keeps a zero row."""
    return np.zeros((max((i for i, _ in decoded), default=0), width), dtype=np.float64)


def _micro(seconds: float) -> float:
    return float(np.rint(float(seconds) * 1e6))


def _time_shape(times: NDArray[np.float64], raster: float, shapes: _ShapeTable) -> int:
    """Return the shape id of a vector of sample times, 0 when it lies on the raster.

    Times are stored in raster units. The grid ``0.5, 1.5, ...`` is what an
    event with no time shape plays, so a file that stores that grid explicitly
    reads back as an event with none.
    """
    ticks = np.asarray(times, dtype=np.float64) / raster
    if ticks.size and np.allclose(ticks, np.arange(ticks.size) + 0.5):
        return 0
    return shapes.intern(ticks)


def _rf_library(
    core: Any, events: NDArray[np.int64], shapes: _ShapeTable
) -> tuple[NDArray[np.float64], NDArray[np.int32]]:
    decoded = list(_decoded(core, events, 0))
    rows = _rows(decoded, 10)
    uses = np.zeros(rows.shape[0], dtype=np.int32)
    raster = core.rf_raster_time()
    for identifier, event in decoded:
        row = rows[identifier - 1]
        row[0] = event.amplitude
        row[1] = shapes.intern(np.asarray(event.magnitude))
        row[2] = shapes.intern(np.asarray(event.phase))
        row[3] = _time_shape(np.asarray(event.t), raster, shapes)
        row[4] = _micro(event.center)
        row[5] = _micro(event.delay)
        row[6] = event.freq_ppm
        row[7] = event.phase_ppm
        row[8] = event.freq_offset
        row[9] = event.phase_offset
        uses[identifier - 1] = _RF_USE[event.use]
    return rows, uses


def _grad_library(
    core: Any, events: NDArray[np.int64], shapes: _ShapeTable
) -> NDArray[np.float64]:
    decoded = list(_decoded(core, events, (1, 2, 3)))
    rows = _rows(decoded, 7)
    raster = core.grad_raster_time()
    for identifier, event in decoded:
        row = rows[identifier - 1]
        if event.type == "trap":
            row[0] = _TRAPEZOID
            row[1] = event.amplitude
            row[2] = _micro(event.rise_time)
            row[3] = _micro(event.flat_time)
            row[4] = _micro(event.fall_time)
            row[5] = _micro(event.delay)
            continue
        waveform = np.asarray(event.waveform, dtype=np.float64)
        # A gradient of no amplitude plays nothing whatever its stored shape.
        normalised = (
            waveform / event.amplitude if event.amplitude else np.zeros_like(waveform)
        )
        row[0] = _ARBITRARY
        row[1] = event.amplitude
        row[2] = event.first
        row[3] = event.last
        row[4] = shapes.intern(normalised)
        row[5] = _time_shape(np.asarray(event.tt), raster, shapes)
        row[6] = _micro(event.delay)
    return rows


def _adc_library(
    core: Any, events: NDArray[np.int64], shapes: _ShapeTable
) -> NDArray[np.float64]:
    decoded = list(_decoded(core, events, 4))
    rows = _rows(decoded, 8)
    for identifier, event in decoded:
        row = rows[identifier - 1]
        row[0] = event.num_samples
        row[1] = float(np.rint(event.dwell * 1e9))
        row[2] = _micro(event.delay)
        row[3] = event.freq_ppm
        row[4] = event.phase_ppm
        row[5] = event.freq_offset
        row[6] = event.phase_offset
        modulation = np.asarray(event.phase_modulation, dtype=np.float64)
        row[7] = shapes.intern(modulation) if modulation.size else 0
    return rows
