"""Shared FastAPI dependencies.

``get_conn`` is re-exported as the single overridable symbol — routers depend on ``deps.get_conn``
so tests swap the DB with one override. ``pagination_params`` and ``recall_filters`` are
sub-dependencies so each route signature stays clean and validation lives in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, Query

from recalls_api.db import get_conn as get_conn  # re-export; tests override deps.get_conn
from recalls_api.models.common import Source
from recalls_api.pagination import Cursor
from recalls_api.settings import Settings, get_settings

__all__ = ["PaginationParams", "RecallFilters", "get_conn", "pagination_params", "recall_filters"]


@dataclass(slots=True)
class PaginationParams:
    limit: int
    cursor: Cursor | None
    with_total: bool


def pagination_params(
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=100, description="Page size (max 100).")] = 25,
    cursor: Annotated[
        str | None, Query(description="Opaque cursor from a prior next_cursor.")
    ] = None,
    with_total: Annotated[bool, Query(description="Also compute total (extra COUNT).")] = False,
) -> PaginationParams:
    return PaginationParams(
        limit=min(limit, settings.page_limit_max),
        cursor=Cursor.decode(cursor) if cursor else None,  # bad cursor -> BadCursor (400)
        with_total=with_total,
    )


@dataclass(slots=True)
class RecallFilters:
    source: Source | None
    classification: str | None
    is_active: bool | None
    published_after: date | None
    published_before: date | None
    firm: str | None


def recall_filters(
    source: Annotated[Source | None, Query(description="Filter by issuing agency.")] = None,
    classification: Annotated[
        str | None,
        Query(max_length=64, description="EXACT match on the source-native classification string."),
    ] = None,
    is_active: Annotated[
        bool | None,
        Query(description="Tri-state; CPSC/NHTSA carry null and match neither true nor false."),
    ] = None,
    published_after: Annotated[
        date | None, Query(description="Inclusive from the START of that calendar day.")
    ] = None,
    published_before: Annotated[
        date | None, Query(description="Inclusive of the ENTIRE published_before calendar day.")
    ] = None,
    firm: Annotated[
        str | None,
        Query(min_length=2, max_length=200, description="Case-insensitive substring (unindexed)."),
    ] = None,
) -> RecallFilters:
    return RecallFilters(source, classification, is_active, published_after, published_before, firm)
