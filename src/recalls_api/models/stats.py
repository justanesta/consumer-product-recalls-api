"""Response models + enums for the ``/stats/*`` read-through endpoints over the gold ``fct_*``.

The ``fct_*`` are small pre-aggregates, so each endpoint returns a typed ``list`` (no pagination);
``/stats/overview`` returns a single object. Per-source non-comparability and the geography/units
caveats live in the ``Field`` descriptions. Columns mirror each gold model's final SELECT (confirmed
against ``_gold.yml`` + the ``fct_*`` SQL, 2026-06-19).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from recalls_api.models.descriptions import D_CLASSIFICATION


class StatsSource(StrEnum):
    """The ``fct_*`` source domain — the 5 agency feeds plus the synthesized ``ALL`` rollup.

    Distinct from the strict ``Source`` enum (which has no ``ALL``). Per-endpoint population varies:
    monthly-trend is per-source only (no ``ALL``); by-country is FDA/USDA (+``ALL``); units is
    NHTSA/USCG/FDA/USDA (no ``ALL``, no CPSC). A source absent from a given fact returns ``[]``.
    """

    CPSC = "CPSC"
    FDA = "FDA"
    USDA = "USDA"
    NHTSA = "NHTSA"
    USCG = "USCG"
    ALL = "ALL"


class Grain(StrEnum):
    """Time grain for ``/stats/recalls-by-period``."""

    MONTH = "month"
    WEEK = "week"
    YEAR = "year"


class GeographyBasis(StrEnum):
    """The two (non-interchangeable) geography lenses for ``/stats/by-geography``."""

    DISTRIBUTION = "distribution"
    FIRM_REGISTRATION = "firm_registration"


class StatsOverview(BaseModel):
    """Headline KPIs for the landing page (API-computed, not a stored ``fct_*``)."""

    total_recalls: int = Field(description="Count of recall events (rows in mart_recall_summary).")
    distinct_firms: int = Field(description="Count of canonical firms (rows in mart_firm_profile).")
    sources: list[str] = Field(description="The feeds covered: CPSC, FDA, USDA, NHTSA, USCG.")
    last_rebuilt_at: datetime | None = Field(
        default=None,
        description="gold_meta.rebuilt_at — when the gold marts were last rebuilt (UTC).",
    )


class PeriodCount(BaseModel):
    """One (period, source) recall count — backs ``/stats/recalls-by-period`` (month/week/year)."""

    model_config = ConfigDict(from_attributes=True)

    period: date = Field(description="Period start (month / ISO-week Monday / Jan-1 per grain).")
    source: str = Field(description="Agency feed, or 'ALL' for the all-source rollup.")
    event_count: int = Field(description="Distinct recall events in this period for this source.")


class MonthlyTrendPoint(BaseModel):
    """One month of the per-source trend over a dense spine — rolling averages + YoY."""

    model_config = ConfigDict(from_attributes=True)

    month: date
    source: str = Field(description="Agency feed (per-source only; no 'ALL' rollup on this fact).")
    event_count: int
    rolling_3mo_avg: float | None = Field(default=None, description="3-month rolling average.")
    rolling_12mo_avg: float | None = Field(default=None, description="12-month rolling average.")
    event_count_year_ago: int | None = Field(
        default=None, description="event_count 12 months earlier (null for the first year)."
    )
    yoy_pct_change: float | None = Field(
        default=None, description="Year-over-year % change vs 12 months ago (null when undefined)."
    )


class ClassificationCount(BaseModel):
    """Recall counts by source-native classification + risk_level (+ the 'ALL' rollup)."""

    model_config = ConfigDict(from_attributes=True)

    source: str = Field(description="Agency feed, or 'ALL'.")
    classification: str | None = Field(default=None, description=D_CLASSIFICATION)
    risk_level: str | None = Field(
        default=None, description="USDA-only health-risk label; null for the other sources."
    )
    event_count: int


class StatusCount(BaseModel):
    """Active / inactive / unknown recall counts per source (+ the 'ALL' rollup)."""

    model_config = ConfigDict(from_attributes=True)

    source: str = Field(description="Agency feed, or 'ALL'.")
    status: str = Field(
        description="'active' / 'inactive' / 'unknown'. CPSC/NHTSA carry no lifecycle -> 'unknown'."
    )
    event_count: int


class FirmLeaderRow(BaseModel):
    """A row of the most-recalled-firms leaderboard (ranked over mart_firm_profile)."""

    model_config = ConfigDict(from_attributes=True)

    firm_id: str = Field(description="Canonical firm id; use with GET /firms/{firm_id}.")
    canonical_name: str
    event_count: int = Field(description="Total distinct recalls for the firm (all sources).")
    active_recalls: int = Field(description="Currently-active recalls (FDA/USDA/USCG only).")
    product_count: int = Field(description="Distinct recalled products (per-firm footprint).")
    event_count_rank: int = Field(description="Dense rank by total recalls (1 = most-recalled).")
    first_recall_at: datetime | None = None
    last_recall_at: datetime | None = None


class GeographyCount(BaseModel):
    """Per-US-state recall counts, two lenses (distribution vs firm-registration) + 'ALL' rollup."""

    model_config = ConfigDict(from_attributes=True)

    geography_basis: str = Field(
        description=(
            "'distribution' (where the product went; FDA/USDA) or 'firm_registration' (where the "
            "firm is registered; USDA/USCG/FDA). The two lenses are DIFFERENT questions — not "
            "interchangeable."
        )
    )
    source: str = Field(description="Agency feed, or 'ALL'.")
    state_code: str = Field(description="USPS 2-letter state/territory code.")
    recall_count: int = Field(
        description=(
            "Recalls touching this state. NOTE: a recall is counted in EVERY state it touches, so "
            "per-state counts SUM TO MORE than the total (industry-footprint reading)."
        )
    )


class CountryCount(BaseModel):
    """Per-distribution-country recall counts (FDA/USDA + 'ALL') — the country analogue of state."""

    model_config = ConfigDict(from_attributes=True)

    source: str = Field(description="Agency feed (FDA/USDA), or 'ALL'.")
    country_code: str = Field(description="ISO-3166-1 alpha-2 (incl. a derived 'US').")
    recall_count: int = Field(
        description=(
            "Recalls distributed to this country. Multi-valued — a US+abroad recall counts once "
            "per country, so per-country counts sum to more than the distinct-recall total."
        )
    )


class UnitsRow(BaseModel):
    """Units recalled per source x unit_category x month. NOT cross-source comparable (no 'ALL')."""

    model_config = ConfigDict(from_attributes=True)

    source: str = Field(
        description="NHTSA/USCG (units affected) or FDA/USDA (quantity). No 'ALL' rollup."
    )
    unit_category: str = Field(
        description=(
            "'count' / 'weight' / 'volume' / 'grouping' — keeps incommensurable units apart; never "
            "sum across categories or sources."
        )
    )
    period: date = Field(description="Month start.")
    recalls_with_units: int
    total_units: float = Field(
        description="Sum of per-recall magnitudes (a recall-magnitude measure, not unique items)."
    )
    avg_units_per_recall: float
    max_units: float


# Convenience: the response-model list for the contract test / surface guard.
__all__ = [
    "ClassificationCount",
    "CountryCount",
    "FirmLeaderRow",
    "GeographyBasis",
    "GeographyCount",
    "Grain",
    "MonthlyTrendPoint",
    "PeriodCount",
    "StatsOverview",
    "StatsSource",
    "StatusCount",
    "UnitsRow",
]
