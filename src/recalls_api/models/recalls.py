"""Recall response models: ``RecallSummary`` (list subset) and ``RecallDetail`` (full wide row).

Field names equal the ``mart_recall_summary`` column labels (01 — Mart 1) so a Core ``RowMapping``
validates 1:1. jsonb rollups the mart leaves un-coalesced (NULL when empty) become ``[]``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from recalls_api.models.common import FirmRef, Source, flatten_upcs


class RecallSummary(BaseModel):
    """The list projection — the small, list-relevant subset (not the full wide row)."""

    model_config = ConfigDict(from_attributes=True)

    recall_event_id: str
    source: Source
    source_recall_id: str = Field(examples=["24-001"])
    title: str | None = Field(default=None, examples=["Acme Toaster Fire Hazard"])
    url: str | None = None
    announced_at: datetime | None = None
    published_at: datetime
    classification: str | None = Field(default=None, examples=["Class II"])
    risk_level: str | None = Field(default=None, examples=["Low - Class II"])
    lifecycle_status: str | None = None
    is_active: bool | None = Field(default=None, description="Tri-state; null for CPSC/NHTSA.")
    reason_category: str | None = None
    distribution_scope: str = Field(examples=["Nationwide"])
    primary_firm_name: str | None = None
    firm_count: int = 0
    product_count: int = 0
    edit_event_count: int = 0
    has_been_edited: bool = False


class RecallSearchHit(RecallSummary):
    """A ``RecallSummary`` plus its FTS relevance ``rank`` (``GET /recalls/search``)."""

    rank: float = Field(
        description="ts_rank_cd relevance; higher = better, not comparable across queries."
    )


class RecallDetail(BaseModel):
    """The full wide row: summary subset + narrative, geo, lifecycle, and the jsonb rollups."""

    model_config = ConfigDict(from_attributes=True)

    # identity / summary subset
    recall_event_id: str
    source: Source
    source_recall_id: str
    title: str | None = None
    url: str | None = None
    announced_at: datetime | None = None
    published_at: datetime
    classification: str | None = None
    risk_level: str | None = None
    lifecycle_status: str | None = None
    is_active: bool | None = None
    reason_category: str | None = None
    distribution_scope: str
    primary_firm_name: str | None = None
    firm_count: int = 0
    product_count: int = 0
    edit_event_count: int = 0
    has_been_edited: bool = False
    # detail-only narrative
    recall_reason: str | None = None
    corrective_action: str | None = None
    consequence_of_defect: str | None = None
    # geo: a scalar prose string vs the parsed codes array (do NOT conflate)
    distribution_states: str | None = Field(
        default=None, description="Agency prose (scalar string)."
    )
    distribution_state_codes: list[str] | None = Field(
        default=None, description="Parsed USPS codes."
    )
    distribution_country_codes: list[str] | None = Field(
        default=None, description="ISO alpha-2, foreign-only (US excluded by design)."
    )
    # jsonb rollups (un-coalesced -> normalize None to [])
    hazards: list[Any] | None = Field(
        default=None, description="Opaque hazard objects; may be null."
    )
    product_upcs: list[str] = Field(
        default_factory=list,
        description="Recall-level UPCs (CPSC-sourced; sparse). Flattened from gold's object array.",
    )
    product_names: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    hins: list[str] = Field(default_factory=list, description="USCG Hull IDs.")
    firms: list[FirmRef] = Field(default_factory=list)
    # observation / lifecycle
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    edit_count: int | None = None
    is_currently_active: bool | None = None
    was_ever_retracted: bool | None = None

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
