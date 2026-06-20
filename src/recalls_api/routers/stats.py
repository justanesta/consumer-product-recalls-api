"""``GET /stats/*`` — read-through aggregate endpoints over the gold ``fct_*`` marts (dashboards).

Small pre-aggregates: each returns a typed ``list`` (``/stats/overview`` a single object); no keyset
pagination. Caching / CORS / rate-limit / the error envelope are inherited from the app. An invalid
``grain`` / ``basis`` / ``source`` enum is a free 422.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.errors import LIST_ERRORS
from recalls_api.models.common import Source
from recalls_api.models.stats import (
    ClassificationCount,
    CountryCount,
    FirmLeaderRow,
    GeographyBasis,
    GeographyCount,
    Grain,
    MonthlyTrendPoint,
    PeriodCount,
    StatsOverview,
    StatsSource,
    StatusCount,
    UnitsRow,
)
from recalls_api.queries import stats as q

router = APIRouter(prefix="/stats", tags=["stats"])

_SourceParam = Annotated[
    StatsSource | None,
    Query(
        description="Filter to one agency, or `ALL` for the all-agency rollup where available. "
        "Omit to get every row; an agency with no data for this stat returns an empty list."
    ),
]


async def _rows[M: BaseModel](conn: AsyncConnection, stmt: Select, model: type[M]) -> list[M]:
    result = await conn.execute(stmt)
    return [model.model_validate(dict(r)) for r in result.mappings()]


@router.get(
    "/overview",
    response_model=StatsOverview,
    responses=LIST_ERRORS,
    summary="Headline KPIs: total recalls, distinct firms, sources covered, last gold rebuild.",
)
async def overview(conn: Annotated[AsyncConnection, Depends(deps.get_conn)]) -> StatsOverview:
    row = (await conn.execute(q.overview_stmt())).mappings().one()
    return StatsOverview(
        total_recalls=row["total_recalls"],
        distinct_firms=row["distinct_firms"],
        last_rebuilt_at=row["last_rebuilt_at"],
        sources=[s.value for s in Source],
    )


@router.get(
    "/recalls-by-period",
    response_model=list[PeriodCount],
    responses=LIST_ERRORS,
    summary="Recall counts per period (month/week/year) per source + 'ALL' rollup.",
    description=(
        "Recall counts per period (month, week, or year) for each agency, plus an `ALL` rollup. "
        "Periods are dated by when each recall was first announced, falling back to its publish "
        "date when no announcement date is on record, so counts can differ from a publish-date "
        "view."
    ),
)
async def recalls_by_period(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    grain: Annotated[Grain, Query(description="Time grain: month | week | year.")] = Grain.MONTH,
    source: _SourceParam = None,
) -> list[PeriodCount]:
    return await _rows(conn, q.by_period_stmt(grain, source), PeriodCount)


@router.get(
    "/monthly-trend",
    response_model=list[MonthlyTrendPoint],
    responses=LIST_ERRORS,
    summary="Per-source monthly trend with rolling averages + year-over-year change.",
    description=(
        "Per-agency monthly counts with rolling averages and year-over-year change. Months are "
        "dated by when each recall was first announced (or its publish date when none is on "
        "record)."
    ),
)
async def monthly_trend(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    source: _SourceParam = None,
) -> list[MonthlyTrendPoint]:
    return await _rows(conn, q.monthly_trend_stmt(source), MonthlyTrendPoint)


@router.get(
    "/by-classification",
    response_model=list[ClassificationCount],
    responses=LIST_ERRORS,
    summary="Recall counts by source-native classification + risk_level (+ 'ALL').",
)
async def by_classification(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    source: _SourceParam = None,
) -> list[ClassificationCount]:
    return await _rows(conn, q.by_classification_stmt(source), ClassificationCount)


@router.get(
    "/status",
    response_model=list[StatusCount],
    responses=LIST_ERRORS,
    summary="Active/inactive/unknown recall counts per source (+ 'ALL').",
)
async def status(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    source: _SourceParam = None,
) -> list[StatusCount]:
    return await _rows(conn, q.status_stmt(source), StatusCount)


@router.get(
    "/firm-leaderboard",
    response_model=list[FirmLeaderRow],
    responses=LIST_ERRORS,
    summary="Most-recalled firms, ranked (top-N).",
)
async def firm_leaderboard(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    limit: Annotated[int, Query(ge=1, le=100, description="Top-N firms (1-100).")] = 20,
) -> list[FirmLeaderRow]:
    return await _rows(conn, q.firm_leaderboard_stmt(limit), FirmLeaderRow)


@router.get(
    "/by-geography",
    response_model=list[GeographyCount],
    responses=LIST_ERRORS,
    summary="Per-state recall counts; basis = distribution | firm_registration (+ 'ALL').",
)
async def by_geography(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    basis: Annotated[
        GeographyBasis,
        Query(description="distribution | firm_registration (different questions, not a toggle)."),
    ] = GeographyBasis.DISTRIBUTION,
    source: _SourceParam = None,
) -> list[GeographyCount]:
    return await _rows(conn, q.by_geography_stmt(basis, source), GeographyCount)


@router.get(
    "/by-country",
    response_model=list[CountryCount],
    responses=LIST_ERRORS,
    summary="Per-distribution-country recall counts (FDA/USDA + 'ALL').",
)
async def by_country(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    source: _SourceParam = None,
) -> list[CountryCount]:
    return await _rows(conn, q.by_country_stmt(source), CountryCount)


@router.get(
    "/units",
    response_model=list[UnitsRow],
    responses=LIST_ERRORS,
    summary="Units recalled per agency and unit type, by month (not comparable across agencies).",
    description=(
        "Units recalled per agency and unit type, by month. Units come in incomparable kinds "
        "(counts, weight, volume), so never add them across kinds or agencies. Months are dated by "
        "when each recall was first announced (or its publish date when none is on record)."
    ),
)
async def units(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    source: _SourceParam = None,
) -> list[UnitsRow]:
    return await _rows(conn, q.units_stmt(source), UnitsRow)
