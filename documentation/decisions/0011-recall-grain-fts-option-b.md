# 0011 - Recall-grain full-text search (Option B): search_vector on mart_recall_summary, ts_rank_cd weighting

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

## Context

Users need keyword search over recalls, not just structured dimension filters. Two implementation options existed:

**Option A — reuse `mart_product_search` (product-grain, DISTINCT ON).**
Roll up `mart_product_search` rows to recall-grain via `DISTINCT ON (recall_event_id)` before ranking. Problems: the rank keyset must be applied after deduplication, making the seek-WHERE awkward and non-deterministic under ties; any recall with zero product rows is silently excluded; and the result shape is product-grain — a mismatch for a caller who wants one recall per hit with a link to `GET /recalls/{source}/{recall_id}`.

**Option B — first-class `search_vector` tsvector on `mart_recall_summary`.**
The upstream pipeline gold-readiness work (G1 2026-06-15) adds a `search_vector tsvector` column to `mart_recall_summary` with a `GIN` index and `setweight` buckets: `title = A`, `brand/product = B`, `cause = C`, `harm = D`. A recall-level vector is dedup-free, covers product-less recalls, and maps cleanly to the recall-grain list endpoint. The API-side lift is small because `GET /products/search` already established the FTS builder pattern.

Option B was chosen. See also [recalls-search-api-plan.md](../../project_scope/recalls-search-api-plan.md) for the original plan, and the pipeline ADR 0042 for the gold read-contract these mart shapes belong to.

## Decision

1. **Endpoint:** `GET /recalls/search` is declared in `routers/recalls.py` before `/{source}/{recall_id}` to prevent path ambiguity.

2. **Match predicate:** `search_vector @@ websearch_to_tsquery('english', :q)`. `websearch_to_tsquery` is injection-safe and never raises on syntactically bad input. The `'english'` regconfig is passed as `sa.literal_column("'english'")`, not a bound param — the `regconfig` overload requires a SQL literal; a bound param resolves to the two-argument `(text, text)` overload, which does not exist and would raise at runtime. (`queries/recalls.py:191–194`)

3. **Rank:** `ts_rank_cd(_RANK_WEIGHTS, search_vector, tsquery)` where `_RANK_WEIGHTS = sa.literal_column("'{0.1,0.2,0.4,1.0}'::float4[]")`. These weights map directly to the gold `setweight` buckets: `A=1.0 (title) > B=0.4 (brand/product) > C=0.2 (cause) > D=0.1 (harm)`. They match `ts_rank_cd`'s built-in defaults, so the query is correct out of the box and the weights can be re-tuned at query time without any gold rebuild. (`queries/recalls.py:184–188`)

4. **Keyset cursor shape:** `(rank: float, recall_event_id: str)` encoded as a base64url 2-tuple. Ranked sort uses `rank DESC, recall_event_id ASC` with the `rank_keyset_where()` seek-WHERE from `pagination.py`. (`routers/recalls.py:95–96`)

5. **Filter surface:** all `RecallFilters` (source, date ranges, `distribution_scope`, `distribution_state`, `distribution_country`, `lifecycle_status`, `source_recall_id`, `firm`) AND-in via the shared `recalls_predicates()` call — the same filter dep as `GET /recalls`.

6. **Response model:** `Page[RecallSearchHit]`, where `RecallSearchHit(RecallSummary)` adds one field: `rank: float`. (`models/recalls.py:42–47`)

## Consequences

**Accepted tradeoffs:**

- The GIN index backs the `@@` match (filter phase) but not the `ts_rank_cd ORDER BY` (sort phase). The sort is over the matched set, not the full corpus, making deep pagination O(matched set). At the expected corpus size this is acceptable; the OpenAPI `_SEARCH_DESC` string documents this honestly (`routers/recalls.py:39–46`).
- Typo/fuzzy search is explicitly not supported. `pg_trgm` is absent from Neon (pipeline ADR 0037 excluded it during firm-resolution work; GIN tsvector is the house standard). This is documented in the endpoint description and in `main.py`'s `_DESCRIPTION` block.
- The `rank` float is JSON-safe and round-trips correctly through the base64url cursor codec. Rank values are not comparable across queries or rebuilds.

**Benefits:**

- Recall-grain result set with no deduplication overhead; product-less recalls are included.
- All existing dimension filters AND-in for free with zero additional code — the filter dep is shared.
- The `setweight` tuning knobs live in the gold pipeline (not in query code), keeping the API's ranking weights separate from the gold schema definition.
