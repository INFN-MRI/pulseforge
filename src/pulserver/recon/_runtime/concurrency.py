"""Number of concurrent reconstructions the host memory allows."""

__all__ = ["compute_max_concurrent"]

import logging
import math
import os

_DEFAULT_PER_RECON_GB: float = 48.0
_DEFAULT_HEADROOM_FRACTION: float = 0.8


def _available_ram_gb() -> float:
    """Available memory in GiB from ``psutil``, else ``sysconf``; 0.0 when neither answers."""
    try:
        import psutil  # type: ignore[import-untyped]

        return psutil.virtual_memory().available / (1024**3)
    except ImportError:
        pass
    try:
        page_size: int = os.sysconf("SC_PAGE_SIZE")
        avail_pages: int = os.sysconf("SC_AVPHYS_PAGES")
        return page_size * avail_pages / (1024**3)
    except (AttributeError, ValueError, OSError):
        return 0.0


def compute_max_concurrent(
    per_recon_gb: float = _DEFAULT_PER_RECON_GB,
    headroom_fraction: float = _DEFAULT_HEADROOM_FRACTION,
    override: int | None = None,
) -> int:
    """Return how many reconstructions may run at once.

    ``floor(available * headroom_fraction / per_recon_gb)``, at least 1, and 1
    when available memory cannot be read.

    Parameters
    ----------
    per_recon_gb
        Memory budgeted for one reconstruction, in GiB.
    headroom_fraction
        Fraction of available memory given to reconstructions.
    override
        Returned as is when positive.
    """
    if override is not None and override > 0:
        logging.info("MRD concurrency limit: %d slot(s)  [manual override]", override)
        return override

    avail_gb = _available_ram_gb()
    if avail_gb <= 0.0:
        logging.warning(
            "Could not determine available RAM — defaulting to 1 concurrent recon slot"
        )
        return 1

    slots = max(1, math.floor(avail_gb * headroom_fraction / per_recon_gb))
    logging.info(
        "MRD concurrency limit: %d slot(s)  "
        "(%.1f GiB available x %.0f%% headroom / %.1f GiB per recon)",
        slots,
        avail_gb,
        headroom_fraction * 100,
        per_recon_gb,
    )
    return slots
