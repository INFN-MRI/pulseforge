"""The package imports and reports a version."""

import pulserver


def test_the_package_reports_a_version():
    assert isinstance(pulserver.__version__, str)
    assert pulserver.__version__
