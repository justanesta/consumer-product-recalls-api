"""Shared FastAPI dependencies.

``get_conn`` is re-exported as the single overridable symbol — routers depend on ``deps.get_conn``
so tests swap the DB with one override. ``pagination_params`` and ``recall_filters`` are
sub-dependencies so each route signature stays clean and validation lives in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import BeforeValidator, StringConstraints

from recalls_api.db import get_conn as get_conn  # re-export; tests override deps.get_conn
from recalls_api.models.common import DistributionScope, Source
from recalls_api.pagination import Cursor
from recalls_api.settings import Settings, get_settings

__all__ = [
    "PaginationParams",
    "RecallFilters",
    "SourceList",
    "get_conn",
    "pagination_params",
    "recall_filters",
    "split_query_list",
]


def split_query_list(value: Any) -> Any:
    """Split comma-bearing query elements so ``?x=A,B`` is equivalent to ``?x=A&x=B`` (repeated).

    FastAPI collects a multi-value query param into a list before validation; this runs as a
    ``BeforeValidator`` on that list and expands any element that itself contains commas (before
    enum/length coercion of the elements). Safe because none of the multi-value filters' legal
    values contain a comma — that is exactly why ``firm``/date filters stay single-value. An absent
    param (``None``) passes straight through.
    """
    if not isinstance(value, list):
        return value
    out: list[Any] = []
    for item in value:
        if isinstance(item, str) and "," in item:
            out.extend(part.strip() for part in item.split(",") if part.strip())
        else:
            out.append(item)
    return out


# Per-element constraints for the multi-value filters (applied to each element, not the list).
_Str64 = Annotated[str, StringConstraints(max_length=64)]
_Code2 = Annotated[str, StringConstraints(min_length=2, max_length=2)]

# Comma-tolerant multi-value query types. Each declares an OpenAPI array param (repeated form) AND
# accepts a single comma-separated value via ``split_query_list``. None when the param is absent.
SourceList = Annotated[list[Source] | None, BeforeValidator(split_query_list)]
_ClassificationList = Annotated[list[_Str64] | None, BeforeValidator(split_query_list)]
_ScopeList = Annotated[list[DistributionScope] | None, BeforeValidator(split_query_list)]
_LifecycleList = Annotated[list[_Str64] | None, BeforeValidator(split_query_list)]
_CodeList = Annotated[list[_Code2] | None, BeforeValidator(split_query_list)]


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
    # Multi-value categorical filters: a list means any-of (OR) within the field; different fields
    # still AND. None/empty = unset. Geo lists use array overlap (&&); the rest use IN.
    source: list[Source] | None
    classification: list[str] | None
    is_active: bool | None
    published_after: date | None
    published_before: date | None
    firm: str | None
    # Dimension filters (defaulted so existing positional constructions stay valid).
    distribution_scope: list[DistributionScope] | None = None
    lifecycle_status: list[str] | None = None
    announced_after: date | None = None
    announced_before: date | None = None
    source_recall_id: str | None = None
    # Geo array-overlap filters (GIN-backed upstream).
    distribution_state: list[str] | None = None
    distribution_country: list[str] | None = None


def recall_filters(
    source: Annotated[
        SourceList,
        Query(description="Issuing agency; repeat or comma-separate for any-of (OR)."),
    ] = None,
    classification: Annotated[
        _ClassificationList,
        Query(
            description="EXACT source-native classification(s); repeat/comma-separate for any-of."
        ),
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
    distribution_scope: Annotated[
        _ScopeList,
        Query(
            description="Gold distribution scope(s); repeat/comma-separate for any-of (422 on a "
            "bad value)."
        ),
    ] = None,
    lifecycle_status: Annotated[
        _LifecycleList,
        Query(
            description="EXACT source-native status(es); repeat/comma-separate for any-of. "
            "Null for CPSC/NHTSA (excludes those rows).",
        ),
    ] = None,
    announced_after: Annotated[
        date | None,
        Query(description="announced_at >= start of that day (UTC); null-announced rows excluded."),
    ] = None,
    announced_before: Annotated[
        date | None,
        Query(
            description="Inclusive of the whole announced_before day; nulls excluded.",
        ),
    ] = None,
    source_recall_id: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=128,
            description="EXACT agency-native id; unique only when combined with source.",
        ),
    ] = None,
    distribution_state: Annotated[
        _CodeList,
        Query(
            description="USPS 2-letter code(s); recalls distributed to ANY (FDA/USDA only). "
            "Repeat/comma-separate for any-of.",
        ),
    ] = None,
    distribution_country: Annotated[
        _CodeList,
        Query(
            description="ISO alpha-2 code(s); FOREIGN distribution only ('US' excluded by design). "
            "Repeat/comma-separate for any-of.",
        ),
    ] = None,
) -> RecallFilters:
    return RecallFilters(
        source=source,
        classification=classification,
        is_active=is_active,
        published_after=published_after,
        published_before=published_before,
        firm=firm,
        distribution_scope=distribution_scope,
        lifecycle_status=lifecycle_status,
        announced_after=announced_after,
        announced_before=announced_before,
        source_recall_id=source_recall_id,
        distribution_state=distribution_state,
        distribution_country=distribution_country,
    )
