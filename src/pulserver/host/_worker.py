"""Design and conversion calls, run in worker processes."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import pypulseqpp as pp

from .. import ir
from ..design import ScannerSequence, load_plugin
from ..protocol import Parameter, Validation

_IR_OPTIONS = ("ir_vendor", "ir_label_column_map", "ir_cache_ext")


@lru_cache(maxsize=32)
def _cached(path: str, mtime_ns: int) -> ScannerSequence:  # noqa: ARG001 -- part of the key
    return load_plugin(Path(path))


def _plugin(path: str) -> ScannerSequence:
    """Return the plugin at ``path``, imported again when the file changed."""
    return _cached(path, Path(path).stat().st_mtime_ns)


def split_limits(limits: Mapping[str, Any]) -> tuple[pp.Opts, dict[str, Any]]:
    """Separate a session's limits into scanner limits and IR conversion options.

    Keys starting with ``ir_`` are conversion options: ``ir_vendor``,
    ``ir_label_column_map`` (three integers separated by spaces) and
    ``ir_cache_ext``. The other keys are ``pypulseqpp.Opts`` keyword arguments.

    Raises
    ------
    ValueError
        If an ``ir_`` key is not a conversion option.
    """
    unknown = [k for k in limits if k.startswith("ir_") and k not in _IR_OPTIONS]
    if unknown:
        raise ValueError(f"not IR conversion options: {unknown}")
    system = pp.Opts(**{k: v for k, v in limits.items() if not k.startswith("ir_")})
    options: dict[str, Any] = {}
    if "ir_vendor" in limits:
        options["vendor"] = int(limits["ir_vendor"])
    if "ir_label_column_map" in limits:
        values = str(limits["ir_label_column_map"]).split()
        options["label_column_map"] = tuple(int(v) for v in values)
    if "ir_cache_ext" in limits:
        options["cache_ext"] = str(limits["ir_cache_ext"])
    return system, options


def listing(path: str) -> dict[str, Parameter]:
    return _plugin(path).listing()


def validate(
    path: str, limits: Mapping[str, Any], request: Mapping[str, Any]
) -> Validation:
    return _plugin(path).validate(split_limits(limits)[0], request)


def generate(
    path: str, limits: Mapping[str, Any], request: Mapping[str, Any], directory: str
) -> tuple[Validation, list[str], str | None]:
    """Design into ``directory`` and convert the result.

    The cache file name is ``None`` for an invalid request, which writes nothing.
    """
    system, options = split_limits(limits)
    validation, paths = _plugin(path).generate(system, request, Path(directory))
    if not paths:
        return validation, paths, None
    return validation, paths, ir.convert(paths[0], system, **options).name


def chain(first: str) -> list[str]:
    return [str(path) for path in ir.chain(first)]


def convert(limits: Mapping[str, Any], seq_path: str) -> str:
    system, options = split_limits(limits)
    return ir.convert(seq_path, system, **options).name
