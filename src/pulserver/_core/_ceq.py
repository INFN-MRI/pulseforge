"""Ceq structure definition."""

__all__ = ["Ceq", "PulseqBlock"]

from dataclasses import dataclass
from types import SimpleNamespace

import struct
import numpy as np
import pypulseq as pp

from . import _autoseg

CHANNEL_ENUM = {"osc0": 0, "osc1": 1, "ext1": 2}
SEGMENT_RINGDOWN_TIME = 116 * 1e-6  # TODO: doesn't have to be hardcoded


@dataclass
class PulseqShapeArbitrary:
    n_samples: int
    raster: float
    magnitude: np.ndarray
    phase: np.ndarray | None = None

    def __post_init__(self):
        self.magnitude = np.asarray(self.magnitude, dtype=np.float32)
        self.phase = (
            np.asarray(self.phase, dtype=np.float32) if self.phase is not None else None
        )

    def to_bytes(self, endian=">") -> bytes:
        if self.phase is not None:
            return (
                struct.pack(endian + "i", self.n_samples)
                + struct.pack(endian + "f", self.raster)
                + self.magnitude.astype(endian + "f4").tobytes()
                + self.phase.astype(endian + "f4").tobytes()
            )

        return (
            struct.pack(endian + "i", self.n_samples)
            + struct.pack(endian + "f", self.raster)
            + self.magnitude.astype(endian + "f4").tobytes()
        )


@dataclass
class PulseqShapeTrap:
    amplitude: float
    rise_time: float
    flat_time: float
    fall_time: float

    def to_bytes(self, endian=">") -> bytes:
        return (
            struct.pack(endian + "f", self.amplitude)
            + struct.pack(endian + "f", self.rise_time)
            + struct.pack(endian + "f", self.flat_time)
            + struct.pack(endian + "f", self.fall_time)
        )


@dataclass
class PulseqRF:
    type: int
    wav: PulseqShapeArbitrary
    duration: float
    delay: float

    def to_bytes(self, endian=">") -> bytes:
        return (
            struct.pack(endian + "h", self.type)
            + self.wav.to_bytes(endian)
            + struct.pack(endian + "f", self.duration)
            + struct.pack(endian + "f", self.delay)
        )

    @classmethod
    def from_struct(cls, data: SimpleNamespace) -> "PulseqRF":
        n_samples = data.signal.shape[0]
        raster = np.diff(data.t)[0]
        rho = np.abs(data.signal)
        theta = np.angle(data.signal)

        return cls(
            type=1,
            wav=PulseqShapeArbitrary(n_samples, raster, rho, theta),
            duration=data.shape_dur,
            delay=data.delay,
        )


@dataclass
class PulseqGrad:
    type: int
    delay: float
    shape: PulseqShapeArbitrary | PulseqShapeTrap

    def to_bytes(self, endian=">") -> bytes:
        return (
            struct.pack(endian + "h", self.type)
            + struct.pack(endian + "f", self.delay)
            + self.shape.to_bytes(endian)
        )

    @classmethod
    def from_struct(cls, data: SimpleNamespace) -> "PulseqGrad":
        if data.type == "trap":
            type = 1
            shape_obj = PulseqShapeTrap(
                data.amplitude, data.rise_time, data.flat_time, data.fall_time
            )
        elif data.type == "grad":
            type = 2
            n_samples = data.waveform.shape[0]
            raster = np.diff(data.tt)[0]
            waveform = data.waveform
            shape_obj = PulseqShapeArbitrary(n_samples, raster, waveform)
        return cls(type=type, delay=data.delay, shape=shape_obj)


@dataclass
class PulseqADC:
    type: int
    num_samples: int
    dwell: float
    delay: float

    def to_bytes(self, endian=">") -> bytes:
        return (
            struct.pack(endian + "h", self.type)
            + struct.pack(endian + "i", self.num_samples)
            + struct.pack(endian + "f", self.dwell)
            + struct.pack(endian + "f", self.delay)
        )

    @classmethod
    def from_struct(cls, data: SimpleNamespace) -> "PulseqADC":
        return cls(
            type=1,
            num_samples=data.num_samples,
            dwell=data.dwell,
            delay=data.delay,
        )


@dataclass
class PulseqTrig:
    type: int
    channel: int
    delay: float
    duration: float

    def to_bytes(self, endian=">") -> bytes:
        return (
            struct.pack(endian + "h", self.type)
            + struct.pack(endian + "i", self.channel)
            + struct.pack(endian + "f", self.delay)
            + struct.pack(endian + "f", self.duration)
        )

    @classmethod
    def from_struct(cls, data: SimpleNamespace) -> "PulseqTrig":
        return cls(
            type=1,
            channel=CHANNEL_ENUM[data.channel],
            delay=data.delay,
            duration=data.duration,
        )


class PulseqBlock:
    """Pulseq block structure."""

    def __init__(
        self,
        ID: int,
        rf: SimpleNamespace = None,
        gx: SimpleNamespace = None,
        gy: SimpleNamespace = None,
        gz: SimpleNamespace = None,
        adc: SimpleNamespace = None,
        trig: SimpleNamespace = None,
    ) -> "PulseqBlock":
        self.ID = ID
        args = [rf, gx, gy, gz, adc, trig]
        args = [arg for arg in args if arg is not None]
        self.duration = pp.calc_duration(*args)
        self.rf = PulseqRF.from_struct(rf) if rf else None
        self.gx = PulseqGrad.from_struct(gx) if gx else None
        self.gy = PulseqGrad.from_struct(gy) if gy else None
        self.gz = PulseqGrad.from_struct(gz) if gz else None
        self.adc = PulseqADC.from_struct(adc) if adc else None
        self.trig = PulseqTrig.from_struct(trig) if trig else None

    def to_bytes(self, endian=">") -> bytes:
        bytes_data = struct.pack(endian + "i", self.ID) + struct.pack(
            endian + "f", self.duration
        )

        # RF Event
        if self.rf:
            bytes_data += self.rf.to_bytes(endian)
        else:
            bytes_data += struct.pack(endian + "h", 0)

        # Gradient Events
        for grad in [self.gx, self.gy, self.gz]:
            if grad:
                bytes_data += grad.to_bytes(endian)
            else:
                bytes_data += struct.pack(endian + "h", 0)

        # ADC Event
        if self.adc:
            bytes_data += self.adc.to_bytes(endian)
        else:
            bytes_data += struct.pack(endian + "h", 0)

        # Trigger Event
        if self.trig:
            bytes_data += self.trig.to_bytes(endian)
        else:
            bytes_data += struct.pack(endian + "h", 0)

        return bytes_data


class Segment:
    """Ceq segment."""

    def __init__(self, segment_id: int, block_ids: list[int]):
        self.segment_id = segment_id
        self.n_blocks_in_segment = len(block_ids)
        self.block_ids = np.asarray(block_ids, dtype=np.int16)

    def to_bytes(self, endian=">") -> bytes:
        return (
            struct.pack(endian + "h", self.segment_id)
            + struct.pack(endian + "h", self.n_blocks_in_segment)
            + self.block_ids.astype(endian + "i2").tobytes()
        )


class Ceq:
    """CEQ structure."""

    def __init__(
        self,
        parent_blocks: list[PulseqBlock],
        loop: list[list],
        sections_edges: list[list[int]],
    ):
        loop = np.asarray(loop, dtype=np.float32)
        segments = _build_segments(loop, sections_edges)

        # build CEQ structure
        self.n_max = loop.shape[0]
        self.n_parent_blocks = len(parent_blocks)
        self.n_segments = len(segments)
        self.parent_blocks = parent_blocks
        self.segments = segments
        self.n_columns_in_loop_array = loop.shape[1] - 1  # discard "hasrot"
        self.loop = loop[:, :-1]
        self.max_b1 = _find_b1_max(parent_blocks)
        self.duration = _calc_duration(self.loop[:, 0], self.loop[:, 9])

    def to_bytes(self, endian=">") -> bytes:
        bytes_data = (
            struct.pack(endian + "i", self.n_max)
            + struct.pack(endian + "h", self.n_parent_blocks)
            + struct.pack(endian + "h", self.n_segments)
        )
        for block in self.parent_blocks:
            bytes_data += block.to_bytes(endian)
        for segment in self.segments:
            bytes_data += segment.to_bytes(endian)
        bytes_data += struct.pack(endian + "h", self.n_columns_in_loop_array)
        bytes_data += self.loop.astype(endian + "f4").tobytes()
        bytes_data += struct.pack(endian + "f", self.max_b1)
        bytes_data += struct.pack(endian + "f", self.duration)
        return bytes_data


# %% local subroutines
def _build_segments(loop, sections_edges):
    hasrot = np.ascontiguousarray(loop[:, -1]).astype(int)
    parent_block_id = np.ascontiguousarray(loop[:, 1]).astype(int) * hasrot

    # build section edges
    if not sections_edges:
        sections_edges = [0]
    sections_edges = np.stack((sections_edges, sections_edges[1:] + [-1]), axis=-1)

    # loop over sections and find segment definitions
    segment_id = np.zeros(loop.shape[0], dtype=np.float32)
    seg_definitions = []

    # fill sections from 0 to n-1
    n_sections = len(sections_edges)
    for n in range(n_sections - 1):
        section_start, section_end = sections_edges[n]
        _seg_definition = _autoseg.find_segment_definitions(
            parent_block_id[section_start:section_end]
        )
        _seg_definition = _autoseg.split_rotated_segments(_seg_definition)
        seg_definitions.extend(_seg_definition)

    # fill last section
    section_start = sections_edges[-1][0]
    _seg_definition = _autoseg.find_segment_definitions(parent_block_id[section_start:])
    _seg_definition = _autoseg.split_rotated_segments(_seg_definition)
    seg_definitions.extend(_seg_definition)

    # for each block, find the segment it belongs to
    for n in range(len(seg_definitions)):
        idx = _autoseg.find_segments(parent_block_id, seg_definitions[n])
        segment_id[idx] = n
    segment_id += 1  # segment 0 is reserved for pure delay
    loop[:, 0] = segment_id

    # now build segment fields
    n_segments = len(seg_definitions)
    segments = []
    for n in range(n_segments):
        segments.append(Segment(n + 1, seg_definitions[n]))

    return segments


def _find_b1_max(parent_blocks):
    return np.max(
        [
            max(abs(block.rf.wav.magnitude))
            for block in parent_blocks
            if block.rf is not None
        ]
    )


def _calc_duration(segment_id, block_duration):
    block_duration = block_duration.sum()

    # total segment ringdown
    n_seg_boundaries = (np.diff(segment_id) != 0).sum()
    seg_ringdown_duration = SEGMENT_RINGDOWN_TIME * n_seg_boundaries

    return block_duration + seg_ringdown_duration
