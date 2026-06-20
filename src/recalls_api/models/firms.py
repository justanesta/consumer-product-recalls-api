"""Firm-profile response model (01 — Mart 3 / mart_firm_profile) + the three per-source sidecars.

The sidecar OUTPUT columns were renamed (gold-readiness R5, applied upstream) to
``firm_usda_attributes`` (USDA establishments) / ``firm_uscg_attributes`` (USCG boat MIC) /
``firm_fda_attributes`` (FDA FEI). Each sidecar is a jsonb array of attribute rows; the shapes
DIFFER by source, so there are three sub-models. ``extra="ignore"`` keeps them forward-compatible.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _collapse_nonscalars(data: Any, keep_lists: frozenset[str] = frozenset()) -> Any:
    """Collapse stray jsonb arrays/objects in a sidecar row to scalar strings.

    USDA's establishment directory can deliver a string-typed field as a jsonb array — e.g. ``dbas``
    and ``activities`` after the 2026-06 FSIS API change — where the wire contract is a scalar
    string. ``coerce_numbers_to_str`` only handles numbers, so without this a single array- or
    object-valued field raises a ResponseValidationError and 500s the whole firm response. This
    mirrors the data side's ``jsonb_array_to_csv()`` and guards the sidecars against future shape
    drift, not just today's fields: a list becomes a comma-joined string, an object its string form,
    while scalars and legitimately list-typed fields (``keep_lists``) pass through untouched.
    """
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in keep_lists or not isinstance(value, list | dict):
            out[key] = value
        elif isinstance(value, list):
            out[key] = ", ".join(str(item) for item in value)
        else:
            out[key] = str(value)
    return out


class UsdaEstablishment(BaseModel):
    """A USDA establishment registration record for the firm."""

    model_config = ConfigDict(from_attributes=True, extra="ignore", coerce_numbers_to_str=True)

    establishment_id: str
    establishment_name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    county: str | None = None
    fips_code: str | None = None
    geolocation: str | None = None
    latest_mpi_active_date: str | None = None
    grant_date: str | None = None
    status_regulated_est: str | None = None
    size: str | None = None
    district: str | None = None
    circuit: str | None = None
    activities: str | None = None
    dbas: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _collapse_jsonb_arrays(cls, data: Any) -> Any:
        # dbas/activities (and any future field) arrive as jsonb arrays from the FSIS establishment
        # directory; collapse non-scalars to strings so one array field can't 500 the firm response.
        return _collapse_nonscalars(data)


class UscgManufacturer(BaseModel):
    """A USCG boat-builder registration record for the firm."""

    model_config = ConfigDict(from_attributes=True, extra="ignore", coerce_numbers_to_str=True)

    mic: str
    company_name: str | None = None
    dba: str | None = None
    parent_company: str | None = None
    parent_mic: str | None = None
    past_company_1: str | None = None
    past_company_2: str | None = None
    past_company_3: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None
    status: str | None = Field(
        default=None,
        description=(
            "The boat builder's operating status, passed through from the USCG directory. Values "
            "seen so far: 'In Business', 'Inactive', 'Federal or State Agency'. Not restricted, so "
            "a new value from the source still parses. Sources: USCG only."
        ),
    )
    in_business: str | None = None
    out_of_business: str | None = None
    date_modified: str | None = None
    uscg_directory_id: str | None = None
    detail_url: str | None = None
    mic_has_prior_holder: bool | None = None
    mic_oob_recycled: bool | None = None
    mic_renamed_not_recycled: bool | None = None
    prior_holders: list[str] = Field(default_factory=list)

    @field_validator("prior_holders", mode="before")
    @classmethod
    def _none_to_list(cls, v: Any) -> Any:
        # Silver builds this as to_jsonb(array_remove(...)) -> [] at the silver grain, but the
        # mart_firm_profile aggregation can re-introduce a NULL; the top-level FirmProfile validator
        # only covers the sidecar LISTS, not this nested row field. Belt-and-suspenders -> [].
        return [] if v is None else v

    @model_validator(mode="before")
    @classmethod
    def _collapse_jsonb_arrays(cls, data: Any) -> Any:
        # prior_holders is a real list[str] and stays a list; every other field is a scalar string.
        return _collapse_nonscalars(data, keep_lists=frozenset({"prior_holders"}))


class FdaAttributes(BaseModel):
    """An FDA registration record for the firm."""

    model_config = ConfigDict(from_attributes=True, extra="ignore", coerce_numbers_to_str=True)

    firm_fei_num: int | str  # FEI bigint; asyncpg returns int (the join casts to text)
    firm_legal_nam: str | None = None
    firm_city_nam: str | None = None
    firm_state_cd: str | None = None
    firm_state_prvnc_nam: str | None = None
    firm_country_nam: str | None = None
    firm_postal_cd: str | None = None
    firm_line1_adr: str | None = None
    firm_line2_adr: str | None = None
    firm_surviving_nam: str | None = None
    firm_surviving_fei: int | str | None = None

    @model_validator(mode="before")
    @classmethod
    def _collapse_jsonb_arrays(cls, data: Any) -> Any:
        return _collapse_nonscalars(data)


class FirmProfile(BaseModel):
    """A single firm merged across agencies: names, recall stats, and registration records."""

    model_config = ConfigDict(from_attributes=True)

    firm_id: str = Field(
        description=(
            "Opaque id for this firm (the merged cross-agency entity). One per firm. Sources: "
            "derived (all five agencies contribute names)."
        )
    )
    canonical_name: str = Field(
        examples=["Acme Foods Inc"],
        description=(
            "The firm's display name: its resolved name, or a representative raw name when it "
            "stands alone. Not an authoritative legal name. Sources: all five."
        ),
    )
    normalized_name: str = Field(
        description=(
            "An upper-cased, trimmed form of the firm's name for case-insensitive lookup. Not "
            "unique (`firm_id` is the key). Sources: all five."
        )
    )
    observed_names: list[str] = Field(
        default_factory=list,
        description=(
            "All the distinct raw spellings of this firm's name that were merged together. Always "
            "has at least one. Sources: all five."
        ),
    )
    observed_company_ids: list[str] = Field(
        default_factory=list,
        description=(
            "The firm's structured identifiers: FDA registration numbers, USDA establishment "
            "numbers, and USCG manufacturer codes. Empty for firms seen only through CPSC or "
            "NHTSA, which carry no usable id. Sources: FDA, USDA, USCG."
        ),
    )
    alternate_names: list[str] = Field(
        default_factory=list,
        description=(
            "Brand or 'doing business as' aliases for the firm (e.g. 'John Deere' for 'Deere & "
            "Company'). Empty when the firm has none. Sources: derived (not a per-agency field)."
        ),
    )
    total_recalls: int = Field(
        default=0,
        description=(
            "Total distinct recalls this firm is linked to, across every agency it appears in "
            "(multiple roles on one recall count once). Always present. Sources: all five."
        ),
    )
    active_recalls: int = Field(
        default=0,
        description=(
            "How many of the firm's recalls are currently active. Only FDA, USDA, and USCG recalls "
            "can be active; CPSC and NHTSA have no status and never count. Always present (0 if "
            "none). Sources: FDA, USDA, USCG."
        ),
    )
    first_recall_at: datetime | None = Field(
        default=None,
        description=(
            "The firm's earliest recall date, by when each recall was first announced (or its "
            "publish date when no announcement date exists). Null only for a firm with no linked "
            "recall. Sources: all five."
        ),
    )
    last_recall_at: datetime | None = Field(
        default=None,
        description=(
            "The firm's most recent recall date, on the same basis as `first_recall_at`. Null "
            "only for a firm with no linked recall. Sources: all five."
        ),
    )
    roles: list[str] = Field(
        default_factory=list,
        description=(
            "The distinct roles this firm has played: manufacturer, importer, distributor (CPSC), "
            "establishment (FDA/USDA), filer or manufacturer (NHTSA), manufacturer (USCG). "
            "Sources: all five."
        ),
    )
    recalls_by_source: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"FDA": 2, "USDA": 1}],
        description=(
            "A map of agency to the firm's recall count (e.g. {'NHTSA': 12, 'CPSC': 3}). Only "
            "agencies where the firm has at least one recall appear, and the values sum to "
            "`total_recalls`. Sources: all five."
        ),
    )
    distinct_products: int = Field(
        default=0,
        description=(
            "Total distinct recalled products across all this firm's recalls, in any role. This "
            "is a per-firm tally, so a product on a multi-firm recall is counted under each firm. "
            "Never null. Sources: all five."
        ),
    )
    firm_usda_attributes: list[UsdaEstablishment] = Field(
        default_factory=list,
        description=(
            "USDA establishment records, one per matched establishment (name, address, regulatory "
            "details, grant dates). Empty for non-USDA firms. Sources: USDA only."
        ),
    )
    firm_uscg_attributes: list[UscgManufacturer] = Field(
        default_factory=list,
        description=(
            "USCG boat-builder records, one per manufacturer code the firm is registered under "
            "(company name, address, status, ownership history). Empty for non-USCG firms. "
            "Sources: USCG only."
        ),
    )
    firm_fda_attributes: list[FdaAttributes] = Field(
        default_factory=list,
        description=(
            "FDA establishment records, one per FDA registration the firm is grouped under (legal "
            "name, address, succession signal). Empty for non-FDA firms. Sources: FDA only."
        ),
    )

    @field_validator(
        "observed_names",
        "observed_company_ids",
        "alternate_names",
        "roles",
        "firm_usda_attributes",
        "firm_uscg_attributes",
        "firm_fda_attributes",
        mode="before",
    )
    @classmethod
    def _none_to_list(cls, v: Any) -> Any:
        return [] if v is None else v

    @field_validator("recalls_by_source", mode="before")
    @classmethod
    def _none_to_dict(cls, v: Any) -> Any:
        return {} if v is None else v
