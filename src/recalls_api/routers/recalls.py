"""``GET /recalls`` (list + filter, keyset) and ``GET /recalls/{source}/{recall_id}`` (detail)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.errors import ITEM_ERRORS, LIST_ERRORS, InvalidParameter, ResourceNotFound
from recalls_api.models.common import Page, Source
from recalls_api.models.recalls import RecallDetail, RecallSummary
from recalls_api.pagination import Cursor, build_page, slice_page
from recalls_api.queries import recalls as q

router = APIRouter(prefix="/recalls", tags=["recalls"])

_LIST_DESC = (
    "Recalls across CPSC, FDA, USDA, NHTSA, USCG, newest first (`published_at DESC`), keyset "
    "(seek) paginated — pass the previous page's `next_cursor` back as `cursor`. Caveats: "
    "`classification` is source-native (not unified); `is_active` is tri-state, so CPSC/NHTSA "
    "(`null`) match neither `true` nor `false`; deep UNFILTERED paging is a full sort (only "
    "`(source, published_at)` is indexed) — add `?source=` for index-backed paging; `firm` is an "
    "unindexed substring convenience filter. Total is omitted unless `with_total=true`."
)
_DETAIL_DESC = (
    "The complete record for one recall, by issuing agency + that agency's native id "
    "(e.g. `CPSC/24-001`). The source is accepted case-insensitively. Field caveats: "
    "`classification`/`risk_level`/`lifecycle_status` are source-native; `is_active` is `null` for "
    "CPSC/NHTSA; `distribution_states` is agency prose (a scalar string), distinct from the parsed "
    "`distribution_state_codes`."
)


@router.get(
    "",
    response_model=Page[RecallSummary],
    responses=LIST_ERRORS,
    summary="List recalls (newest first), with filters and keyset pagination.",
    description=_LIST_DESC,
)
async def list_recalls(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    filters: Annotated[deps.RecallFilters, Depends(deps.recall_filters)],
    page: Annotated[deps.PaginationParams, Depends(deps.pagination_params)],
) -> Page[RecallSummary]:
    rows = list((await conn.execute(q.list_stmt(filters, page.cursor, page.limit))).mappings())
    page_rows, has_next = slice_page(rows, page.limit)
    next_cursor = (
        Cursor(
            (page_rows[-1]["published_at"].isoformat(), page_rows[-1]["recall_event_id"])
        ).encode()
        if has_next and page_rows
        else None
    )
    total = None
    if page.with_total:
        total = (await conn.execute(q.list_count_stmt(filters))).scalar_one()
    items = [RecallSummary.model_validate(dict(r)) for r in page_rows]
    return build_page(items, limit=page.limit, next_cursor=next_cursor, total=total)


@router.get(
    "/{source}/{recall_id}",
    response_model=RecallDetail,
    responses=ITEM_ERRORS,
    summary="Fetch one recall's full record by its source + native recall id.",
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
    row = (await conn.execute(q.detail_stmt(src.value, recall_id))).mappings().one_or_none()
    if row is None:
        raise ResourceNotFound(f"no recall for {src.value}/{recall_id}")
    return RecallDetail.model_validate(dict(row))
