"""Firm-profile response model (01 — Mart 3 / mart_firm_profile) + the three per-source sidecars.

The sidecar OUTPUT columns were renamed (gold-readiness R5, applied upstream) to
``firm_usda_attributes`` (USDA establishments) / ``firm_uscg_attributes`` (USCG boat MIC) /
``firm_fda_attributes`` (FDA FEI). Each sidecar is a jsonb array of attribute rows; the shapes
DIFFER by source, so there are three sub-models. ``extra="ignore"`` keeps them forward-compatible.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UsdaEstablishment(BaseModel):
    """A USDA/FSIS establishment row (firm_usda_attributes, join key establishment_id)."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

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


class UscgManufacturer(BaseModel):
    """A USCG boat-manufacturer/MIC row (firm_uscg_attributes, join key mic)."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

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
    status: str | None = None
    in_business: str | None = None
    out_of_business: str | None = None
    date_modified: str | None = None
    uscg_directory_id: str | None = None
    detail_url: str | None = None
    mic_has_prior_holder: bool | None = None
    mic_oob_recycled: bool | None = None
    mic_renamed_not_recycled: bool | None = None
    prior_holders: list[str] = Field(default_factory=list)


class FdaAttributes(BaseModel):
    """An FDA FEI firm row (firm_fda_attributes, join key firm_fei_num cast to text)."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

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


class FirmProfile(BaseModel):
    """One canonical (cross-source) firm: identity, aliases, recall stats, and 3 sidecars."""

    model_config = ConfigDict(from_attributes=True)

    firm_id: str
    canonical_name: str = Field(examples=["Acme Foods Inc"])
    normalized_name: str
    observed_names: list[str] = Field(default_factory=list)
    observed_company_ids: list[str] = Field(default_factory=list)
    alternate_names: list[str] = Field(default_factory=list)
    total_recalls: int = 0
    active_recalls: int = 0
    first_recall_at: datetime | None = None
    last_recall_at: datetime | None = None
    roles: list[str] = Field(default_factory=list)
    recalls_by_source: dict[str, int] = Field(
        default_factory=dict, examples=[{"FDA": 2, "USDA": 1}]
    )
    distinct_products: int = 0
    firm_usda_attributes: list[UsdaEstablishment] = Field(default_factory=list)  # USDA
    firm_uscg_attributes: list[UscgManufacturer] = Field(default_factory=list)  # USCG
    firm_fda_attributes: list[FdaAttributes] = Field(default_factory=list)  # FDA

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
