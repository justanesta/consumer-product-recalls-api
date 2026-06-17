Purpose: Exhaustive endpoint-by-endpoint reference for the Consumer Product Recalls API.

# API Reference

- [Conventions](#conventions)
- [GET /recalls](#get-recalls)
- [GET /recalls/search](#get-recallssearch)
- [GET /recalls/{source}/{recall\_id}](#get-recallssourcerecall_id)
- [GET /products/search](#get-productssearch)
- [GET /firms/{firm\_id}](#get-firmsfirm_id)
- [GET /health](#get-health)
- [GET /health/db](#get-healthdb)

---

## Conventions

**Base URL:** `https://consumer-product-recalls-api.fly.dev`

**All responses are JSON.** Send `Accept: application/json` or omit it; no content negotiation.

**Interactive docs:** `/docs` (Swagger UI), `/redoc` (ReDoc), `/openapi.json` (raw spec).

### Page envelope

List and search endpoints return a `Page[T]` object:

```json
{
  "items": [ /* array of result objects */ ],
  "next_cursor": "eyJ...",
  "limit": 25,
  "total": null
}
```

| Field | Type | Notes |
|---|---|---|
| `items` | array | The current page of results. Empty array when there are no results. |
| `next_cursor` | string \| null | Opaque base64url token. `null` on the last page. |
| `limit` | integer | The page size used for this response. |
| `total` | integer \| null | Count of all matching rows. `null` unless `with_total=true` was passed. |

### Keyset pagination

Pass `next_cursor` from one response back as the `cursor` query parameter on the next request to get the following page. Keep all filter parameters identical across pages; changing a filter with a live cursor produces undefined results.

```
GET /recalls?limit=25&cursor=<next_cursor from prior response>
```

Request `with_total=true` to include a `total` count. This fires a second `COUNT(*)` query and adds latency; omit it unless the UI requires a total.

A malformed `cursor` value returns **400 `bad_cursor`**.

### Error envelope

Every non-2xx response uses this shape:

```json
{
  "error": {
    "type": "not_found",
    "detail": "no recall for CPSC/24-001",
    "request_id": "a3f9c2d44b1e..."
  }
}
```

| HTTP status | `error.type` | `Retry-After` header | When |
|---|---|---|---|
| 400 | `bad_cursor` | — | Malformed or wrong-shape pagination cursor. |
| 404 | `not_found` | — | Requested resource does not exist. |
| 422 | `invalid_parameter` | — | Invalid query/path parameter value or a required selector is missing. |
| 429 | `rate_limited` | `60` | Per-IP rate limit exceeded (default 60 requests/minute). |
| 500 | `internal_error` | — | Unexpected server error; details go to logs only. |
| 503 | `upstream_unavailable` | `5` | Database unreachable or timed out (includes cold Neon wake). Retry after 5 s. |

`detail` is a human-readable string for most errors. For 422 responses from FastAPI path/query validation it is an array of `{"loc": [...], "msg": "..."}` objects.

### Caching

Successful `GET` responses carry:
- `Cache-Control: public, max-age=300` (5 minutes, reflecting the nightly ~03:00 UTC rebuild cadence).
- `ETag: W/"0.1.0-<startup_id>"` — a weak ETag that changes on each deploy. Use with `If-None-Match` for conditional GETs.
- `Last-Modified` — set to the server startup time, not the data rebuild time. A per-rebuild ETag sourced from `gold_meta.rebuilt_at` is deferred.

`/health` and `/health/db` always return `Cache-Control: no-store`.

### Rate limit

Default: **60 requests per minute per IP** (per process; resets on cold start — not a global cluster-wide counter). Health endpoints (`/health`, `/health/db`) are exempt and do not consume rate-limit budget. Exceeded: 429 + `Retry-After: 60`.

---

## GET /recalls

List recalls across all five agencies, newest first, with optional filters and keyset pagination.

```
GET /recalls
```

**Response model:** `Page[RecallSummary]`

**Status codes:** 400 `bad_cursor`, 422 `invalid_parameter`, 429 `rate_limited`, 503 `upstream_unavailable`

### Parameters

All parameters are optional. Different filters AND together. The six categorical filters marked
**multi** below accept more than one value — repeat the param (`?source=CPSC&source=FDA`) or
comma-separate it (`?source=CPSC,FDA`); the two forms are equivalent. Multiple values for the **same**
field are OR-ed (any-of); different fields still AND. A single value behaves exactly as before. (Only
fields whose legal values never contain a comma are multi-value — `firm` and the date ranges stay
single-value.)

#### Recall filters

| Name | Type | Default | Constraints | Notes |
|---|---|---|---|---|
| `source` | enum (**multi**) | — | `CPSC`, `FDA`, `USDA`, `NHTSA`, `USCG` (uppercase) | Filter to one or more issuing agencies (any-of). Unknown value → 422. |
| `classification` | string (**multi**) | — | `max_length=64` per value | Exact match on the source-native classification string(s); any-of. Values differ by agency; see [data_contract.md](data_contract.md) for the root cause. |
| `is_active` | boolean | — | — | Tri-state. CPSC and NHTSA carry `null`; a `true` or `false` filter silently excludes all their records. See [data_contract.md](data_contract.md). |
| `lifecycle_status` | string (**multi**) | — | `max_length=64` per value | Exact match; source-native; any-of. CPSC/NHTSA carry `null`, so filtering on this value excludes their rows. |
| `distribution_scope` | enum (**multi**) | — | `Nationwide`, `Regional`, `Unspecified`, `International` | Any-of; validated; 422 on any other value. |
| `distribution_state` | string (**multi**) | — | exactly 2 chars each, USPS code | Recalls distributed to **any** of these US states (array overlap). GIN-backed. FDA/USDA only; CPSC/NHTSA/USCG have no distribution area data. |
| `distribution_country` | string (**multi**) | — | exactly 2 chars each, ISO alpha-2 | Recalls distributed to **any** of these countries (array overlap). **Foreign distribution only** — `US` is excluded by design (US distribution is captured by `distribution_scope` + `distribution_state`). GIN-backed. FDA/USDA only. See [data_contract.md](data_contract.md). |
| `source_recall_id` | string | — | `min_length=1`, `max_length=128` | Exact match on the agency-native recall id. Unique only when combined with `source`; use the detail route for a guaranteed single result. |
| `firm` | string | — | `min_length=2`, `max_length=200` | Case-insensitive substring match on `primary_firm_name`. Unindexed — avoid on very large result sets without a leading `source` filter. |
| `published_after` | date (`YYYY-MM-DD`) | — | — | Inclusive start of the calendar day. |
| `published_before` | date (`YYYY-MM-DD`) | — | — | Inclusive of the entire `published_before` day. |
| `announced_after` | date (`YYYY-MM-DD`) | — | — | `announced_at >= start of day (UTC)`. Rows with a null `announced_at` are excluded. |
| `announced_before` | date (`YYYY-MM-DD`) | — | — | Inclusive of the entire `announced_before` day. Rows with a null `announced_at` are excluded. |

#### Pagination

| Name | Type | Default | Constraints | Notes |
|---|---|---|---|---|
| `limit` | integer | `25` | `ge=1`, `le=100` | Page size. Capped at 100. |
| `cursor` | string | — | — | Opaque token from a prior `next_cursor`. Malformed value → 400. |
| `with_total` | boolean | `false` | — | When `true`, fires an extra `COUNT(*)` and populates `Page.total`. |

### Key response fields (`RecallSummary`)

| Field | Type | Notes |
|---|---|---|
| `recall_event_id` | string | Opaque md5 surrogate. Use with `source` on the detail route. |
| `source` | enum | `CPSC` \| `FDA` \| `USDA` \| `NHTSA` \| `USCG` |
| `source_recall_id` | string | Agency-native recall id (e.g. `24-001` for CPSC). |
| `title` | string \| null | Recall title. |
| `url` | string \| null | Canonical agency URL. |
| `announced_at` | datetime \| null | Null for ~20 FDA records and all CPSC/NHTSA. |
| `published_at` | datetime | Always present; primary sort key. |
| `classification` | string \| null | Source-native tier string (e.g. `Class II`). |
| `risk_level` | string \| null | Source-native risk descriptor (e.g. `Low - Class II`); not unified across sources. |
| `lifecycle_status` | string \| null | Source-native lifecycle string. `null` for CPSC/NHTSA. |
| `is_active` | boolean \| null | Tri-state. See [data_contract.md](data_contract.md). |
| `reason_category` | string \| null | Coarse reason bucket; `null` when the source provides none. |
| `distribution_scope` | string | `Nationwide` \| `Regional` \| `Unspecified` \| `International`. Always present. |
| `primary_firm_name` | string \| null | Top-level firm name from the mart rollup. |
| `firm_count` | integer | Number of firms linked to this recall. |
| `product_count` | integer | Number of distinct products. |
| `edit_event_count` | integer | Number of times the recall has been amended in the source feed. |
| `has_been_edited` | boolean | Whether the recall has been amended since first publication. |

### Examples

List the 5 newest CPSC recalls:

```bash
curl "https://consumer-product-recalls-api.fly.dev/recalls?source=CPSC&limit=5"
```

Nationwide FDA recalls in the last 90 days:

```bash
curl "https://consumer-product-recalls-api.fly.dev/recalls?source=FDA&distribution_scope=Nationwide&published_after=2026-03-17"
```

Fetch the next page using the cursor from the previous response:

```bash
curl "https://consumer-product-recalls-api.fly.dev/recalls?source=FDA&limit=5&cursor=<next_cursor>"
```

Get the first page plus a total count:

```http
GET /recalls?source=USDA&with_total=true
```

### Caveats

- **`is_active` and `lifecycle_status` filters exclude CPSC/NHTSA rows** — those sources carry no native lifecycle field; both columns are `null` for every CPSC and NHTSA record. Root cause: [data_contract.md](data_contract.md).
- **`classification` is source-native, not a unified enum** — `Class I` on an FDA record and `Class I` on a USDA record mean the same hazard tier, but `H` on USCG and blank on CPSC/NHTSA are structurally different values from different agencies. Root cause: [data_contract.md](data_contract.md).
- **`distribution_state` / `distribution_country` are FDA/USDA-only** — CPSC, NHTSA, and USCG have no distribution area data in the upstream source. Root cause: [data_contract.md](data_contract.md).
- **Unfiltered list sort is a full table sort** — without a leading `source` filter the planner cannot use the `btree(source, published_at)` index for ordering. Add `source=` for consistent performance on deep pages.

---

## GET /recalls/search

Recall-grain keyword search ranked by relevance.

```
GET /recalls/search
```

**Response model:** `Page[RecallSearchHit]` — `RecallSummary` fields plus `rank: float`

**Status codes:** 400 `bad_cursor`, 422 `invalid_parameter`, 429 `rate_limited`, 503 `upstream_unavailable`

### Parameters

All filters from [GET /recalls](#get-recalls) apply unchanged. The following parameter is added and required:

| Name | Type | Default | Constraints | Notes |
|---|---|---|---|---|
| `q` | string | **required** | `min_length=2`, `max_length=200` | Keywords in Postgres `websearch_to_tsquery` syntax. Token/prefix matching only; no fuzzy or typo correction. Omitting `q` → 422. |

Pagination parameters (`limit`, `cursor`, `with_total`) apply as on the list endpoint.

### Key response fields (`RecallSearchHit`)

All `RecallSummary` fields, plus:

| Field | Type | Notes |
|---|---|---|
| `rank` | float | `ts_rank_cd` relevance score. Higher is more relevant. Not comparable across different queries. |

Search covers: recall title, product names, firm name, recall reason, and consequence narrative.

### Examples

Search all agencies for recalls involving baby products:

```bash
curl "https://consumer-product-recalls-api.fly.dev/recalls/search?q=baby+stroller+fall"
```

Search within a single source with a date bound:

```bash
curl "https://consumer-product-recalls-api.fly.dev/recalls/search?q=listeria&source=FDA&published_after=2025-01-01"
```

Fetch the second page:

```http
GET /recalls/search?q=listeria&source=FDA&cursor=<next_cursor>
```

### Caveats

- **Token/prefix matching only, no fuzzy search.** A misspelled term returns zero results. `websearch_to_tsquery` supports phrases (`"peanut butter"`) and negation (`-contamination`). Root cause: [data_contract.md](data_contract.md).
- **Relevance-ordered keyset is not index-backed for ordering.** The GIN index serves the `@@` match; the `ts_rank_cd DESC` sort runs over the matched set. On large unfiltered result sets this can be slow; add `source=` or a date range to bound the matched set.
- Same `is_active`, `classification`, and distribution caveats as [GET /recalls](#get-recalls).

---

## GET /recalls/{source}/{recall\_id}

Fetch the full record for one recall by its issuing agency and agency-native recall id.

```
GET /recalls/{source}/{recall_id}
```

**Response model:** `RecallDetail`

**Status codes:** 404 `not_found`, 422 `invalid_parameter`, 429 `rate_limited`, 503 `upstream_unavailable`

### Parameters

| Name | Location | Type | Constraints | Notes |
|---|---|---|---|---|
| `source` | path | string | Must be a valid agency code | Accepted **case-insensitively** — `cpsc`, `CPSC`, and `Cpsc` all work. Normalized to uppercase internally. Unknown value → 422. Valid values: `CPSC`, `FDA`, `USDA`, `NHTSA`, `USCG`. |
| `recall_id` | path | string | `min_length=1`, `max_length=128` | The agency-native recall id exactly as the agency issues it (e.g. `24-001` for CPSC, a numeric string for FDA). |

### Key response fields (`RecallDetail`)

All `RecallSummary` fields, plus:

| Field | Type | Notes |
|---|---|---|
| `recall_reason` | string \| null | Narrative reason for the recall. |
| `corrective_action` | string \| null | What consumers should do. |
| `consequence_of_defect` | string \| null | Described hazard outcome. |
| `distribution_states` | string \| null | Agency prose (a single scalar string, e.g. `"Nationwide"`). Do not confuse with `distribution_state_codes`. |
| `distribution_state_codes` | list[string] \| null | Parsed USPS 2-letter codes. `null` for CPSC/NHTSA/USCG. |
| `distribution_country_codes` | list[string] \| null | ISO alpha-2 codes; foreign-only (`US` excluded). `null` for CPSC/NHTSA/USCG. |
| `hazards` | list \| null | Opaque hazard objects; structure varies by source. |
| `product_upcs` | list[string] | Recall-level UPCs. Empty list (`[]`) when none. |
| `product_names` | list[string] | Product names on this recall. Always a list, never null. |
| `models` | list[string] | Product model numbers. Always a list, never null. |
| `hins` | list[string] | USCG Hull Identification Numbers. Empty for non-USCG sources. |
| `firms` | list[FirmRef] | Firms linked to this recall. Each has `firm_id`, `name`, `role`, `match_confidence`. |
| `first_seen_at` | datetime \| null | When the pipeline first ingested this recall. |
| `last_seen_at` | datetime \| null | When the pipeline last saw this recall in the source feed. |
| `is_currently_active` | boolean \| null | Most recent lifecycle state from the source feed. |
| `was_ever_retracted` | boolean \| null | Whether the recall was ever marked inactive then reactivated. |

### Examples

Fetch a CPSC recall (case-insensitive source):

```bash
curl "https://consumer-product-recalls-api.fly.dev/recalls/CPSC/24-001"
```

```bash
curl "https://consumer-product-recalls-api.fly.dev/recalls/cpsc/24-001"
```

Fetch an FDA recall:

```bash
curl "https://consumer-product-recalls-api.fly.dev/recalls/FDA/12345"
```

```http
GET /recalls/usda/026-2025
```

### Caveats

- **`is_active` is `null` for CPSC and NHTSA** — these sources carry no native lifecycle field. Root cause: [data_contract.md](data_contract.md).
- **`classification`, `risk_level`, `lifecycle_status` are source-native** — the strings come directly from the agency and are not mapped to a common vocabulary. Root cause: [data_contract.md](data_contract.md).
- **`distribution_states` (prose) vs `distribution_state_codes` (parsed array) are different fields.** Do not use the prose string for filtering; filter with `distribution_state` on the list endpoint instead.
- **`product_upcs` is recall-level, not per-product.** A recall listing UPC `012345678901` means the recall as a whole covers that UPC — not necessarily that every product on the recall carries it. Root cause: [data_contract.md](data_contract.md).

---

## GET /products/search

Search recalled products by keyword, exact identifier, or recall-level UPC.

```
GET /products/search
```

**Response model:** `Page[ProductSearchHit]`

**Status codes:** 400 `bad_cursor`, 422 `invalid_parameter`, 429 `rate_limited`, 503 `upstream_unavailable`

### Parameters

**At least one selector (`q`, `hin`, `model`, or `upc`) is required.** Omitting all four → 422.

**Selector precedence:** `q` > (`hin` and/or `model`) > `upc`. When `q` is present it is always used as the FTS path, regardless of other selectors. `hin` and `model` can be combined (AND-ed). `source` is optional on every path and AND-s with the selector.

#### Selector parameters

| Name | Type | Default | Constraints | Notes |
|---|---|---|---|---|
| `q` | string | — | `min_length=2`, `max_length=200` | Full-text search over product name, description, recall title, and firm name. Token/prefix only; no fuzzy. Results sorted by relevance. |
| `hin` | string | — | `max_length=64` | Exact USCG Hull Identification Number. Sorted by `published_at DESC`. |
| `model` | string | — | `max_length=128` | Exact product model string. Sorted by `published_at DESC`. Can be combined with `hin`. |
| `upc` | string | — | `max_length=32` | UPC code. Matched at the **recall level** via JSONB array containment over `recall_product_upcs`. Per-product `upc` is empty for all rows today. Results carry `upc_is_recall_level: true`. UPC data is CPSC-sourced and sparse, so most codes return no match. |
| `source` | enum (**multi**) | — | `CPSC`, `FDA`, `USDA`, `NHTSA`, `USCG` | Optional source filter, AND-ed with whichever selector is active. Accepts one or more values (repeat or comma-separate) for any-of (OR). |

#### Pagination

| Name | Type | Default | Constraints | Notes |
|---|---|---|---|---|
| `limit` | integer | `25` | `ge=1`, `le=100` | Page size. |
| `cursor` | string | — | — | Opaque token from a prior `next_cursor`. Malformed → 400. |
| `with_total` | boolean | `false` | — | Fires an extra `COUNT(*)` and populates `Page.total`. |

### Key response fields (`ProductSearchHit`)

| Field | Type | Notes |
|---|---|---|
| `recall_product_id` | string | Opaque product-level id; keyset cursor anchor. |
| `recall_event_id` | string | Links to the parent recall (`GET /recalls/{source}/{recall_id}`). |
| `source` | enum | Issuing agency. |
| `product_name` | string \| null | Product name. |
| `product_description` | string \| null | Product description. |
| `model` | string \| null | Model number. |
| `hin` | string \| null | USCG Hull ID. Non-null for USCG recalls only. |
| `upc` | string \| null | Per-product UPC. **Always `null` today** — product-grain UPC extraction is unimplemented in the pipeline. |
| `recall_product_upcs` | list[string] | Recall-level UPCs. This is what `upc` search actually matches against. |
| `published_at` | datetime | Recall publication date. |
| `is_active` | boolean \| null | Tri-state (null for CPSC/NHTSA). |
| `rank` | float \| null | `ts_rank_cd` relevance. Populated only on the `q` path; `null` on `hin`/`model`/`upc` paths. |
| `upc_is_recall_level` | `true` (literal) | Always `true`. Indicates that any UPC data here is at the recall level, not the product level. |

### Examples

FTS for airbag-related products:

```bash
curl "https://consumer-product-recalls-api.fly.dev/products/search?q=airbag+inflator"
```

Exact model lookup:

```bash
curl "https://consumer-product-recalls-api.fly.dev/products/search?model=ABC-1234"
```

Hull ID lookup (USCG):

```bash
curl "https://consumer-product-recalls-api.fly.dev/products/search?hin=ABC12345D678"
```

UPC recall lookup:

```bash
curl "https://consumer-product-recalls-api.fly.dev/products/search?upc=012345678901"
```

Combine `hin` and `model`:

```http
GET /products/search?hin=ABC12345D678&model=XR200
```

### Caveats

- **`upc` search is recall-level, not product-level.** The per-product `upc` column is `null` for every row; UPC lookup uses `recall_product_upcs` (a recall-wide array). `upc_is_recall_level: true` is always set to signal this. A miss means no recall lists that UPC at the recall level, not that the product was never recalled. Root cause: [data_contract.md](data_contract.md).
- **No fuzzy search.** Token/prefix matching only on the `q` path. Root cause: [data_contract.md](data_contract.md).
- **At least one selector is required.** Providing none returns 422.

---

## GET /firms/{firm\_id}

Fetch a canonical (cross-source) firm profile with agency registration sidecars.

```
GET /firms/{firm_id}
```

**Response model:** `FirmProfile`

**Status codes:** 404 `not_found`, 422 `invalid_parameter`, 429 `rate_limited`, 503 `upstream_unavailable`

### Parameters

| Name | Location | Type | Constraints | Notes |
|---|---|---|---|---|
| `firm_id` | path | string | exactly 32 chars, pattern `^[0-9a-f]{32}$` | Opaque md5 cluster id. Malformed shape → 422 before the DB is touched. Not found → 404. Obtain the id from a `RecallDetail.firms[].firm_id` field. |

### Key response fields (`FirmProfile`)

| Field | Type | Notes |
|---|---|---|
| `firm_id` | string | Opaque 32-hex md5 cluster id. |
| `canonical_name` | string | Representative name for the cluster. |
| `normalized_name` | string | Lowercased/trimmed canonical name used for matching. |
| `observed_names` | list[string] | All raw name variants that merged into this cluster (the merge audit trail). |
| `observed_company_ids` | list[string] | Every structured government id that folded into this cluster — FDA FEI, USDA/FSIS establishment number, USCG MIC, CPSC company_id. Also the join key to the three sidecars below. |
| `alternate_names` | list[string] | Brand / DBA surface-form aliases (the DBA brand plus brand-bearing parentheticals), kept as a search/alias field — distinct from the raw spellings in `observed_names`. |
| `total_recalls` | integer | Total recall count across all sources. |
| `active_recalls` | integer | Count of recalls currently marked active. |
| `first_recall_at` | datetime \| null | Earliest recall date for this firm. |
| `last_recall_at` | datetime \| null | Most recent recall date for this firm. |
| `roles` | list[string] | Distinct roles this firm has played across its recalls: `manufacturer`, `establishment`, `filer`, `importer`, `distributor`. |
| `recalls_by_source` | object | Map of source → recall count, e.g. `{"CPSC": 3, "FDA": 1}`. |
| `distinct_products` | integer | Number of distinct product records linked to this firm. |
| `firm_usda_attributes` | list[UsdaEstablishment] | USDA/FSIS establishment records. Empty for non-USDA firms. |
| `firm_uscg_attributes` | list[UscgManufacturer] | USCG Manufacturer ID Code (MIC) records. Empty for non-USCG firms. |
| `firm_fda_attributes` | list[FdaAttributes] | FDA FEI (Firm Establishment Identifier) records. Empty for non-FDA firms. |

The three sidecar types have **different shapes** from each other. CPSC and NHTSA contribute no sidecar records; those lists are always empty for firms that appear only in those sources.

### Examples

Fetch a firm by id (obtain from a recall's `firms[].firm_id`):

```bash
curl "https://consumer-product-recalls-api.fly.dev/firms/a3f9c2d44b1e8f7c0d2e5b6a9c1f3e4d"
```

```http
GET /firms/a3f9c2d44b1e8f7c0d2e5b6a9c1f3e4d
```

Workflow — look up a recall, then fetch its firm profile:

```bash
# 1. Get a recall detail
curl "https://consumer-product-recalls-api.fly.dev/recalls/CPSC/24-001"
# 2. From firms[].firm_id in the response:
curl "https://consumer-product-recalls-api.fly.dev/firms/<firm_id from step 1>"
```

### Caveats

- **The `firm_id` is opaque.** Do not attempt to construct one; always obtain it from `RecallDetail.firms[].firm_id`. The 32-hex pattern guard is a shape check only — a syntactically valid but unknown id returns 404.
- **A firm appearing under multiple agencies collapses to one row.** `recalls_by_source` breaks down the count per agency.
- **`first_recall_at` and `last_recall_at` are `null` if the firm has no matched recalls in the gold mart** (can occur for newly ingested firms not yet linked to a recall event).

---

## GET /health

Liveness probe. Confirms the process is running. Does not touch the database.

```
GET /health
```

**Response model:** `Health`

**Status codes:** 200 only (no documented error responses)

**Rate-limit exempt.** The Fly.io liveness probe hits this path; it never consumes rate-limit budget and never wakes a sleeping Neon database.

### Response fields

| Field | Type | Value |
|---|---|---|
| `status` | string | Always `"ok"` |
| `version` | string | API version string (e.g. `"0.1.0"`) |

### Example

```bash
curl "https://consumer-product-recalls-api.fly.dev/health"
```

```json
{"status": "ok", "version": "0.1.0"}
```

---

## GET /health/db

Readiness probe. Executes a `SELECT 1` against the read-only Neon database and confirms the connection is live.

```
GET /health/db
```

**Response model:** `DbHealth`

**Status codes:** 200, 503 `upstream_unavailable` (+ `Retry-After: 5`)

**Rate-limit exempt.**

Use this endpoint to check whether the database is reachable before sending data requests. After a Fly.io cold start, the Neon database may be suspended; this probe will return 503 until Neon wakes (typically a few seconds). The deploy pipeline retries this endpoint up to 5 times with 10-second sleeps.

### Response fields

| Field | Type | Value |
|---|---|---|
| `status` | string | Always `"ok"` |
| `database` | string | Always `"reachable"` |

### Example

```bash
curl "https://consumer-product-recalls-api.fly.dev/health/db"
```

```json
{"status": "ok", "database": "reachable"}
```

Cold Neon:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 5

{"error": {"type": "upstream_unavailable", "detail": "database temporarily unavailable", "request_id": "..."}}
```
