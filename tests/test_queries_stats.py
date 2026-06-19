"""Unit tests for the /stats/* query builders — compile + assert binds/tables (no DB)."""

from __future__ import annotations

from recalls_api.models.stats import GeographyBasis, Grain, StatsSource
from recalls_api.queries import stats as q


def _sql(stmt: object) -> str:
    return str(stmt.compile())  # type: ignore[attr-defined]


def test_by_period_picks_table_per_grain() -> None:
    assert "fct_recalls_by_month" in _sql(q.by_period_stmt(Grain.MONTH, None))
    assert "fct_recalls_by_week" in _sql(q.by_period_stmt(Grain.WEEK, None))
    assert "fct_recalls_by_year" in _sql(q.by_period_stmt(Grain.YEAR, None))


def test_source_filter_binds_and_is_omitted_when_none() -> None:
    stmt = q.by_period_stmt(Grain.MONTH, StatsSource.FDA)
    assert stmt.compile().params["source"] == "FDA"
    assert "WHERE" not in _sql(q.by_period_stmt(Grain.MONTH, None)).upper()


def test_by_classification_projects_native_columns() -> None:
    s = _sql(q.by_classification_stmt(None))
    assert "classification" in s and "risk_level" in s and "event_count" in s


def test_firm_leaderboard_orders_by_rank_and_limits() -> None:
    stmt = q.firm_leaderboard_stmt(5)
    assert "event_count_rank" in _sql(stmt)
    assert stmt.compile().params["limit"] == 5


def test_geography_binds_basis() -> None:
    stmt = q.by_geography_stmt(GeographyBasis.DISTRIBUTION, None)
    assert stmt.compile().params["basis"] == "distribution"


def test_units_targets_units_table() -> None:
    assert "fct_units_recalled" in _sql(q.units_stmt(StatsSource.NHTSA))


def test_overview_reads_both_marts_and_gold_meta() -> None:
    s = _sql(q.overview_stmt())
    assert "mart_recall_summary" in s and "mart_firm_profile" in s and "gold_meta" in s
