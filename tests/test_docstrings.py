"""Run every docstring example in the installed package.

Modules are collected by importing the package, not with ``--doctest-modules``
over ``src/``, which collides with a non-editable install.
"""

import doctest
import importlib
import pkgutil

import pytest

import pulserver as package


def _modules():
    yield package
    for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        yield importlib.import_module(info.name)


@pytest.mark.parametrize("module", list(_modules()), ids=lambda module: module.__name__)
def test_every_docstring_example_runs(module, capsys):
    results = doctest.testmod(
        module, verbose=False, report=False, optionflags=doctest.ELLIPSIS
    )
    captured = capsys.readouterr()
    assert results.failed == 0, captured.out
