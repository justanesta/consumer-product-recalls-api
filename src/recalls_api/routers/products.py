"""``GET /products/search`` — keyword FTS, exact identifier (hin/model), or recall-level UPC."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.errors import LIST_ERRORS, InvalidParameter
from recalls_api.models.common import Page
from recalls_api.models.products import ProductSearchHit
from recalls_api.pagination import Cursor, build_page, slice_page
from recalls_api.queries import products as pq

router = APIRouter(prefix="/products", tags=["products"])

_DESC = (
    'Search recalled products — "is my product recalled?". Keyword (`q`) is a full-text search '
    "over product name, description, recall title, and firm, ranked by relevance (`rank`); whole "
    "words and prefixes only, no fuzzy or typo search. `hin` and `model` are exact-match lookups. "
    "`upc` matches at the recall level, so each hit carries `upc_is_recall_level: true` — a miss "
    "means no recall lists that UPC, not that the product is safe. Supply at least one of `q`, "
    "`hin`, `model`, or `upc` (otherwise 422); if several are given, `q` wins, then `hin`/`model`, "
    "then `upc`. `source` narrows any of these and accepts multiple values (repeat or "
    "comma-separate)."
)


def _encode_cursor(row: dict, sort: str) -> str:
    if sort == "rank":
        return Cursor((row["rank"], row["recall_product_id"]), "r").encode()
    return Cursor((row["published_at"].isoformat(), row["recall_product_id"]), "p").encode()


@router.get(
    "/search",
    response_model=Page[ProductSearchHit],
    responses=LIST_ERRORS,
    summary="Search recalled products by keyword (full-text) or exact identifier.",
    description=_DESC,
)
async def search_products(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    page: Annotated[deps.PaginationParams, Depends(deps.pagination_params)],
    q: Annotated[
        str | None,
        Query(min_length=2, max_length=200, description="Keywords to search for."),
    ] = None,
    hin: Annotated[
        str | None, Query(max_length=64, description="Exact Hull ID (USCG boats).")
    ] = None,
    model: Annotated[str | None, Query(max_length=128, description="Exact product model.")] = None,
    upc: Annotated[
        str | None,
        Query(
            max_length=32,
            description=(
                "Look up recalled products by 12-digit UPC barcode. Matches at the recall level — "
                "UPC data is sparse and comes only from CPSC (about 5% of CPSC recalls; absent for "
                "FDA, USDA, NHTSA, and USCG). A miss means no recall lists that UPC, **not** that "
                "the product is safe."
            ),
            examples=["012345678905"],
        ),
    ] = None,
    source: Annotated[
        deps.SourceList,
        Query(description="Optional agency filter; repeat/comma-separate to match any of several."),
    ] = None,
) -> Page[ProductSearchHit]:
    # Precedence q > identifier > upc; require at least one selector (422 otherwise).
    stmt: Select
    count_stmt: Select
    match (q, hin, model, upc):
        case (None, None, None, None):
            raise InvalidParameter("provide at least one of: q, hin, model, upc")
        case (str() as text, _, _, _):
            stmt = pq.fts_stmt(text, page.cursor, page.limit, source)
            count_stmt = pq.fts_count_stmt(text, source)
            sort = "rank"
        case (None, h, m, _) if h is not None or m is not None:
            stmt = pq.identifier_stmt(h, m, page.cursor, page.limit, source)
            count_stmt = pq.identifier_count_stmt(h, m, source)
            sort = "published_at"
        case (None, None, None, str() as code):
            stmt = pq.upc_stmt(code, page.cursor, page.limit, source)
            count_stmt = pq.upc_count_stmt(code, source)
            sort = "published_at"
        case _:  # pragma: no cover — defensive; the cases above are exhaustive for the param space
            raise InvalidParameter("unsupported combination of search parameters")

    rows = list((await conn.execute(stmt)).mappings())
    page_rows, has_next = slice_page(rows, page.limit)
    next_cursor = _encode_cursor(dict(page_rows[-1]), sort) if has_next and page_rows else None
    total = (await conn.execute(count_stmt)).scalar_one() if page.with_total else None
    items = [ProductSearchHit.model_validate(dict(r)) for r in page_rows]
    return build_page(items, limit=page.limit, next_cursor=next_cursor, total=total)
