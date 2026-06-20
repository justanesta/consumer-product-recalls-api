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

# --- Shared descriptions for the summary-subset columns (identical on Summary & Detail) ---
_D_RECALL_EVENT_ID = (
    "Opaque surrogate id for one recall event, stable across re-extractions: md5('<SOURCE>|<source "
    "recall key>'), reused verbatim from silver (ADR 0038). Not a raw agency id — pair source with "
    "source_recall_id for the human-facing key. Sources: all five."
)
_D_SOURCE = "Originating agency feed (closed enum): CPSC, FDA, USDA, NHTSA, USCG. Always populated."
_D_SOURCE_RECALL_ID = (
    "Agency-native recall identifier; meaning varies by source — CPSC RecallNumber, FDA "
    "RECALLEVENTID, USDA field_recall_number (DDD-YYYY), NHTSA CAMPNO, USCG recall Number. Pair "
    "with source for global identity. Always populated."
)
_D_TITLE = (
    "Human-readable recall headline. Native title for CPSC/USDA; synthesized as '<recall-id> — "
    "<firm/model name>' for FDA/NHTSA/USCG (no native title). Effectively always populated."
)
_D_URL = (
    "Public detail-page URL for the recall. Sources: CPSC, USDA, USCG (null for FDA/NHTSA, which "
    "provide no per-recall detail URL)."
)
_D_ANNOUNCED_AT = (
    "Date the recall was first announced/initiated, conformed across all five sources. Nullable: "
    "~20 FDA events lack a trustworthy initiation date. Use published_at when a guaranteed date is "
    "required. Sources: all five."
)
_D_PUBLISHED_AT = (
    "Last-published/modified date, coalesced per source to always be present — the guaranteed "
    "sort/pagination key (contrast nullable announced_at). NHTSA's underlying field is a "
    "record-creation date, not a last-modified (its flat file carries no last-modified field). "
    "Sources: all five."
)
_D_CLASSIFICATION = (
    "Recall severity/hazard classification in the source's NATIVE vocabulary (FDA: 1/2/3, NC=Not "
    "Yet Classified; USDA: Class I/II/III, Public Health Alert; USCG: H/L/M/S). NOT normalized "
    "across sources. Sources: FDA, USDA, USCG (null for CPSC/NHTSA)."
)
_D_RISK_LEVEL = (
    "USDA health-risk label derived 1:1 from the USDA classification (e.g. 'High - Class I', 'Low "
    "- Class II', 'Marginal - Class III', 'Public Health Alert'). Sources: USDA only (null for "
    "CPSC/FDA/NHTSA/USCG)."
)
_D_LIFECYCLE_STATUS = (
    "Recall lifecycle/status in the source's native vocabulary (FDA: Ongoing/Completed/Terminated; "
    "USDA: Active Recall/Closed Recall/Public Health Alert; USCG: Open/Closed). NOT normalized; "
    "see is_active for a conformed boolean. Sources: FDA, USDA, USCG (null for CPSC/NHTSA)."
)
_D_IS_ACTIVE = (
    "Conformed tri-state flag for whether the recall is still active, derived from each source's "
    "lifecycle field (USDA Public Health Alert counts as active). Sources: FDA, USDA, USCG (null "
    "for CPSC/NHTSA, which have no lifecycle concept and so match neither true nor false)."
)
_D_REASON_CATEGORY = (
    "Categorical recall-reason tokens from USDA's FSIS taxonomy (comma-joined, e.g. 'Unreported "
    "Allergens, Misbranding'). Sources: USDA only (null for CPSC/FDA/NHTSA/USCG, whose reasons are "
    "free text in recall_reason)."
)
_D_DISTRIBUTION_SCOPE = (
    "Conformed distribution-breadth enum, always populated: Nationwide, International, Regional, "
    "or Unspecified. Classified from real distribution text for FDA/USDA; CPSC/USCG default to "
    "Unspecified and NHTSA to Nationwide. Sources: all five."
)
_D_PRIMARY_FIRM_NAME = (
    "Primary display firm for the recall — the canonical firm name picked by role priority "
    "(manufacturer > establishment > filer > importer > distributor, then alphabetical). Null only "
    "if no firm resolves. Sources: all five."
)
_D_FIRM_COUNT = (
    "Count of DISTINCT firms linked to this recall across all roles (a firm in multiple roles "
    "counts once, so this may be less than len(firms)). 0 when no firm resolves. Sources: all "
    "five."
)
_D_PRODUCT_COUNT = (
    "Number of distinct product rows for this recall. CPSC/FDA/NHTSA can exceed 1; USDA and USCG "
    "are always 1 (modeled one-product-per-recall). Never null. Sources: all five."
)
_D_HAS_BEEN_EDITED = (
    "True if the pipeline has detected at least one editorially-meaningful change to a tracked "
    "event field (recall_reason, classification, lifecycle_status, title, terminated_at) by "
    "diffing consecutive bronze snapshots; false otherwise. Observed-edit evidence, NOT a flag of "
    "an official agency amendment — cosmetic/whitespace changes are suppressed, tracked fields "
    "vary by source, and detection is bounded by snapshot retention and a pipeline reseed (false "
    "can mean 'no change seen since the last reseed'). Synthesized; populated for all sources."
)


class RecallSummary(BaseModel):
    """The list projection — the small, list-relevant subset (not the full wide row)."""

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
    """A ``RecallSummary`` plus its FTS relevance ``rank`` (``GET /recalls/search``)."""

    rank: float = Field(
        description=(
            "Full-text relevance (ts_rank_cd over the recall search_vector, weighted "
            "title>brand>cause>harm). Higher is more relevant, but scores are not comparable "
            "across queries. Computed per request; present only on the /recalls/search path."
        )
    )


class RecallDetail(BaseModel):
    """The full wide row: summary subset + narrative, geo, lifecycle, and the jsonb rollups."""

    model_config = ConfigDict(from_attributes=True)

    # identity / summary subset (descriptions shared with RecallSummary via _D_* constants)
    recall_event_id: str = Field(description=_D_RECALL_EVENT_ID)
    source: Source = Field(description=_D_SOURCE)
    source_recall_id: str = Field(description=_D_SOURCE_RECALL_ID)
    title: str | None = Field(default=None, description=_D_TITLE)
    url: str | None = Field(default=None, description=_D_URL)
    announced_at: datetime | None = Field(default=None, description=_D_ANNOUNCED_AT)
    published_at: datetime = Field(description=_D_PUBLISHED_AT)
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
            "Free-text recall/defect narrative, conformed across sources (CPSC Description, FDA "
            "reason-for-recall, USDA HTML summary, NHTSA defect summary, USCG short problem note). "
            "Content type and length vary by source; USDA is HTML-encoded and USCG is truncated to "
            "~25 chars. Sources: all five."
        ),
    )
    corrective_action: str | None = Field(
        default=None,
        description=(
            "Free-text corrective-action / remedy narrative (what the manufacturer and consumer "
            "should do). Sources: NHTSA only (null for CPSC/FDA/USDA/USCG in this model)."
        ),
    )
    consequence_of_defect: str | None = Field(
        default=None,
        description=(
            "Free-text description of what can happen if the defect is not remedied "
            "(harm/consequence). Sources: NHTSA only (null for CPSC/FDA/USDA/USCG)."
        ),
    )
    # geo: a scalar prose string vs the parsed codes array (do NOT conflate)
    distribution_states: str | None = Field(
        default=None,
        description=(
            "USDA distribution-states as a raw comma-joined string (e.g. 'Nationwide', 'Arizona, "
            "California') — prose, not parsed codes. For machine-readable geography use "
            "distribution_state_codes. Sources: USDA only (null for CPSC/FDA/NHTSA/USCG)."
        ),
    )
    distribution_state_codes: list[str] | None = Field(
        default=None,
        description=(
            "USPS 2-letter state/territory codes for where the recalled product was distributed "
            "(initial distribution area). Null when no geography parsed; an empty array indicates "
            "a foreign-country-only recall. A precision-first parse (absence of a code is not "
            "proof of non-distribution). Sources: FDA, USDA (null for CPSC/NHTSA/USCG)."
        ),
    )
    distribution_country_codes: list[str] | None = Field(
        default=None,
        description=(
            "ISO-3166-1 alpha-2 codes for the FOREIGN countries the product was distributed to (US "
            "excluded by design — domestic geography is distribution_state_codes). Null when no "
            "geography parsed; an empty array indicates a domestic-only recall. Sources: FDA (null "
            "for CPSC/USDA/NHTSA/USCG — the USDA path exists but field_states is states-only "
            "today)."
        ),
    )
    # jsonb rollups (un-coalesced -> normalize None to [])
    hazards: list[Any] | None = Field(
        default=None,
        description=(
            "CPSC structured hazard array (jsonb objects with a free-text 'Name'; categorical "
            "HazardType/HazardTypeID are empty at source). Sources: CPSC only (null for "
            "FDA/USDA/NHTSA/USCG). NHTSA's harm narrative is in consequence_of_defect."
        ),
    )
    product_upcs: list[str] = Field(
        default_factory=list,
        description=(
            "Recall-level product UPC codes (gold stores them as [{upc:…}] objects; the API "
            "flattens to bare strings, [] when absent). Sources: CPSC only and sparse (~5% of CPSC "
            "recalls); empty for FDA/USDA/NHTSA/USCG."
        ),
    )
    product_names: list[str] = Field(
        default_factory=list,
        description=(
            "Deduplicated array of distinct product names (never null; [] when empty). "
            "Source-dependent semantics: CPSC = product name; USCG = boat model name; FDA = the "
            "product DESCRIPTION text; USDA = the recall TITLE; NHTSA = the COMPONENT description. "
            "Sources: all five."
        ),
    )
    models: list[str] = Field(
        default_factory=list,
        description=(
            "Deduplicated array of product model identifiers (never null; [] when empty). "
            "Populated only for NHTSA (MODELTXT, e.g. 'F-150'); always [] for CPSC, FDA, USDA, "
            "USCG. Sources: NHTSA only."
        ),
    )
    hins: list[str] = Field(
        default_factory=list,
        description=(
            "Deduplicated array of USCG Hull Identification Numbers (the boating analog of a "
            "VIN/UPC; never null, [] when empty). USCG-only — always [] for CPSC, FDA, USDA, "
            "NHTSA; only ~54% of USCG recalls carry a real HIN. Sources: USCG only."
        ),
    )
    firms: list[FirmRef] = Field(
        default_factory=list,
        description=(
            "Array of all firms tied to this recall, one object per firm-role ({firm_id, name, "
            "role, match_confidence}), ordered by role then name. A firm in multiple roles appears "
            "multiple times, so len(firms) can exceed firm_count. Always a (possibly empty) array, "
            "never null. Sources: all five."
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
