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
from recalls_api.models.descriptions import D_CLASSIFICATION


class ProductSearchHit(BaseModel):
    # protected_namespaces=() so the `model_year` field doesn't trip Pydantic's `model_` guard.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    recall_product_id: str = Field(
        description=(
            "Stable, opaque id for one recalled product line (unique, never null). Also the "
            "pagination cursor anchor. Sources: all five."
        )
    )
    recall_event_id: str = Field(
        description=(
            "Id of the parent recall event (links to `GET /recalls/{source}/{recall_id}`). Several "
            "products can share one recall for CPSC, FDA, and NHTSA; one-to-one for USDA and USCG. "
            "Sources: all five."
        )
    )
    source: Source = Field(
        description="The issuing agency: CPSC, FDA, USDA, NHTSA, or USCG. Always present."
    )
    source_recall_id: str = Field(
        description=(
            "Each agency's own recall identifier, paired with `source` for the public key. For "
            "CPSC, USDA, NHTSA, and USCG it is recall-level; for FDA it is the product id, and the "
            "FDA recall id is in `recall_event_id`. Always present."
        )
    )
    product_name: str | None = Field(
        default=None,
        description=(
            "The product's name. Varies by agency: CPSC product name, USCG boat model name, FDA "
            "product description, USDA recall title, NHTSA component description. May be null for "
            "some rows. Sources: all five."
        ),
    )
    product_description: str | None = Field(
        default=None,
        description=(
            "A free-text description of the product. Varies by agency: FDA repeats the product "
            "name, USDA gives a product-items blob (about 40% null), NHTSA the component "
            "description, USCG a short defect note (about 25 characters). Sources: FDA, USDA, "
            "NHTSA, USCG (null for CPSC, which has none)."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "Product model identifier, used by the `model` exact-match lookup. Populated only for "
            "NHTSA (e.g. 'F-150'); null for the others (USCG's boat name is in `product_name`). "
            "Sources: NHTSA only."
        ),
    )
    type: str | None = Field(
        default=None,
        examples=["Frozen ready-to-eat"],
        description=(
            "Each agency's own product category code or label (not standardized across agencies): "
            "FDA commodity (Devices, Food, Drugs, Veterinary, Biologics, Cosmetics); USDA "
            "processing category; NHTSA recall-type code (V/T/E/C/I/X); USCG a numeric boat-type "
            "code; CPSC a free-text product type. Compare only within one agency; null where the "
            "agency provides no type. Sources: all five."
        ),
    )
    model_year: str | int | None = Field(
        default=None,
        examples=[2019],
        description=(
            "Model year of the recalled item, as text. Populated only for NHTSA and USCG (varied "
            "formats, about 32% null for USCG); null for CPSC, FDA, and USDA. Kept as text because "
            "USCG values are not always numeric. Sources: NHTSA, USCG."
        ),
    )
    hin: str | None = Field(
        default=None,
        description=(
            "USCG Hull Identification Number for the recalled boat (the boating equivalent of a "
            "VIN). USCG only; only about 54% of USCG products carry a real HIN. Sources: USCG only."
        ),
    )
    recall_title: str | None = Field(
        default=None,
        description=(
            "Headline of the recall this product belongs to. CPSC and USDA provide one directly; "
            "for FDA, NHTSA, and USCG it is built from the recall id and firm or model name. "
            "Always present. Sources: all five."
        ),
    )
    classification: str | None = Field(default=None, description=D_CLASSIFICATION)
    risk_level: str | None = Field(
        default=None,
        description=(
            "USDA's health-risk label, mapping directly to its classification (e.g. 'High - Class "
            "I'). Sources: USDA only (null for the others)."
        ),
    )
    published_at: datetime = Field(
        description=(
            "When the recall was last published or updated. Always present, and the default sort "
            "key. Sources: all five."
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
            "Whether the recall is still active (from the FDA, USDA, or USCG status). Null for "
            "CPSC and NHTSA. Sources: FDA, USDA, USCG."
        ),
    )
    firm_name: str | None = Field(
        default=None,
        description=(
            "The recall's main firm, chosen by role priority (manufacturer, then establishment, "
            "filer, importer, distributor). May be null when no firm is matched. Sources: all "
            "five."
        ),
    )
    recall_product_upcs: list[str] = Field(
        default_factory=list,
        description=(
            "Recall-level UPC codes (shared across the whole recall and repeated on each product "
            "row; this is what UPC search matches). Empty list when absent. Populated only for "
            "CPSC and sparse there (about 5% of CPSC recalls); empty for the others. Sources: CPSC "
            "only."
        ),
    )
    rank: float | None = Field(
        default=None,
        description=(
            "Search relevance score (higher is more relevant). Present only on the keyword (`q`) "
            "path; null for `hin`, `model`, and `upc` lookups. Scores are not comparable between "
            "queries. Computed per request. Applies to all sources."
        ),
    )
    upc_is_recall_level: Literal[True] = Field(
        default=True,
        description=(
            "Always true. A reminder that UPC search matches at the recall level (currently "
            "CPSC-sourced and sparse), not at the individual-product level. Applies to all "
            "sources."
        ),
    )

    @field_validator("recall_product_upcs", mode="before")
    @classmethod
    def _flatten_recall_upcs(cls, v: Any) -> Any:
        # Gold stores UPCs as [{"upc": "X"}] objects; unwrap to bare strings (and None -> []).
        return flatten_upcs(v)
