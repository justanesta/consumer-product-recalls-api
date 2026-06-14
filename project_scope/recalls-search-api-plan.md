# Plan — `GET /recalls/search` (API side, Option B)

**Goal.** A recall-grain keyword endpoint: full-text search over recalls, ranked, that links each hit
to `GET /recalls/{source}/{recall_id}`. This is **Option B**: it reads a NEW recall-level
`search_vector` added to `mart_recall_summary` upstream — see the companion
`recalls-search-gold-plan.md`. It mirrors the already-shipped `GET /products/search` FTS path almost
verbatim, which is why the API-side lift is small (~1–2h) once the gold column lands.

> **Why B over A (reuse `mart_product_search`):** the product vector is *product*-grain — rolling it
> up to recalls needs `DISTINCT ON` + an awkward rank-keyset over a deduped set, and silently misses
> any recall with zero product rows. A first-class recall-level vector is index-backed, dedup-free,
> and correct for product-less recalls. Clean & right, per your call.

## Dependency / sequencing

Blocked on the gold change (recall-level `search_vector` tsvector + `GIN`). You can build and test
the API in parallel by adding the column to the test seed first (it's the same DDL) — the endpoint
doesn't care whether the column comes from dbt or the seed.

## Changes

### `queries/recalls.py`
- Add the FTS column handle (not selected, referenced in predicate/rank), exactly like products:
  ```python
  _search_vector = sa.literal_column("search_vector")  # tsvector on mart_recall_summary; GIN-indexed
  ```
- Add builders (mirror `products.fts_stmt` / `fts_count_stmt`, reusing the existing
  `recalls_predicates` so the same `source`/date filters AND-in):
  ```python
  def _tsquery(q: str):
      return sa.func.websearch_to_tsquery(sa.literal_column("'english'"), sa.bindparam("q", q))

  def search_stmt(filters, q, cursor, limit):
      tq = _tsquery(q)
      rank = sa.func.ts_rank_cd(_search_vector, tq).label("rank")
      stmt = sa.select(*_LIST_COLS, rank).where(_search_vector.op("@@")(tq), *recalls_predicates(filters))
      if cursor is not None:
          stmt = stmt.where(rank_keyset_where(cursor, rank, recall_summary.c.recall_event_id))
      return stmt.order_by(rank.desc(), recall_summary.c.recall_event_id.asc()).limit(limit + 1)

  def search_count_stmt(filters, q):
      tq = _tsquery(q)
      return sa.select(sa.func.count()).select_from(recall_summary).where(
          _search_vector.op("@@")(tq), *recalls_predicates(filters))
  ```
  `websearch_to_tsquery` is injection-safe and never raises on bad input. `'english'` must be a SQL
  literal (regconfig overload), not a bound param — same gotcha as products.

### `models/recalls.py`
- Add a thin hit model so the response is a list projection + relevance:
  ```python
  class RecallSearchHit(RecallSummary):
      rank: float = Field(description="ts_rank_cd relevance; higher = better. Not comparable across queries.")
  ```

### `routers/recalls.py`
- Add the route. **Declare it before** `/{source}/{recall_id}` for readability (segment counts already
  disambiguate `/recalls/search` from `/recalls/{source}/{recall_id}`, so it's not strictly required):
  ```python
  @router.get("/search", response_model=Page[RecallSearchHit], responses=LIST_ERRORS, ...)
  async def search_recalls(conn, filters: ... = Depends(deps.recall_filters), page: ...,
                           q: Annotated[str, Query(min_length=2, max_length=200)]):
      stmt = q_recalls.search_stmt(filters, q, page.cursor, page.limit)
      rows = list((await conn.execute(stmt)).mappings())
      page_rows, has_next = slice_page(rows, page.limit)
      next_cursor = Cursor((page_rows[-1]["rank"], page_rows[-1]["recall_event_id"])).encode() if has_next and page_rows else None
      total = (await conn.execute(q_recalls.search_count_stmt(filters, q))).scalar_one() if page.with_total else None
      items = [RecallSearchHit.model_validate(dict(r)) for r in page_rows]
      return build_page(items, limit=page.limit, next_cursor=next_cursor, total=total)
  ```
- `q` is required (≥2 chars) — distinguishes this from the filter-only `GET /recalls`.
- Reuse `deps.recall_filters` so `source` + date filters AND-in for free. (Whether to *also* surface
  the new `lifecycle_status`/`distribution_*`/`announced_at` filters here is a `gold-audit-charter.md`
  decision; the wiring is identical once those land on the filter dep.)

### OpenAPI description (honest caveats — match the products voice)
- Token/prefix FTS over title + firm + product names + narrative; **NO fuzzy/typo search** (no pg_trgm,
  ADR 0037). Ranked by `rank` (`ts_rank_cd`), not comparable across queries.
- Recall-grain (deduped), unlike `/products/search` which is product-grain.
- Relevance-ordered keyset is **not index-backed** (the GIN serves the `@@` match, not the sort); the
  sort is over the matched set. Same as products — fine at corpus scale.

## Tests (`tests/`)
- **Seed:** add `search_vector tsvector` to the `mart_recall_summary` DDL in `seed_gold.sql`, populate
  it with `to_tsvector('english', …)` on insert, and add a `GIN(search_vector)` index for parity with prod.
- **New `test_recalls_search.py`:** keyword match; rank ordering; `source` AND-filter; keyset
  pagination across pages; `q` too short → 422; no-match → empty page (not error); garbage/operator-y
  `q` is injection-safe (no 500). Mirror `tests/.../test_products_search` structure.
- **Contract:** regenerate `openapi.json` (`python -m recalls_api.export_openapi > openapi.json`) and
  let the drift test guard it.

## Open decisions
- Filters on search: start with `source` + `published_after`/`published_before` (cheap, AND-ed). Fold
  in the broader filter set (charter) when it lands.
- Limit ranking knobs (`setweight` weights) live in the **gold** vector definition, not here.
