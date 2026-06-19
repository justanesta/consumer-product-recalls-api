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
    status: str | None = Field(
        default=None,
        description=(
            "USCG boat-manufacturer directory operating status, passed through verbatim from the "
            "scraped USCG directory. Observed warn-guarded live domain (per the data side's "
            "accepted_values test as of 2026-06-19): 'In Business', 'Inactive', 'Federal or State "
            "Agency'. Not enum-constrained, so a future upstream value still parses. Sources: USCG "
            "only."
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

    firm_id: str = Field(
        description=(
            "Synthetic primary key of the canonical firm (a cross-source cluster). Derived from "
            "the firm-resolution crosswalk, falling back to md5(normalized name). One row per "
            "canonical firm across all agencies. Sources: derived (all five contribute names)."
        )
    )
    canonical_name: str = Field(
        examples=["Acme Foods Inc"],
        description=(
            "Human-readable display name of the canonical firm — the cluster's resolved name, or "
            "the representative raw firm name when unclustered. Not an authoritative legal name. "
            "Sources: all five."
        ),
    )
    normalized_name: str = Field(
        description=(
            "Upper-cased, whitespace-trimmed form of the firm's representative name for "
            "case-insensitive lookup. NOT a unique key (firm_id is the key). Sources: all five."
        )
    )
    observed_names: list[str] = Field(
        default_factory=list,
        description=(
            "JSONB array of all distinct raw firm-name surface forms (across sources and "
            "spellings) that map to this canonical firm — the provenance/audit trail of names "
            "collapsed together. Always >=1 element. Sources: all five."
        ),
    )
    observed_company_ids: list[str] = Field(
        default_factory=list,
        description=(
            "JSONB array of distinct structured firm identifiers observed for this firm: FDA FEI "
            "numbers, USDA FSIS establishment numbers, and USCG MICs. Also the join key to the "
            "three sidecars. Sources: FDA, USDA, USCG (empty for firms seen only via CPSC/NHTSA, "
            "which carry no usable firm id)."
        ),
    )
    alternate_names: list[str] = Field(
        default_factory=list,
        description=(
            "JSONB array of brand/DBA surface-form aliases (e.g. 'John Deere' for 'Deere & Company "
            "(John Deere)'), derived by the firm-resolution step for search and fuzzy matching. "
            "Empty when the firm has no aliases. Sources: derived (not a per-agency field)."
        ),
    )
    total_recalls: int = Field(
        default=0,
        description=(
            "Total distinct recalls this firm is linked to, across all sources it appears in (a "
            "firm in multiple roles on one recall counts once). Always present. Sources: all five."
        ),
    )
    active_recalls: int = Field(
        default=0,
        description=(
            "Count of this firm's distinct currently-active recalls. Only FDA, USDA, and USCG "
            "recalls can be active; CPSC and NHTSA have no lifecycle (is_active null) and never "
            "count. Always present (0 if none). Sources counted: FDA, USDA, USCG."
        ),
    )
    first_recall_at: datetime | None = Field(
        default=None,
        description=(
            "Earliest recall publication timestamp for this firm (min of published_at — a "
            "per-source 'last published / record-created' date, not a uniform announcement date). "
            "Null only for a firm with no linked recall. Sources: all five."
        ),
    )
    last_recall_at: datetime | None = Field(
        default=None,
        description=(
            "Most recent recall publication timestamp for this firm (max of published_at; same "
            "per-source caveat as first_recall_at). Null only for a firm with no linked recall. "
            "Sources: all five."
        ),
    )
    roles: list[str] = Field(
        default_factory=list,
        description=(
            "Distinct roles this firm has played across its recalls: manufacturer, importer, "
            "distributor (CPSC), establishment (FDA/USDA), filer/manufacturer (NHTSA), "
            "manufacturer (USCG). Sources: all five."
        ),
    )
    recalls_by_source: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"FDA": 2, "USDA": 1}],
        description=(
            "JSONB object mapping source -> distinct recall count for this firm (e.g. {'NHTSA': "
            "12, 'CPSC': 3}). Only sources where the firm has >=1 recall appear as keys, and the "
            "values sum to total_recalls. Sources: all five."
        ),
    )
    distinct_products: int = Field(
        default=0,
        description=(
            "Total distinct recalled-product rows across all recalls this firm is associated with, "
            "in any role (a per-firm footprint, NOT a global distinct — a product on a multi-firm "
            "recall is counted under each firm). Never null. Sources: all five."
        ),
    )
    firm_usda_attributes: list[UsdaEstablishment] = Field(
        default_factory=list,
        description=(
            "USDA FSIS establishment attributes — a JSON array of one block per matched FSIS "
            "establishment number (name, address, regulatory metadata, grant dates). Empty for "
            "non-USDA firms. Sources: USDA only."
        ),
    )
    firm_uscg_attributes: list[UscgManufacturer] = Field(
        default_factory=list,
        description=(
            "USCG boat-manufacturer directory attributes — a JSON array of one block per USCG "
            "Manufacturer Identification Code (MIC) the firm is registered under (company name, "
            "address, status, succession lineage, MIC-recycle flags). Empty for non-USCG firms. "
            "Sources: USCG only."
        ),
    )
    firm_fda_attributes: list[FdaAttributes] = Field(
        default_factory=list,
        description=(
            "FDA establishment attributes — a JSON array of one block per FDA FEI the firm "
            "clusters under (legal name, address at time of recall, firm-succession signal). Empty "
            "for non-FDA firms. Sources: FDA only."
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
