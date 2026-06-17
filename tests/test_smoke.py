"""C1 smoke test: the package imports and exposes its version.

Real coverage arrives with the feature branches (settings/errors in C2, endpoints in C4+).
"""

from __future__ import annotations

from importlib.metadata import version

from recalls_api import __version__


def test_version_is_single_sourced_from_pyproject() -> None:
    # __version__ is read from installed package metadata (pyproject.toml is the single source),
    # so assert it tracks that — never hardcode a literal here (that would force an edit per bump).
    assert __version__ == version("consumer-product-recalls-api")
    assert __version__ != "0.0.0"  # the PackageNotFoundError fallback should not be in play here
