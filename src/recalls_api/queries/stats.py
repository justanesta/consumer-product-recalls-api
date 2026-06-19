"""Builders for the ``/stats/*`` read-through endpoints over the gold ``fct_*`` aggregate marts.

Pure: build statements, never execute. The ``fct_*`` are small pre-aggregates, so these are plain
ordered SELECTs (no keyset/pagination). Column names mirror each gold model's final SELECT
(confirmed against ``_gold.yml`` + the ``fct_*`` SQL, 2026-06-19). An out-of-domain ``source``
simply yields an empty result.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Select
from sqlalchemy.sql.elements import ColumnElement

from recalls_api.models.stats import GeographyBasis, Grain, StatsSource

# --- fct_* table literals (only the columns the API projects) ---

_BY_PERIOD: dict[Grain, sa.TableClause] = {
    grain: sa.table(
        name,
        sa.column("period", sa.Date),
        sa.column("source", sa.Text),
        sa.column("event_count", sa.BigInteger),
    )
    for grain, name in (
        (Grain.MONTH, "fct_recalls_by_month"),
        (Grain.WEEK, "fct_recalls_by_week"),
        (Grain.YEAR, "fct_recalls_by_year"),
    )
}

fct_monthly_trend = sa.table(
    "fct_recalls_monthly_trend",
    sa.column("month", sa.Date),
    sa.column("source", sa.Text),
    sa.column("event_count", sa.BigInteger),
    sa.column("rolling_3mo_avg", sa.Numeric),
    sa.column("rolling_12mo_avg", sa.Numeric),
    sa.column("event_count_year_ago", sa.BigInteger),
    sa.column("yoy_pct_change", sa.Numeric),
)

fct_classification = sa.table(
    "fct_recalls_by_classification",
    sa.column("source", sa.Text),
    sa.column("classification", sa.Text),
    sa.column("risk_level", sa.Text),
    sa.column("event_count", sa.BigInteger),
)

fct_status = sa.table(
    "fct_recall_status",
    sa.column("source", sa.Text),
    sa.column("status", sa.Text),
    sa.column("event_count", sa.BigInteger),
)

fct_firm = sa.table(
    "fct_recalls_by_firm",
    sa.column("firm_id", sa.Text),
    sa.column("canonical_name", sa.Text),
    sa.column("event_count", sa.BigInteger),
    sa.column("active_recalls", sa.BigInteger),
    sa.column("product_count", sa.BigInteger),
    sa.column("first_recall_at", sa.TIMESTAMP(timezone=True)),
    sa.column("last_recall_at", sa.TIMESTAMP(timezone=True)),
    sa.column("event_count_rank", sa.BigInteger),
)

fct_geography = sa.table(
    "fct_recalls_by_geography",
    sa.column("geography_basis", sa.Text),
    sa.column("source", sa.Text),
    sa.column("state_code", sa.Text),
    sa.column("recall_count", sa.BigInteger),
)

fct_country = sa.table(
    "fct_recalls_by_country",
    sa.column("source", sa.Text),
    sa.column("country_code", sa.Text),
    sa.column("recall_count", sa.BigInteger),
)

fct_units = sa.table(
    "fct_units_recalled",
    sa.column("source", sa.Text),
    sa.column("unit_category", sa.Text),
    sa.column("period", sa.Date),
    sa.column("recalls_with_units", sa.BigInteger),
    sa.column("total_units", sa.Numeric),
    sa.column("avg_units_per_recall", sa.Numeric),
    sa.column("max_units", sa.Numeric),
)

# Minimal literals for the API-computed overview (counts + the one-row build stamp).
_mart_recall_summary = sa.table("mart_recall_summary", sa.column("recall_event_id", sa.Text))
_mart_firm_profile = sa.table("mart_firm_profile", sa.column("firm_id", sa.Text))
_gold_meta = sa.table("gold_meta", sa.column("rebuilt_at", sa.TIMESTAMP(timezone=True)))


def _source_eq(col: ColumnElement, source: StatsSource | None) -> ColumnElement[bool] | None:
    """Bind an equality on the source column, or None to omit the WHERE."""
    if source is None:
        return None
    return col == sa.bindparam("source", source.value)


def overview_stmt() -> Select:
    """One-round-trip KPI read: total recalls, distinct firms, last gold rebuild."""
    total = sa.select(sa.func.count()).select_from(_mart_recall_summary).scalar_subquery()
    firms = sa.select(sa.func.count()).select_from(_mart_firm_profile).scalar_subquery()
    rebuilt = sa.select(_gold_meta.c.rebuilt_at).limit(1).scalar_subquery()
    return sa.select(
        total.label("total_recalls"),
        firms.label("distinct_firms"),
        rebuilt.label("last_rebuilt_at"),
    )


def by_period_stmt(grain: Grain, source: StatsSource | None) -> Select:
    t = _BY_PERIOD[grain]
    stmt = sa.select(t.c.period, t.c.source, t.c.event_count)
    cond = _source_eq(t.c.source, source)
    if cond is not None:
        stmt = stmt.where(cond)
    return stmt.order_by(t.c.source, t.c.period)


def monthly_trend_stmt(source: StatsSource | None) -> Select:
    t = fct_monthly_trend
    stmt = sa.select(
        t.c.month,
        t.c.source,
        t.c.event_count,
        t.c.rolling_3mo_avg,
        t.c.rolling_12mo_avg,
        t.c.event_count_year_ago,
        t.c.yoy_pct_change,
    )
    cond = _source_eq(t.c.source, source)
    if cond is not None:
        stmt = stmt.where(cond)
    return stmt.order_by(t.c.source, t.c.month)


def by_classification_stmt(source: StatsSource | None) -> Select:
    t = fct_classification
    stmt = sa.select(t.c.source, t.c.classification, t.c.risk_level, t.c.event_count)
    cond = _source_eq(t.c.source, source)
    if cond is not None:
        stmt = stmt.where(cond)
    return stmt.order_by(t.c.source, t.c.event_count.desc())


def status_stmt(source: StatsSource | None) -> Select:
    t = fct_status
    stmt = sa.select(t.c.source, t.c.status, t.c.event_count)
    cond = _source_eq(t.c.source, source)
    if cond is not None:
        stmt = stmt.where(cond)
    return stmt.order_by(t.c.source, t.c.status)


def firm_leaderboard_stmt(limit: int) -> Select:
    t = fct_firm
    return (
        sa.select(
            t.c.firm_id,
            t.c.canonical_name,
            t.c.event_count,
            t.c.active_recalls,
            t.c.product_count,
            t.c.first_recall_at,
            t.c.last_recall_at,
            t.c.event_count_rank,
        )
        .order_by(t.c.event_count_rank.asc())
        .limit(sa.bindparam("limit", limit))
    )


def by_geography_stmt(basis: GeographyBasis, source: StatsSource | None) -> Select:
    t = fct_geography
    conds: list[ColumnElement[bool]] = [t.c.geography_basis == sa.bindparam("basis", basis.value)]
    src = _source_eq(t.c.source, source)
    if src is not None:
        conds.append(src)
    return (
        sa.select(t.c.geography_basis, t.c.source, t.c.state_code, t.c.recall_count)
        .where(*conds)
        .order_by(t.c.source, t.c.recall_count.desc())
    )


def by_country_stmt(source: StatsSource | None) -> Select:
    t = fct_country
    stmt = sa.select(t.c.source, t.c.country_code, t.c.recall_count)
    cond = _source_eq(t.c.source, source)
    if cond is not None:
        stmt = stmt.where(cond)
    return stmt.order_by(t.c.source, t.c.recall_count.desc())


def units_stmt(source: StatsSource | None) -> Select:
    t = fct_units
    stmt = sa.select(
        t.c.source,
        t.c.unit_category,
        t.c.period,
        t.c.recalls_with_units,
        t.c.total_units,
        t.c.avg_units_per_recall,
        t.c.max_units,
    )
    cond = _source_eq(t.c.source, source)
    if cond is not None:
        stmt = stmt.where(cond)
    return stmt.order_by(t.c.period.desc(), t.c.source, t.c.unit_category)
