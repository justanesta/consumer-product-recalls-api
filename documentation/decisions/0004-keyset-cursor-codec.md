# 0004 - Keyset (seek) pagination: opaque base64url 2-tuple cursor, DESC-then-ASC seek WHERE

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

> Upstream framing: keyset pagination over the gold mart key columns was ratified in pipeline ADR 0024 (`documentation/decisions/0024-serving-layer-api-design.md` in the pipeline repo).

---

## Context

The gold mart `mart_recall_summary` holds tens of thousands of rows with nightly appends. OFFSET pagination requires Postgres to scan and discard N rows for every page — cost grows linearly with depth and is unsuitable for a public API on a free-tier serverless DB.

Two distinct sort shapes are needed across the API:

- **List path** (`GET /recalls`): `published_at DESC, recall_event_id ASC`. This compound is backed by the R2 expression index `(published_at DESC, recall_event_id)` applied upstream in the gold mart. (`src/recalls_api/queries/recalls.py:153-171`)
- **FTS path** (`GET /recalls/search`, `GET /products/search` with `q=`): `ts_rank_cd DESC, <id> ASC`. Rank is computed at query time; only the GIN serves the `@@` match predicate. The ORDER BY is an application-level sort over the matched set, not index-backed. (`src/recalls_api/pagination.py:7-9`)

A compound `DESC, ASC` sort cannot use a Postgres row-value `<` comparison (that operator assumes all-ascending columns). A separate seek-WHERE expansion is required.

Finally, the cursor is round-tripped through an untrusted client. A tampered or garbage payload must map to HTTP 400, not a downstream `ValueError` that would surface as 500.

---

## Decision

1. **Encode the last row's sort values as a 2-tuple.** `Cursor` is a frozen dataclass with a single `values: tuple[Any, ...]` field. Encoding: `json.dumps([val, id], separators=(",", ":"))` → UTF-8 → `base64.urlsafe_b64encode` with padding stripped. (`src/recalls_api/pagination.py:30-38`)

2. **Decode with arity guard.** Re-pad, `base64.urlsafe_b64decode`, `json.loads`. Any `binascii.Error`, `UnicodeDecodeError`, `json.JSONDecodeError`, or `ValueError` raises `BadCursor("malformed pagination cursor")` (HTTP 400). A payload that is not a 2-element list raises `BadCursor("cursor payload is not a 2-element tuple")`. The arity check fires before the 2-tuple is unpacked by any seek-WHERE builder. (`src/recalls_api/pagination.py:40-53`)

3. **Expand `DESC, ASC` seek-WHERE as an OR.** `col < :p OR (col = :p AND id > :id)` — the only correct expansion for a compound descending-then-ascending sort with bound params only (no SQL injection). (`src/recalls_api/pagination.py:56-82`)

4. **Serialize `published_at` as an ISO string.** JSON has no native datetime type. `Cursor.encode` stores `published_at.isoformat()`; `published_at_keyset_where` parses it back to `datetime` and binds it as `TIMESTAMP(timezone=True)` so asyncpg sends a proper `timestamptz` comparison — a bare string binding fails the overload. (`src/recalls_api/pagination.py:63-70`)

5. **Fetch `limit + 1` rows; `has_next = len(rows) > limit`.** The extra row is never returned to the caller; it only drives the `has_next` boolean in `slice_page()`. No `COUNT(*)` is issued unless the caller passes `?with_total=true`. (`src/recalls_api/pagination.py:85-88`, `src/recalls_api/queries/recalls.py:171`)

6. **Two concrete keyset shapes, no others.**

   | Shape | Sort | Used by |
   |---|---|---|
   | `(published_at ISO, id)` | `published_at DESC, id ASC` | `recalls.list_stmt`; `products.identifier_stmt`; `products.upc_stmt` |
   | `(float rank, id)` | `ts_rank_cd DESC, id ASC` | `recalls.search_stmt`; `products.fts_stmt` |

---

## Consequences

**Benefits:**

- No server-side cursor state. The cursor is fully self-describing; any API instance can decode any page token.
- The arity guard converts a wrong-shape cursor (e.g., a token from a different endpoint version or a crafted payload) into a 400 before the seek-WHERE builder ever unpacks the tuple.
- `?with_total=true` is an explicit opt-in; most callers avoid the extra `COUNT(*)` entirely.
- Rank weights in `ts_rank_cd` (`'{0.1,0.2,0.4,1.0}'::float4[]`) are tunable without rebuilding the GIN index. (`src/recalls_api/queries/recalls.py:188`)

**Accepted costs:**

- FTS keyset pagination is O(matched-set) for deep pages — the GIN backs the `@@` match but not the `ts_rank_cd ORDER BY`. This is disclosed in the OpenAPI description (`src/recalls_api/routers/recalls.py:44-46`).
- Pagination is stable only as long as sort-key values are stable. A nightly rebuild that changes `published_at` or `recall_event_id` for existing rows would invalidate live cursors. The upstream gold contract (pipeline ADR 0042) treats these columns as immutable keys for exactly this reason.
- HMAC signing was considered and rejected for v1: `BadCursor` on any garbage input is sufficient protection for a public read-only API; HMAC adds complexity without meaningful security gain.
