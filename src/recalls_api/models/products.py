"""Product-search response model (01 — Mart 2 / mart_product_search).

``rank`` is populated only on the keyword (FTS) path; ``upc_is_recall_level`` is a constant honesty
flag (the per-product ``upc`` column is NULL today, so UPC search matches the recall-level
``recall_product_upcs`` array via containment).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from recalls_api.models.common import Source, flatten_upcs


class ProductSearchHit(BaseModel):
    # protected_namespaces=() so the `model_year` field doesn't trip Pydantic's `model_` guard.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    recall_product_id: str
    recall_event_id: str
    source: Source
    source_recall_id: str
    product_name: str | None = None
    product_description: str | None = None
    model: str | None = None
    type: str | None = Field(default=None, examples=["Frozen ready-to-eat"])
    model_year: str | int | None = Field(default=None, examples=[2019])
    hin: str | None = None
    upc: str | None = Field(
        default=None, description="Product-grain UPC; currently null for all rows."
    )
    recall_title: str | None = None
    classification: str | None = None
    risk_level: str | None = None
    published_at: datetime
    url: str | None = None
    is_active: bool | None = None
    firm_name: str | None = None
    recall_product_upcs: list[str] = Field(
        default_factory=list, description="Recall-level UPCs, flattened from gold's object array."
    )
    rank: float | None = Field(
        default=None, description="Relevance; present only for keyword (q) search."
    )
    upc_is_recall_level: Literal[True] = Field(
        default=True,
        description="UPC matches are recall-level (recall_product_upcs), not product-grain.",
    )

    @field_validator("recall_product_upcs", mode="before")
    @classmethod
    def _flatten_recall_upcs(cls, v: Any) -> Any:
        # Gold stores UPCs as [{"upc": "X"}] objects; unwrap to bare strings (and None -> []).
        return flatten_upcs(v)
