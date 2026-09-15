"""Conversion of a Pulseq sequence into the scanner's segmented binary IR."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pypulseqpp as pp

from .._accelerators import require
from ._source import conversion_payload


def _scanner(system: pp.Opts) -> tuple[float, ...]:
    """Gyromagnetic ratio, field strength and the four rasters, in Hz/T, T and us."""
    return (
        float(system.gamma),
        float(system.B0),
        system.rf_raster_time * 1e6,
        system.grad_raster_time * 1e6,
        system.adc_raster_time * 1e6,
        system.block_duration_raster * 1e6,
    )


def cache_path(seq_path: Path | str, cache_ext: str = ".pseg") -> Path:
    """Return the cache file of a sequence: its last suffix replaced by ``cache_ext``."""
    return Path(seq_path).with_suffix(cache_ext)


def chain(seq_path: Path | str) -> list[Path]:
    """Return the files of the ``NextSequence`` chain starting at a sequence file, in play order.

    Raises
    ------
    ValueError
        If a file of the chain cannot be read, or the chain does not end.
    """
    return [Path(p) for p in require("chain")(str(seq_path))]


def convert(
    seq_path: Path | str,
    system: pp.Opts,
    *,
    vendor: int = 0,
    label_column_map: Sequence[int] = (0, 1, 2),
    cache_ext: str = ".pseg",
    verify_signature: bool = True,
) -> Path:
    """Segment a sequence file and write its IR cache beside it.

    The ``NextSequence`` chain starting at the file is read as the
    subsequences of one scan. An existing cache at the destination is
    replaced. RF vendor statistics are left at zero: ``vendor`` only tags the
    cache for the reader that loads it, which must be built for that vendor.

    Parameters
    ----------
    seq_path
        Text or binary Pulseq file.
    system
        Limits and rasters the scan is segmented under.
    vendor
        ``PULSEG_VENDOR_*`` code; 0 is vendor-neutral.
    label_column_map
        Pulseq label state indices filling the three ADC label columns:
        0 SLC, 1 PHS, 2 REP, 3 AVG, 4 SEG, 5 SET, 6 ECO, 7 PAR, 8 LIN, 9 ACQ.
    cache_ext
        Extension of the cache file, dot included.
    verify_signature
        Refuse a file whose signature is missing or does not match.

    Returns
    -------
    Path
        The cache file.

    Raises
    ------
    ValueError
        If the file cannot be read, verified or segmented.
    OSError
        If no cache was written.
    """
    seq_path = Path(seq_path)
    target = cache_path(seq_path, cache_ext)
    target.unlink(missing_ok=True)
    require("convert")(
        str(seq_path),
        *_scanner(system),
        int(vendor),
        list(label_column_map),
        cache_ext,
        verify_signature,
    )
    if not target.is_file():
        raise OSError(f"no cache was written for {seq_path}")
    return target


def convert_sequence(
    seq_path: Path | str,
    system: pp.Opts,
    *,
    vendor: int = 0,
    label_column_map: Sequence[int] = (0, 1, 2),
    cache_ext: str = ".pseg",
) -> Path:
    """Segment a sequence read through pypulseqpp and write its IR cache beside it.

    As :func:`convert`, reading the ``NextSequence`` chain with
    ``pypulseqpp.Sequence`` instead of a Pulseq parser of its own. An existing
    cache at the destination is replaced.

    Raises
    ------
    ValueError
        If a file of the chain cannot be read or segmented.
    OSError
        If no cache was written.
    """
    seq_path = Path(seq_path)
    target = cache_path(seq_path, cache_ext)
    target.unlink(missing_ok=True)
    payload = [conversion_payload(read_sequence(part)) for part in chain(seq_path)]
    require("convert_libraries")(
        payload,
        str(seq_path),
        *_scanner(system),
        int(vendor),
        list(label_column_map),
        cache_ext,
    )
    if not target.is_file():
        raise OSError(f"no cache was written for {seq_path}")
    return target


def read_sequence(path: Path | str) -> pp.Sequence:
    """Read one Pulseq file, text or binary, into a sequence."""
    sequence = pp.Sequence()
    sequence.read(Path(path))
    return sequence


def summary(
    seq_path: Path | str,
    system: pp.Opts,
    *,
    cache_ext: str | None = None,
    label_column_map: Sequence[int] = (0, 1, 2),
) -> dict[str, Any]:
    """Return the segmentation of a sequence: subsequences, segments and readouts.

    With ``cache_ext``, the cache beside the file is loaded instead of the file
    being parsed; this build loads only vendor-neutral caches, and only when the
    size recorded in the cache matches the file.

    Raises
    ------
    ValueError
        If the file cannot be parsed or the cache cannot be loaded.
    """
    seq_path = Path(seq_path)
    if cache_ext is None:
        return require("summary_from_parse")(
            str(seq_path), *_scanner(system), list(label_column_map)
        )
    return require("summary_from_cache")(
        str(cache_path(seq_path, cache_ext)), seq_path.stat().st_size
    )
