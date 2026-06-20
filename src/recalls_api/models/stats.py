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
    """An agency, plus ``ALL`` for the all-agency rollup.

    Not every endpoint uses every value: monthly-trend has no ``ALL``; by-country covers FDA and
    USDA; units covers NHTSA, USCG, FDA, and USDA with no ``ALL`` and no CPSC. A value with no data
    for a given stat returns an empty list.
    """

    CPSC = "CPSC"
    FDA = "FDA"
    USDA = "USDA"
    NHTSA = "NHTSA"
    USCG = "USCG"
    ALL = "ALL"


class Grain(StrEnum):
    """Time bucket for ``/stats/recalls-by-period``: month, week, or year."""

    MONTH = "month"
    WEEK = "week"
    YEAR = "year"


class GeographyBasis(StrEnum):
    """The two geography views for ``/stats/by-geography`` (they answer different questions)."""

    DISTRIBUTION = "distribution"
    FIRM_REGISTRATION = "firm_registration"


class StatsOverview(BaseModel):
    """Headline totals for an overview or landing page."""

    total_recalls: int = Field(description="Total number of recall events.")
    distinct_firms: int = Field(description="Total number of distinct firms.")
    sources: list[str] = Field(description="The agencies covered: CPSC, FDA, USDA, NHTSA, USCG.")
    last_rebuilt_at: datetime | None = Field(
        default=None,
        description="When the data was last rebuilt (UTC).",
    )


class PeriodCount(BaseModel):
    """A recall count for one period and agency (``/stats/recalls-by-period``)."""

    model_config = ConfigDict(from_attributes=True)

    period: date = Field(
        description="Start of the period (first of the month, the Monday of the week, or Jan 1)."
    )
    source: str = Field(description="Agency, or `ALL` for the all-agency rollup.")
    event_count: int = Field(
        description="Number of distinct recalls in this period for this agency."
    )


class MonthlyTrendPoint(BaseModel):
    """One month of an agency's recall trend, with rolling averages and year-over-year change."""

    model_config = ConfigDict(from_attributes=True)

    month: date
    source: str = Field(description="Agency (this stat has no `ALL` rollup).")
    event_count: int
    rolling_3mo_avg: float | None = Field(default=None, description="3-month rolling average.")
    rolling_12mo_avg: float | None = Field(default=None, description="12-month rolling average.")
    event_count_year_ago: int | None = Field(
        default=None, description="The count 12 months earlier (null for the first year)."
    )
    yoy_pct_change: float | None = Field(
        default=None, description="Year-over-year % change vs 12 months ago (null when undefined)."
    )


class ClassificationCount(BaseModel):
    """Recall counts by each agency's own classification and risk level, plus an ``ALL`` rollup."""

    model_config = ConfigDict(from_attributes=True)

    source: str = Field(description="Agency, or `ALL`.")
    classification: str | None = Field(default=None, description=D_CLASSIFICATION)
    risk_level: str | None = Field(
        default=None, description="USDA-only health-risk label; null for the other agencies."
    )
    event_count: int


class StatusCount(BaseModel):
    """Active, inactive, and unknown recall counts per agency, plus an ``ALL`` rollup."""

    model_config = ConfigDict(from_attributes=True)

    source: str = Field(description="Agency, or `ALL`.")
    status: str = Field(
        description="'active', 'inactive', or 'unknown'. CPSC and NHTSA have no status, so they "
        "are 'unknown'."
    )
    event_count: int


class FirmLeaderRow(BaseModel):
    """A row of the most-recalled-firms leaderboard."""

    model_config = ConfigDict(from_attributes=True)

    firm_id: str = Field(description="A firm's id; use with `GET /firms/{firm_id}`.")
    canonical_name: str
    event_count: int = Field(description="Total distinct recalls for the firm (all agencies).")
    active_recalls: int = Field(description="Currently active recalls (FDA, USDA, USCG only).")
    product_count: int = Field(description="Distinct recalled products for this firm.")
    event_count_rank: int = Field(description="Rank by total recalls (1 = most recalled).")
    first_recall_at: datetime | None = None
    last_recall_at: datetime | None = None


class GeographyCount(BaseModel):
    """Per-state recall counts, by distribution or firm-registration, plus an ``ALL`` rollup."""

    model_config = ConfigDict(from_attributes=True)

    geography_basis: str = Field(
        description=(
            "'distribution' (where the product went; FDA/USDA) or 'firm_registration' (where the "
            "firm is registered; USDA/USCG/FDA). These answer different questions and are not "
            "interchangeable."
        )
    )
    source: str = Field(description="Agency, or `ALL`.")
    state_code: str = Field(description="Two-letter US state or territory code.")
    recall_count: int = Field(
        description=(
            "Recalls touching this state. A recall is counted in every state it touches, so "
            "per-state counts add up to more than the total."
        )
    )


class CountryCount(BaseModel):
    """Per-country recall counts for distribution (FDA and USDA), plus an ``ALL`` rollup."""

    model_config = ConfigDict(from_attributes=True)

    source: str = Field(description="Agency (FDA or USDA), or `ALL`.")
    country_code: str = Field(description="Two-letter country code (including a derived 'US').")
    recall_count: int = Field(
        description=(
            "Recalls distributed to this country. A recall sold in the US and abroad counts once "
            "per country, so per-country counts add up to more than the total."
        )
    )


class UnitsRow(BaseModel):
    """Units recalled per agency, unit type, and month. Not comparable across agencies."""

    model_config = ConfigDict(from_attributes=True)

    source: str = Field(
        description="NHTSA and USCG report units affected; FDA and USDA report quantity. No `ALL` "
        "rollup."
    )
    unit_category: str = Field(
        description=(
            "'count', 'weight', 'volume', or 'grouping'. Keeps incomparable units apart; never add "
            "across categories or agencies."
        )
    )
    period: date = Field(description="Start of the month.")
    recalls_with_units: int
    total_units: float = Field(
        description="Sum of the per-recall amounts (a measure of recall size, not a count of "
        "unique items)."
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
