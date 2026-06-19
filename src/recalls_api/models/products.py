"""Product-search response model (01 — Mart 2 / mart_product_search).

``rank`` is populated only on the keyword (FTS) path; ``upc_is_recall_level`` is a constant honesty
flag. The gold mart carries a per-product ``upc`` column but it is NULL for every row of every
source (a forward-looking placeholder), so the API no longer projects it; UPC search matches the
recall-level ``recall_product_upcs`` array via containment.

Per-field ``description=`` strings are the API's machine-readable data dictionary; the trailing
``Sources: …`` clause is the per-source provenance tag (see provenance-analysis-2026-06-17.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from recalls_api.models.common import Source, flatten_upcs


class ProductSearchHit(BaseModel):
    # protected_namespaces=() so the `model_year` field doesn't trip Pydantic's `model_` guard.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    recall_product_id: str = Field(
        description=(
            "Stable surrogate primary key for one recalled product line, reused verbatim from "
            "silver (md5, unique, never null). Also the keyset cursor anchor. Sources: all five."
        )
    )
    recall_event_id: str = Field(
        description=(
            "Surrogate key of the parent recall event (md5; joins to GET "
            "/recalls/{source}/{recall_id}). Many products can share one event for CPSC/FDA/NHTSA; "
            "1:1 for USDA/USCG. Sources: all five."
        )
    )
    source: Source = Field(
        description="Originating data source: CPSC, FDA, USDA, NHTSA, USCG. Always populated."
    )
    source_recall_id: str = Field(
        description=(
            "Source-native recall identifier, paired with source for the public natural key. "
            "Recall-grain for CPSC/USDA/NHTSA/USCG; for FDA it is the product id (product-grain) — "
            "the FDA recall-event id is recall_event_id. Always populated."
        )
    )
    product_name: str | None = Field(
        default=None,
        description=(
            "Product name for this recalled product. Source-dependent: CPSC = product name; USCG = "
            "boat model name; FDA = the product DESCRIPTION text; USDA = the recall TITLE; NHTSA = "
            "the COMPONENT description. May be null for some rows. Sources: all five."
        ),
    )
    product_description: str | None = Field(
        default=None,
        description=(
            "Free-text description of the product. Source-dependent: FDA = the product description "
            "(same value as product_name); USDA = the product-items blob (~40% null); NHTSA = the "
            "component description; USCG = a short defect/problem note (~25 chars). Sources: FDA, "
            "USDA, NHTSA, USCG (null for CPSC, whose per-product description is absent at source)."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "Product model identifier for exact-match lookup (btree-indexed). Populated only for "
            "NHTSA (MODELTXT, e.g. 'F-150'); null for CPSC, FDA, USDA, USCG (USCG's boat name is "
            "in product_name). Sources: NHTSA only."
        ),
    )
    type: str | None = Field(
        default=None,
        examples=["Frozen ready-to-eat"],
        description=(
            "Source-specific product category code/label (NOT harmonized across sources): FDA = "
            "commodity (Devices/Food/Drugs/Veterinary/Biologics/Cosmetics); USDA = FSIS processing "
            "category; NHTSA = recall-type code (V/T/E/C/I/X); USCG = a numeric boat-type code; "
            "CPSC = a free-text product type. Compare only within a single source; null where the "
            "source provides no type. Sources: all five."
        ),
    )
    model_year: str | int | None = Field(
        default=None,
        examples=[2019],
        description=(
            "Model year of the recalled item (text). Populated only for NHTSA (YEARTXT, with the "
            "'9999' sentinel nulled) and USCG (varied formats; ~32% null); null for CPSC, FDA, "
            "USDA. Kept as text because USCG values are not uniformly numeric. Sources: NHTSA, "
            "USCG."
        ),
    )
    hin: str | None = Field(
        default=None,
        description=(
            "USCG Hull Identification Number for the recalled boat (the boating analog of a "
            "VIN/UPC; btree-indexed). USCG-only — null for CPSC, FDA, USDA, NHTSA; only ~54% of "
            "USCG products carry a real HIN. Sources: USCG only."
        ),
    )
    recall_title: str | None = Field(
        default=None,
        description=(
            "Headline of the recall this product belongs to. Native title for CPSC/USDA; "
            "synthesized '<recall-id> — <firm/model>' for FDA/NHTSA/USCG. Always populated. "
            "Sources: all five."
        ),
    )
    classification: str | None = Field(
        default=None,
        description=(
            "Recall severity/hazard classification in the source's native vocabulary (FDA 1/2/3, "
            "NC; USDA Class I/II/III, Public Health Alert; USCG H/L/M/S). NOT normalized across "
            "sources. Sources: FDA, USDA, USCG (null for CPSC/NHTSA)."
        ),
    )
    risk_level: str | None = Field(
        default=None,
        description=(
            "USDA health-risk label derived 1:1 from the USDA classification (e.g. 'High - Class "
            "I'). Sources: USDA only (null for CPSC/FDA/NHTSA/USCG)."
        ),
    )
    published_at: datetime = Field(
        description=(
            "Publication / last-published timestamp of the recall (always present; the canonical "
            "sort key). Sources: all five."
        )
    )
    url: str | None = Field(
        default=None,
        description=(
            "Agency detail-page URL for the recall. Sources: CPSC, USDA, USCG (null for FDA/NHTSA)."
        ),
    )
    is_active: bool | None = Field(
        default=None,
        description=(
            "Conformed tri-state flag for whether the recall is still active (from the "
            "FDA/USDA/USCG lifecycle). Sources: FDA, USDA, USCG (null for CPSC/NHTSA)."
        ),
    )
    firm_name: str | None = Field(
        default=None,
        description=(
            "Primary display firm for the recall — the canonical name of the highest-priority firm "
            "by role (manufacturer > establishment > filer > importer > distributor). May be null "
            "when no firm resolves. Sources: all five."
        ),
    )
    recall_product_upcs: list[str] = Field(
        default_factory=list,
        description=(
            "Recall-level UPC codes (recall-event grain, denormalized onto each product row; this "
            "is what UPC search matches via containment). Gold stores them as [{upc:…}] objects; "
            "the API flattens to bare strings ([] when absent). Populated only for CPSC and sparse "
            "there (~5% of CPSC recalls); empty for FDA/USDA/NHTSA/USCG. Sources: CPSC only."
        ),
    )
    rank: float | None = Field(
        default=None,
        description=(
            "Cover-density full-text relevance (ts_rank_cd over the product search_vector). "
            "Present only on the keyword (q) path; null for hin/model/upc lookups. Higher is more "
            "relevant, but scores are not comparable across queries. Computed per request, not "
            "stored. Source-independent."
        ),
    )
    upc_is_recall_level: Literal[True] = Field(
        default=True,
        description=(
            "Constant True honesty flag: UPC search is recall-level (containment over "
            "recall_product_upcs, currently CPSC-sourced and sparse), not product-grain. The "
            "per-product upc column is null for every source. Always True; source-independent."
        ),
    )

    @field_validator("recall_product_upcs", mode="before")
    @classmethod
    def _flatten_recall_upcs(cls, v: Any) -> Any:
        # Gold stores UPCs as [{"upc": "X"}] objects; unwrap to bare strings (and None -> []).
        return flatten_upcs(v)
