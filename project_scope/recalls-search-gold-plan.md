# Plan — recall-level `search_vector` (pipeline / gold side, Option B)

**Repo:** `consumer-product-recalls` (NOT this one). **Branch:** `feature/pre-go-live-validation`
(the authoritative branch; `main` is behind). **This is a dbt change, not an Alembic migration.**

**Goal.** Add a recall-grain FTS `search_vector` (tsvector) + `GIN` index to `mart_recall_summary`,
so the API's `GET /recalls/search` (see `recalls-search-api-plan.md`) is an index-backed, dedup-free
keyword search at the recall grain. This is the clean counterpart to reusing the product-grain vector.

**Why it's cheap now.** Pre-go-live, no API clients exist, and only `fct_recalls_by_firm` reads
`mart_recall_summary` (and it doesn't touch a `search_vector`) — so this is **zero downstream
breakage**, same risk profile as the R5 rename. Free now, contract-affecting after the API ships.

## Changes (pipeline repo)

### 1. `dbt/models/gold/mart_recall_summary.sql` — add the column
Add a weighted tsvector so ranking favors the title/firm over deep narrative. Recommended composition
(tune during the audit; the API is agnostic to the exact weights):

```sql
,
setweight(to_tsvector('english', coalesce(title, '')), 'A')
|| setweight(to_tsvector('english',
       coalesce(primary_firm_name, '') || ' ' ||
       coalesce(array_to_string(product_names_text, ' '), '') || ' ' ||
       coalesce(array_to_string(models_text, ' '), '')), 'B')
|| setweight(to_tsvector('english',
       coalesce(recall_reason, '') || ' ' ||
       coalesce(corrective_action, '') || ' ' ||
       coalesce(consequence_of_defect, '') || ' ' ||
       coalesce(reason_category, '')), 'C')
  AS search_vector
```
- `product_names`/`models` are jsonb arrays in the mart; build the vector from the **text rollups**
  feeding them (the `array_agg` expressions before `to_jsonb`), or convert via
  `jsonb_array_elements_text` — whichever is cleaner in the existing model. The point: include product
  names + models so "is my <product> recalled?" keyword queries hit at recall grain.
- Result is **NOT NULL** (every coalesce is `''`), so a `not_null` test is valid.
- Mirror exactly how `mart_product_search.search_vector` is declared in its model — copy that pattern
  (it already uses `to_tsvector('english', …)` and a GIN index) for consistency and to inherit the
  ADR-0037 "no pg_trgm" posture (this is plain FTS, no conflict).

### 2. GIN index
Declare it the same way `mart_product_search` declares its `GIN(search_vector)` — dbt model
`config(indexes=[{'columns': ['search_vector'], 'type': 'gin'}])` (or the post-hook pattern that model
uses). Verify after build with `EXPLAIN ANALYZE` on a `WHERE search_vector @@ websearch_to_tsquery(...)`
query — expect a Bitmap Index Scan on the GIN, not a Seq Scan.

### 3. `dbt/models/gold/_gold.yml` — document + test
Add the `search_vector` column description ("FTS tsvector, GIN-indexed; built from title (A) + firm /
product names / models (B) + narrative (C); english config; no pg_trgm → token/prefix only") and a
`not_null` test.

### 4. Grants
`GRANT SELECT` on a table already covers new columns, so `recalls_readonly` needs nothing extra —
**unless** the role uses column-level grants. Confirm; re-grant the column if so.

### 5. Revalidation
- `dbt build -s mart_recall_summary+` (the mart + downstream), confirm `fct_recalls_by_firm` is
  unaffected (it doesn't read the column — same check R5 did).
- `dbt test` green (incl. the new `not_null`).
- `EXPLAIN ANALYZE` a sample `@@` query → GIN bitmap scan confirmed.
- Confirm the column is visible on the `recalls_readonly` role.

## Opportunistic: fold in gold-readiness R2 while you're in this model
You're already editing/rebuilding `mart_recall_summary`. Its known weak spot (doc 01 / 02) is that
**unfiltered** `ORDER BY published_at DESC` for `GET /recalls` is not index-backed (only
`(source, published_at)` exists). Adding a `(published_at DESC, recall_event_id)` index in the same
change fixes deep unfiltered paging. Same model, same `dbt build` — low marginal cost. Optional, but
this is the natural moment.

## ADR
Consider a short ADR (sibling to 0037) noting: recall-level FTS added to `mart_recall_summary`;
english config; weighted (A/B/C); GIN; **still no pg_trgm** (fuzzy/typo remains explicitly out — a
separate future decision, not bundled here).

## Done =
Column live on the read-only role, GIN present and used (EXPLAIN), dbt tests green, downstream
unaffected. Then the API plan unblocks.
