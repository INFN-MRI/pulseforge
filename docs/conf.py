"""Sphinx configuration for the pulserver documentation."""

from __future__ import annotations

import logging

project = "pulserver"
copyright = "2024-2026, Matteo Cencini"  # noqa: A001
author = "Matteo Cencini"

extensions = [
    "sphinx_copybutton",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["build", "Thumbs.db", ".DS_Store"]

myst_enable_extensions = ["colon_fence", "deflist", "dollarmath", "linkify"]
myst_footnote_transition = False

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_typehints = "none"
autodoc_preserve_defaults = True

napoleon_numpy_docstring = True
napoleon_custom_sections = [("Attributes", "params_style")]

intersphinx_timeout = 10
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
}


class _InventoryOutageFilter(logging.Filter):
    """Drop the untyped warning intersphinx logs when an inventory is unreachable.

    The build runs under ``-W`` and ``suppress_warnings`` cannot name this
    message, so an outage at another project's documentation host would fail it.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "failed to reach any of the inventories" not in record.getMessage()


def setup(app):
    for handler in logging.getLogger("sphinx").handlers:
        handler.filters.insert(0, _InventoryOutageFilter())


html_theme = "sphinx_book_theme"
html_theme_options = {
    "repository_url": "https://github.com/pulserver/pulserver",
    "repository_branch": "orchestrator",
    "path_to_docs": "docs",
    "use_repository_button": True,
    "use_issues_button": True,
    "home_page_in_toc": True,
}
html_title = "pulserver"
