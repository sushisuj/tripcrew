"""Sphinx configuration for tripcrew docs, set up for Read the Docs.

Mirrors the Constellate docs setup (same Sphinx + RTD pattern, same reason:
get the skeleton right before there's a lot of content to migrate later).
"""

project = "tripcrew"
copyright = "2026, Sujan"
author = "Sujan"
release = "0.0.1"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
