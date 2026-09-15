"""Design calls, run in worker processes."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import pypulseqpp as pp

from ..design import ScannerSequence, load_plugin
from ..protocol import Parameter, Validation


@lru_cache(maxsize=32)
def _cached(path: str, mtime_ns: int) -> ScannerSequence:  # noqa: ARG001 -- part of the key
    return load_plugin(Path(path))


def _plugin(path: str) -> ScannerSequence:
    """Return the plugin at ``path``, imported again when the file changed."""
    return _cached(path, Path(path).stat().st_mtime_ns)


def listing(path: str) -> dict[str, Parameter]:
    return _plugin(path).listing()


def validate(
    path: str, limits: Mapping[str, Any], request: Mapping[str, Any]
) -> Validation:
    return _plugin(path).validate(pp.Opts(**limits), request)


def generate(
    path: str, limits: Mapping[str, Any], request: Mapping[str, Any], directory: str
) -> tuple[Validation, list[str]]:
    return _plugin(path).generate(pp.Opts(**limits), request, Path(directory))
