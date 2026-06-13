"""C1 smoke test: the package imports and exposes its version.

Real coverage arrives with the feature branches (settings/errors in C2, endpoints in C4+).
"""

from __future__ import annotations

from recalls_api import __version__


def test_version() -> None:
    assert __version__ == "0.1.0"
