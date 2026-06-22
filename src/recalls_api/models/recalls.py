"""Recall response models: ``RecallSummary`` (list subset) and ``RecallDetail`` (full wide row).

Field names equal the ``mart_recall_summary`` column labels (01 — Mart 1) so a Core ``RowMapping``
validates 1:1. jsonb rollups the mart leaves un-coalesced (NULL when empty) become ``[]``.

Per-field ``description=`` strings are the API's machine-readable data dictionary (the OpenAPI SSOT;
see provenance-analysis-2026-06-17.md). The trailing ``Sources: …`` clause is the per-source
provenance tag; shared summary-field descriptions live in ``_D_*`` constants so the same column is
documented identically on ``RecallSummary`` and ``RecallDetail``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from recalls_api.models.common import FirmRef, Source, flatten_upcs
from recalls_api.models.descriptions import D_CLASSIFICATION

# --- Shared descriptions for the summary-subset columns (identical on Summary & Detail) ---
_D_RECALL_EVENT_ID = (
    "Stable, opaque id for one recall event; it does not change between data refreshes. This is "
    "not the agency's own recall number. For the human-facing key, pair `source` with "
    "`source_recall_id`. Sources: all five."
)
_D_SOURCE = "The issuing agency: CPSC, FDA, USDA, NHTSA, or USCG. Always present."
_D_SOURCE_RECALL_ID = (
    "Each agency's own recall identifier; its form varies by agency (e.g. CPSC recall number, FDA "
    "event id, USDA's DDD-YYYY number, NHTSA campaign number, USCG recall number). Pair with "
    "`source` for a globally unique key. Always present."
)
_D_TITLE = (
    "The recall's headline. CPSC and USDA provide one directly; for FDA, NHTSA, and USCG (which "
    "have none) it is built from the recall id and the firm or model name. Effectively always "
    "present."
)
_D_URL = (
    "Link to the recall's public detail page. Sources: CPSC, USDA, USCG (null for FDA and NHTSA, "
    "which don't publish a per-recall page)."
)
_D_ANNOUNCED_AT = (
    "When the recall was first announced or initiated. Null for about 20 FDA recalls that have no "
    "reliable announcement date; use `event_date` (or `published_at`) when you need a date that is "
    "always present. Filterable via `announced_after`/`announced_before`. Sources: all five."
)
_D_PUBLISHED_AT = (
    "When the recall was last published or updated — always present. For NHTSA this is really a "
    "record-creation date, since NHTSA does not publish a last-modified date. Filterable via "
    "`published_after`/`published_before`. This was the default sort key until the feed moved to "
    "`event_date` (announce-recency); it is still returned and filterable. Sources: all five."
)
_D_EVENT_DATE = (
    "The recall's effective date for the newest-first feed: its announcement date when known, "
    "falling back to `published_at` for the few recalls with no announcement date. Always present, "
    "and the key the list is sorted and paginated on. Equals `announced_at` whenever that is set. "
    "Sources: all five."
)
# classification is shared across recalls/products/stats, centralized in models.descriptions so the
# USCG H/L/M/S caveat can't drift across the three modules.
_D_CLASSIFICATION = D_CLASSIFICATION
_D_RISK_LEVEL = (
    "USDA's health-risk label, which maps directly to its classification (e.g. 'High - Class I', "
    "'Low - Class II', 'Marginal - Class III', 'Public Health Alert'). Sources: USDA only (null "
    "for the others)."
)
_D_LIFECYCLE_STATUS = (
    "The recall's status in each agency's own words (FDA: Ongoing/Completed/Terminated; USDA: "
    "Active Recall/Closed Recall/Public Health Alert; USCG: Open/Closed). Not standardized across "
    "agencies; see `is_active` for a single yes/no. Sources: FDA, USDA, USCG (null for CPSC/NHTSA)."
)
_D_IS_ACTIVE = (
    "Whether the recall is still active, based on each agency's status (a USDA Public Health Alert "
    "counts as active). Null for CPSC and NHTSA, which don't track a status, so they match neither "
    "true nor false. Sources: FDA, USDA, USCG."
)
_D_REASON_CATEGORY = (
    "USDA's categorized recall reasons, comma-joined (e.g. 'Unreported Allergens, Misbranding'). "
    "Sources: USDA only; for the other agencies the reason is free text in `recall_reason`."
)
_D_DISTRIBUTION_SCOPE = (
    "How widely the product was distributed, always present: Nationwide, International, Regional, "
    "or Unspecified. Derived from distribution text for FDA and USDA; CPSC and USCG default to "
    "Unspecified, NHTSA to Nationwide. Sources: all five."
)
_D_PRIMARY_FIRM_NAME = (
    "The recall's main firm, chosen by role priority (manufacturer, then establishment, filer, "
    "importer, distributor, then alphabetical). Null only when no firm could be matched. Sources: "
    "all five."
)
_D_FIRM_COUNT = (
    "Number of distinct firms linked to this recall across all roles. A firm with several roles "
    "counts once, so this can be less than the number of entries in `firms`. 0 when none matched. "
    "Sources: all five."
)
_D_PRODUCT_COUNT = (
    "Number of distinct products on this recall. CPSC, FDA, and NHTSA can have several; USDA and "
    "USCG always have one. Never null. Sources: all five."
)
_D_HAS_BEEN_EDITED = (
    "True if the pipeline has spotted at least one meaningful change to a tracked field (recall "
    "reason, classification, status, title, or termination date) since it began tracking this "
    "recall. It is evidence of an observed edit, not an official agency amendment, and it carries "
    "no date. Present for all sources."
)


class RecallSummary(BaseModel):
    """A recall as it appears in list results (the commonly used fields, not the full record)."""

    model_config = ConfigDict(from_attributes=True)

    recall_event_id: str = Field(description=_D_RECALL_EVENT_ID)
    source: Source = Field(description=_D_SOURCE)
    source_recall_id: str = Field(description=_D_SOURCE_RECALL_ID, examples=["24-001"])
    title: str | None = Field(
        default=None, description=_D_TITLE, examples=["Acme Toaster Fire Hazard"]
    )
    url: str | None = Field(default=None, description=_D_URL)
    announced_at: datetime | None = Field(default=None, description=_D_ANNOUNCED_AT)
    published_at: datetime = Field(description=_D_PUBLISHED_AT)
    event_date: datetime = Field(description=_D_EVENT_DATE)
    classification: str | None = Field(
        default=None, description=_D_CLASSIFICATION, examples=["Class II"]
    )
    risk_level: str | None = Field(
        default=None, description=_D_RISK_LEVEL, examples=["Low - Class II"]
    )
    lifecycle_status: str | None = Field(default=None, description=_D_LIFECYCLE_STATUS)
    is_active: bool | None = Field(default=None, description=_D_IS_ACTIVE)
    reason_category: str | None = Field(default=None, description=_D_REASON_CATEGORY)
    distribution_scope: str = Field(description=_D_DISTRIBUTION_SCOPE, examples=["Nationwide"])
    primary_firm_name: str | None = Field(default=None, description=_D_PRIMARY_FIRM_NAME)
    firm_count: int = Field(default=0, description=_D_FIRM_COUNT)
    product_count: int = Field(default=0, description=_D_PRODUCT_COUNT)
    has_been_edited: bool = Field(default=False, description=_D_HAS_BEEN_EDITED)


class RecallSearchHit(RecallSummary):
    """A recall list item plus a search relevance ``rank`` (from ``GET /recalls/search``)."""

    rank: float = Field(
        description=(
            "Search relevance score (higher is more relevant), weighted toward title, then brand, "
            "cause, and harm. Scores are not comparable between different queries. Computed per "
            "request; present only on `/recalls/search`."
        )
    )


class RecallDetail(BaseModel):
    """A recall's full record: list fields, narrative, geography, lifecycle, and related lists."""

    model_config = ConfigDict(from_attributes=True)

    # identity / summary subset (descriptions shared with RecallSummary via _D_* constants)
    recall_event_id: str = Field(description=_D_RECALL_EVENT_ID)
    source: Source = Field(description=_D_SOURCE)
    source_recall_id: str = Field(description=_D_SOURCE_RECALL_ID)
    title: str | None = Field(default=None, description=_D_TITLE)
    url: str | None = Field(default=None, description=_D_URL)
    announced_at: datetime | None = Field(default=None, description=_D_ANNOUNCED_AT)
    published_at: datetime = Field(description=_D_PUBLISHED_AT)
    event_date: datetime = Field(description=_D_EVENT_DATE)
    classification: str | None = Field(default=None, description=_D_CLASSIFICATION)
    risk_level: str | None = Field(default=None, description=_D_RISK_LEVEL)
    lifecycle_status: str | None = Field(default=None, description=_D_LIFECYCLE_STATUS)
    is_active: bool | None = Field(default=None, description=_D_IS_ACTIVE)
    reason_category: str | None = Field(default=None, description=_D_REASON_CATEGORY)
    distribution_scope: str = Field(description=_D_DISTRIBUTION_SCOPE)
    primary_firm_name: str | None = Field(default=None, description=_D_PRIMARY_FIRM_NAME)
    firm_count: int = Field(default=0, description=_D_FIRM_COUNT)
    product_count: int = Field(default=0, description=_D_PRODUCT_COUNT)
    has_been_edited: bool = Field(default=False, description=_D_HAS_BEEN_EDITED)
    # detail-only narrative
    recall_reason: str | None = Field(
        default=None,
        description=(
            "The recall or defect narrative, in free text. What it contains varies by agency (CPSC "
            "description, FDA reason for recall, USDA summary, NHTSA defect summary, USCG short "
            "problem note); USDA may contain HTML and USCG is truncated to about 25 characters. "
            "Sources: all five."
        ),
    )
    corrective_action: str | None = Field(
        default=None,
        description=(
            "What the manufacturer and consumer should do, in free text. Sources: NHTSA only (null "
            "for the others)."
        ),
    )
    consequence_of_defect: str | None = Field(
        default=None,
        description=(
            "What can happen if the defect is not fixed, in free text. Sources: NHTSA only (null "
            "for the others)."
        ),
    )
    # geo: a scalar prose string vs the parsed codes array (do NOT conflate)
    distribution_states: str | None = Field(
        default=None,
        description=(
            "USDA's distribution states as a plain comma-joined string (e.g. 'Nationwide' or "
            "'Arizona, California'). For parsed two-letter codes use `distribution_state_codes` "
            "instead. Sources: USDA only (null for the others)."
        ),
    )
    distribution_state_codes: list[str] | None = Field(
        default=None,
        description=(
            "Two-letter US state and territory codes for where the product was distributed. Null "
            "when no geography could be parsed; an empty list means a foreign-only recall. Parsed "
            "conservatively, so a missing code is not proof the product was not sold there. "
            "Sources: FDA, USDA (null for CPSC/NHTSA/USCG)."
        ),
    )
    distribution_country_codes: list[str] | None = Field(
        default=None,
        description=(
            "Two-letter codes for the foreign countries the product was distributed to (the US is "
            "excluded by design; for US geography use `distribution_state_codes`). Null when no "
            "geography could be parsed; an empty list means a domestic-only recall. Sources: FDA "
            "(null for CPSC, USDA, NHTSA, and USCG; USDA currently provides states only)."
        ),
    )
    # jsonb rollups (un-coalesced -> normalize None to [])
    hazards: list[Any] | None = Field(
        default=None,
        description=(
            "CPSC's structured hazard list (each entry has a free-text name; the category fields "
            "are empty at the source). Sources: CPSC only (null for the others). NHTSA's harm "
            "description is in `consequence_of_defect` instead."
        ),
    )
    product_upcs: list[str] = Field(
        default_factory=list,
        description=(
            "Recall-level UPC codes (empty list when absent). Sources: CPSC only and sparse (about "
            "5% of CPSC recalls); empty for FDA, USDA, NHTSA, and USCG."
        ),
    )
    product_names: list[str] = Field(
        default_factory=list,
        description=(
            "Distinct product names, de-duplicated (never null; empty list when none). What this "
            "means varies by agency: CPSC product name, USCG boat model name, FDA product "
            "description, USDA recall title, NHTSA component description. Sources: all five."
        ),
    )
    models: list[str] = Field(
        default_factory=list,
        description=(
            "Distinct product model identifiers, de-duplicated (never null; empty list when none). "
            "Populated only for NHTSA (e.g. 'F-150'); always empty for the others. Sources: NHTSA "
            "only."
        ),
    )
    hins: list[str] = Field(
        default_factory=list,
        description=(
            "Distinct USCG Hull Identification Numbers, de-duplicated (the boating equivalent of a "
            "VIN; never null, empty list when none). USCG only, and only about 54% of USCG recalls "
            "carry a real HIN. Sources: USCG only."
        ),
    )
    firms: list[FirmRef] = Field(
        default_factory=list,
        description=(
            "All firms tied to this recall, one entry per firm-role, ordered by role then name. A "
            "firm with several roles appears more than once, so this can be longer than "
            "`firm_count`. Always a list (possibly empty), never null. Sources: all five."
        ),
    )

    @field_validator("product_names", "models", "hins", "firms", mode="before")
    @classmethod
    def _none_to_list(cls, v: Any) -> Any:
        # The mart leaves these jsonb arrays NULL when empty (01 NULL-vs-coalesce).
        return [] if v is None else v

    @field_validator("product_upcs", mode="before")
    @classmethod
    def _flatten_product_upcs(cls, v: Any) -> Any:
        # Gold stores UPCs as [{"upc": "X"}] objects; unwrap to bare strings (and None -> []).
        return flatten_upcs(v)
