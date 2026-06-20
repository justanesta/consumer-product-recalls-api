"""Cross-cutting response primitives: the ``Source`` enum, the ``Page[T]`` envelope, ``FirmRef``,
and the health models. Resource models (recalls/products/firms) live in sibling modules.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def flatten_upcs(v: Any) -> Any:
    """Normalize a gold UPC array to plain strings.

    Gold stores recall-level UPCs as an array of objects — ``[{"upc": "012345678905"}]`` (lowercase
    key) — not bare strings. This unwraps each ``{"upc": x}`` element to ``x`` so the response field
    stays ``list[str]``. Tolerant of the future flattened shape (bare strings pass through) and of a
    NULL array (-> ``[]``), so it is safe across the pending cross-repo gold change.
    """
    if v is None:
        return []
    if isinstance(v, list):
        return [e["upc"] if isinstance(e, dict) and "upc" in e else e for e in v]
    return v


class Source(StrEnum):
    """The issuing agency: CPSC, FDA, USDA, NHTSA, or USCG."""

    CPSC = "CPSC"
    FDA = "FDA"
    USDA = "USDA"
    NHTSA = "NHTSA"
    USCG = "USCG"


class DistributionScope(StrEnum):
    """How widely a product was distributed: Nationwide, Regional, International, or Unspecified."""

    NATIONWIDE = "Nationwide"
    REGIONAL = "Regional"
    UNSPECIFIED = "Unspecified"
    INTERNATIONAL = "International"


class Page[T](BaseModel):
    """A page of results. Pass ``next_cursor`` back as ``cursor`` to fetch the next page."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    next_cursor: str | None = Field(default=None, examples=["eyJ2IjpbIjIwMjYtMDEtMDEiLCJhYmMiXX0"])
    limit: int = Field(examples=[25])
    total: int | None = Field(
        default=None, description="Only when with_total=true.", examples=[None]
    )


class FirmRef(BaseModel):
    """One firm tied to a recall; ``firm_id`` links to ``GET /firms/{firm_id}``."""

    model_config = ConfigDict(from_attributes=True)

    firm_id: str = Field(
        examples=["7d2c1e5b8a40f0a9f4c7e3a1e3a1c6f2"],
        description="A firm's id; use with `GET /firms/{firm_id}`.",
    )
    name: str = Field(examples=["Acme Corporation"], description="The firm's cleaned-up name.")
    # role / match_confidence are closed UPSTREAM but surfaced as free strings: the API does not let
    # clients filter on them and must not break if the pipeline adds a value.
    role: str = Field(
        examples=["manufacturer"],
        description=(
            "Role this firm played on the recall (manufacturer/importer/distributor for CPSC, "
            "establishment for FDA/USDA, filer/manufacturer for NHTSA, manufacturer for USCG)."
        ),
    )
    match_confidence: str = Field(
        examples=["exact_name"],
        description="How this firm was matched to the recall (e.g. exact_name, fei_exact).",
    )


class Health(BaseModel):
    """Liveness body."""

    status: Literal["ok"] = "ok"
    version: str = Field(examples=["0.1.0"])


class DbHealth(BaseModel):
    """Readiness body, returned only when the database is reachable."""

    status: Literal["ok"] = "ok"
    database: Literal["reachable"] = "reachable"
