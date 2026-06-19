"""recalls-api — open, read-only FastAPI serving layer over the recalls gold marts."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: pyproject.toml's [project].version, read back from installed package
    # metadata (mirrors the pipeline repo). Bump pyproject.toml only — this cascades to FastAPI's
    # OpenAPI `version`, the `/health` body, and the cache ETag.
    __version__ = version("consumer-product-recalls-api")
except PackageNotFoundError:  # raw source tree, no install — degrade instead of crashing
    __version__ = "0.0.0"
