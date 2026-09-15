"""Shared fixtures.

Every numerical check that can run on both devices is parametrised over
``device``; the CUDA leg skips when no device is present.
"""

import pytest


def _cuda_available():
    try:
        import torch
    except ImportError:
        return False
    return torch.cuda.is_available()


@pytest.fixture(
    params=[
        "cpu",
        pytest.param(
            "cuda",
            marks=[
                pytest.mark.cuda,
                pytest.mark.skipif(not _cuda_available(), reason="no CUDA device"),
            ],
        ),
    ]
)
def device(request):
    """Run the test on each device this machine actually has."""
    return request.param
