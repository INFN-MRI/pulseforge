"""Every docstring example runs, against the installed package.

The examples are the documentation, so one that has drifted is a broken one.
They are collected from the package as imported rather than from the source
tree, so this says the same thing about an editable checkout and about an
installed wheel.
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
