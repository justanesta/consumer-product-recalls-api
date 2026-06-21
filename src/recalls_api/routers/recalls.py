"""``GET /recalls`` (list + filter, keyset) and ``GET /recalls/{source}/{recall_id}`` (detail)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.errors import ITEM_ERRORS, LIST_ERRORS, InvalidParameter, ResourceNotFound
from recalls_api.models.common import Page, Source
from recalls_api.models.recalls import RecallDetail, RecallSearchHit, RecallSummary
from recalls_api.pagination import Cursor, build_page, slice_page
from recalls_api.queries import recalls as rq

router = APIRouter(prefix="/recalls", tags=["recalls"])

_LIST_DESC = (
    "Recalls across all five agencies, newest first (by `event_date` — when each recall was "
    "announced, falling back to its published date for the few with no announcement date), with "
    "cursor pagination. Pass a page's `next_cursor` back as `cursor` for the next page. Filters "
    "combine with AND across fields; the categorical ones (`source`, "
    "`classification`, `lifecycle_status`, `distribution_scope`, `distribution_state`, "
    "`distribution_country`) accept multiple values: repeat the param or comma-separate them "
    "(`?source=CPSC,FDA`) to match any of them within that field. Each filter notes its own "
    "caveats below. The total count is omitted unless you pass `with_total=true`."
)
_DETAIL_DESC = (
    "The full record for one recall, identified by its issuing agency and that agency's own recall "
    "id (e.g. `CPSC/24-001`). The agency name is case-insensitive. A couple of field notes: "
    "`classification`, `risk_level`, and `lifecycle_status` use each agency's own vocabulary; "
    "`is_active` is `null` for CPSC and NHTSA; and `distribution_states` is the agency's free-text "
    "prose, separate from the parsed `distribution_state_codes`."
)
_SEARCH_DESC = (
    "Keyword search over recalls, full-text across each recall's title, product names, firm, and "
    "narrative, ranked by relevance (`rank`). Matches whole words and prefixes only; no fuzzy or "
    "typo search. Unlike `/products/search` (which is product-level and also does identifier and "
    "UPC lookups via `?upc=`), this returns one row per recall, each linking to its detail route. "
    "All `/recalls` filters apply here too."
)


@router.get(
    "",
    response_model=Page[RecallSummary],
    responses=LIST_ERRORS,
    summary="List recalls, newest first, with filters and pagination.",
    description=_LIST_DESC,
)
async def list_recalls(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    filters: Annotated[deps.RecallFilters, Depends(deps.recall_filters)],
    page: Annotated[deps.PaginationParams, Depends(deps.pagination_params)],
) -> Page[RecallSummary]:
    rows = list((await conn.execute(rq.list_stmt(filters, page.cursor, page.limit))).mappings())
    page_rows, has_next = slice_page(rows, page.limit)
    next_cursor = (
        Cursor(
            (page_rows[-1]["event_date"].isoformat(), page_rows[-1]["recall_event_id"]), "e"
        ).encode()
        if has_next and page_rows
        else None
    )
    total = None
    if page.with_total:
        total = (await conn.execute(rq.list_count_stmt(filters))).scalar_one()
    items = [RecallSummary.model_validate(dict(r)) for r in page_rows]
    return build_page(items, limit=page.limit, next_cursor=next_cursor, total=total)


@router.get(
    "/search",
    response_model=Page[RecallSearchHit],
    responses=LIST_ERRORS,
    summary="Search recalls by keyword, with the same filters.",
    description=_SEARCH_DESC,
)
async def search_recalls(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    filters: Annotated[deps.RecallFilters, Depends(deps.recall_filters)],
    page: Annotated[deps.PaginationParams, Depends(deps.pagination_params)],
    q: Annotated[
        str, Query(min_length=2, max_length=200, description="Keywords (Postgres websearch).")
    ],
) -> Page[RecallSearchHit]:
    stmt = rq.search_stmt(filters, q, page.cursor, page.limit)
    rows = list((await conn.execute(stmt)).mappings())
    page_rows, has_next = slice_page(rows, page.limit)
    next_cursor = (
        Cursor((page_rows[-1]["rank"], page_rows[-1]["recall_event_id"]), "r").encode()
        if has_next and page_rows
        else None
    )
    total = None
    if page.with_total:
        total = (await conn.execute(rq.search_count_stmt(filters, q))).scalar_one()
    items = [RecallSearchHit.model_validate(dict(r)) for r in page_rows]
    return build_page(items, limit=page.limit, next_cursor=next_cursor, total=total)


@router.get(
    "/{source}/{recall_id}",
    response_model=RecallDetail,
    responses=ITEM_ERRORS,
    summary="Fetch one recall's full record by agency and recall id.",
    description=_DETAIL_DESC,
)
async def get_recall(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    source: Annotated[str, Path(description="Issuing agency (accepted case-insensitively).")],
    recall_id: Annotated[
        str, Path(min_length=1, max_length=128, description="The agency-native recall id.")
    ],
) -> RecallDetail:
    # Declared as str (not Source) so a lowercase source is normalized, not rejected (decision 10).
    try:
        src = Source(source.upper())
    except ValueError as exc:
        valid = ", ".join(s.value for s in Source)
        raise InvalidParameter(f"unknown source {source!r}; expected one of: {valid}") from exc
    row = (await conn.execute(rq.detail_stmt(src.value, recall_id))).mappings().one_or_none()
    if row is None:
        raise ResourceNotFound(f"no recall for {src.value}/{recall_id}")
    return RecallDetail.model_validate(dict(row))
