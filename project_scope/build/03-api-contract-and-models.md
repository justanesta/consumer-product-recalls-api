# 03 — API Contract & Pydantic Models (recalls-api)

> **Hardened build spec.** Authoritative schema facts come from `01-ground-truth-gold-marts.md`
> (cited inline as "see 01 — Mart N"); locked decisions from `02-plan-reconciliation.md`. This doc is
> the contract the build session implements against directly: every endpoint's params, response model,
> error map, and OpenAPI copy; every Pydantic v2 field with its mart-column source and default; and the
> filter→predicate→index map. Implementation wiring (query builders, `db.py`, `pagination.py` codec)
> lives in **04**; tests/CI in **05**; deploy/ops (cache headers, 503/Retry-After, role) in **06**;
> gold-layer asks in **07**; commit plan in **08**.
>
> **Conventions used here (mirroring the house skills):** all params are
> `Annotated[T, Query(...)]` / `Annotated[T, Path(...)]`; `|`-unions never `Optional[...]`; `StrEnum`
> for the one closed domain (`source`); `match` for source-dispatch; Pydantic v2 `model_config =
> ConfigDict(from_attributes=True)` on every response model so a SQLAlchemy Core `Row` (a `Mapping`)
> coerces straight into the model. Python 3.12.

---

## 0. Cross-cutting primitives

These are referenced by every endpoint and live in `recalls_api/models/common.py` (envelope/enums) and
`recalls_api/errors.py` (envelope + handlers). Defined in full in **Section B**; named here so Section A reads
cleanly.

| Primitive | Purpose |
|---|---|
| `Source(StrEnum)` | the only closed enum: `CPSC FDA USDA NHTSA USCG` (uppercase). Path/query coercion + 422 on a bad value, *for free*. |
| `Page[T]` | generic envelope `{items: list[T], next_cursor: str \| None, limit: int, total: int \| None}`. |
| `Cursor` | opaque base64url codec over the last sort tuple (impl in `pagination.py`, **04**). |
| `ErrorEnvelope` | uniform error body `{error: {type, detail, request_id}}`. |
| `FirmRef` | the `firms[]` jsonb element shape, shared by `RecallSummary` and `RecallDetail`. |

### Error model (applies to every endpoint)

Every non-2xx response uses **one** envelope so clients parse errors uniformly. `request_id` is the
uuid bound by the contextvars middleware (decision 13) and echoed in `X-Request-ID`.

```python
# recalls_api/errors.py
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

class ErrorDetail(BaseModel):
    type: str = Field(examples=["ResourceNotFound"])  # the ApiError subclass name
    detail: Any = Field(examples=["No recall found for CPSC/24-001."])  # human-readable message
    request_id: str = Field(examples=["b1d9c6f2-3a1e-4c7e-9f0a-7d2c1e5b8a40"])

class ErrorEnvelope(BaseModel):
    error: ErrorDetail
```

| Type | HTTP | Trigger | Headers | Source of the raise |
|---|---|---|---|---|
| `ResourceNotFound` | 404 | detail/firm id resolves to zero rows | — | handler-level `raise NotFound(...)` |
| `InvalidParameter` | 422 | a `Query`/`Path`/Pydantic constraint fails, **or** `/products/search` supplied none of `q\|hin\|model\|upc` | — | FastAPI `RequestValidationError` reshaped into `ErrorEnvelope` |
| `BadCursor` | 400 | `?cursor=` fails base64url decode / shape check | — | `Cursor.decode()` raises `BadCursor` |
| `UpstreamUnavailable` | 503 | Neon cold/asleep or connect/command timeout (decision 14) | `Retry-After: 5` | `db` dependency catches `asyncpg`/SQLAlchemy `Operational... / TimeoutError` |
| `RateLimited` | 429 | slowapi IP limiter trips (decision: chosen here, **not** ADR-ratified — see 02) | `Retry-After: <window>` | slowapi handler reshaped into `ErrorEnvelope` |

> **Judgment call:** `429`/slowapi is carried because the plan intends it, but 02 flags it as *not*
> ADR-ratified — the limiter and limits are an API-repo decision (tune to the free-tier DB in **06**).
> Keep `RateLimited` in every `responses={}` map regardless so the OpenAPI contract is stable whether or
> not the limiter is enabled in a given deploy.

`responses={}` reuse — declare once and spread (`responses={**ERR_5XX, ...}`):

```python
# recalls_api/errors.py
_ERR = {"model": ErrorEnvelope}
ERR_422 = {422: {**_ERR, "description": "InvalidParameter — a parameter failed validation."}}
ERR_400 = {400: {**_ERR, "description": "BadCursor — opaque cursor failed to decode."}}
ERR_404 = {404: {**_ERR, "description": "ResourceNotFound."}}
ERR_503 = {503: {**_ERR, "description": "UpstreamUnavailable — database cold/unreachable; retry."}}
ERR_429 = {429: {**_ERR, "description": "RateLimited — slow down; see Retry-After."}}
LIST_ERRORS = {**ERR_400, **ERR_422, **ERR_503, **ERR_429}
ITEM_ERRORS = {**ERR_404, **ERR_422, **ERR_503, **ERR_429}
```

---

## SECTION A — Endpoint contract

The DB handle is injected by a single dependency `db: AsyncConnection = Depends(get_conn)` (DI pattern,
impl in **04**); it is the seam that converts a cold/asleep Neon into a `503 UpstreamUnavailable`
(decision 14). All handlers are `async def`.

### A.1 `GET /recalls` — list + filter (mart_recall_summary)

```python
@router.get(
    "/recalls",
    response_model=Page[RecallSummary],
    responses=LIST_ERRORS,
    summary="List recalls (newest first), with filters and keyset pagination.",
)
async def list_recalls(
    db: Annotated[AsyncConnection, Depends(get_conn)],
    source: Annotated[Source | None, Query(description="Filter by issuing agency.")] = None,
    classification: Annotated[str | None, Query(
        max_length=64,
        description="EXACT match on the source-native classification string (see caveat).",
    )] = None,
    is_active: Annotated[bool | None, Query(
        description="Tri-state. true/false match only sources that carry status; "
                    "CPSC and NHTSA recalls have is_active = null and NEVER match either value.",
    )] = None,
    published_after: Annotated[date | None, Query(
        description="Inclusive lower bound (calendar date): published_at >= the START of that day.",
    )] = None,
    published_before: Annotated[date | None, Query(
        description="Inclusive upper bound (calendar date): matches the ENTIRE published_before day.",
    )] = None,
    firm: Annotated[str | None, Query(
        min_length=2, max_length=200,
        description="Case-insensitive substring of primary_firm_name (UNINDEXED; see caveat).",
    )] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(description="Opaque pagination cursor from next_cursor.")] = None,
    with_total: Annotated[bool, Query(description="Also compute total (extra COUNT; off by default).")] = False,
) -> Page[RecallSummary]: ...
```

**Filter → column → index** (full table in Section C):

| Param | Mart column (01 — Mart 1) | Index it rides | Predicate |
|---|---|---|---|
| `source` | `source` | leads `btree(source, published_at)` | `source = :source` |
| `classification` | `classification` | `btree(classification)` | `classification = :classification` (equality, **not** ILIKE) |
| `is_active` | `is_active` (tri-state) | `btree(is_active)` | `is_active = :is_active` (NULL rows excluded by design) |
| `published_after/before` | `published_at` (NOT NULL) | `(source, published_at)` only when `source` leads; else range-scan/sort | `published_at >= :published_after::date` / `published_at < (:published_before::date + INTERVAL '1 day')` |
| `firm` | `primary_firm_name` | **none** (seq filter) | `primary_firm_name ILIKE '%'\|\|:firm\|\|'%'` |
| ordering | `(published_at, recall_event_id)` | index-backed **only** when `source` present | `ORDER BY published_at DESC, recall_event_id DESC` |

**Ordering & pagination.** Always `ORDER BY published_at DESC, recall_event_id DESC` (deterministic
tiebreak; `recall_event_id` is UNIQUE/NOT NULL). Keyset: decode `cursor` → `(published_at,
recall_event_id)`; append `WHERE (published_at, recall_event_id) < (:c_pub, :c_id)`; fetch `limit + 1`;
if `len > limit`, pop the extra and set `next_cursor = encode(last_kept)`, else `next_cursor = None`.
`total` is `None` unless `with_total=true` (then one extra `COUNT(*)` over the same `WHERE`).

**Date-range boundary semantics (decision 4; identical in 04's `queries/recalls.py` builder).** The
filter params are **calendar dates** compared against a **`timestamptz`** column, so a bare `<=`/`<`
against the date would silently drop same-day rows (e.g. `published_at <= '2026-05-01'` excludes
`2026-05-01T09:00Z`). The contract is therefore:
- `published_after` → `published_at >= :published_after::date` (inclusive from the start of that day).
- `published_before` → `published_at < (:published_before::date + INTERVAL '1 day')` (inclusive of the
  **ENTIRE** `published_before` calendar day).

> **⚠️ The single most important caveat (02 blocker).** There is **no standalone `published_at` index
> and no `(published_at, recall_event_id)` index** — only the composite `btree(source, published_at)`.
> So an **unfiltered** `GET /recalls` (`ORDER BY published_at DESC`) is a **full sort**, not an index
> seek; it is index-backed only when `?source=` (an equality on the composite's leading column) is
> supplied. The keyset cursor still works correctly when unfiltered — it just is not index-accelerated.
> This is acceptable at corpus scale (tens of thousands of rows; see 02), but the OpenAPI copy must say
> so and steer deep pagination behind `?source=`. **Do not** claim the composite backs an unfiltered sort.

**OpenAPI copy (verbatim `description=`):**

> Returns recalls across CPSC, FDA, USDA, NHTSA, and USCG, newest first
> (`published_at DESC`), with keyset (seek) pagination — pass the `next_cursor` from the previous page
> back as `cursor`. **Caveats carried from the data:** (1) `classification` is **source-native and not a
> unified enum** — FDA uses `1`/`2`/`3`/`NC`, USDA uses `Class I`/`Class II`/`Class III`/`Public Health Alert`, USCG uses `H`/`L`/`M`/`S`, and
> CPSC/NHTSA have none; `?classification=` is an **exact-string equality** whose meaning depends on the
> source you also filter by. (2) `is_active` is **tri-state**: CPSC and NHTSA recalls carry no lifecycle
> status (`null`) and therefore match **neither** `is_active=true` nor `is_active=false`. (3) **Deep,
> unfiltered pagination is more expensive than it looks** — only `(source, published_at)` is indexed, so
> ordering by date across all sources is a full sort; add `?source=` for index-backed paging. (4)
> `firm` is an unindexed substring match (`primary_firm_name`); it is a convenience filter, not a search
> endpoint. Total count is omitted by default; pass `with_total=true` to opt into it.

---

### A.2 `GET /recalls/{source}/{recall_id}` — detail (mart_recall_summary)

```python
@router.get(
    "/recalls/{source}/{recall_id}",
    response_model=RecallDetail,
    responses=ITEM_ERRORS,
    summary="Fetch one recall's full record by its source + native recall id.",
)
async def get_recall(
    db: Annotated[AsyncConnection, Depends(get_conn)],
    source: Annotated[str, Path(description="Issuing agency (accepted case-insensitively).")],
    recall_id: Annotated[str, Path(
        min_length=1, max_length=128,
        description="The agency-native recall id (RecallNumber / campno / FSIS number / etc.).",
    )],
) -> RecallDetail: ...
```

**Lookup (decision 3, 01 — recall_event_id section).** Compute the surrogate **in the API** and hit
the `UNIQUE(recall_event_id)` index — O(1), no scan, no new index:

```python
import hashlib
def recall_event_id(source: Source, recall_id: str) -> str:
    # source is already uppercase (StrEnum value); storage is uppercase.
    return hashlib.md5(f"{source.value}|{recall_id}".encode()).hexdigest()
# WHERE recall_event_id = :id   ->  UNIQUE(recall_event_id)
```

**`{source}` path-param rule (decision 10, consistent with 04/05).** The path param is declared as a
plain `str` (NOT `Source`) so a lowercase source is not rejected before we can normalize it. In the
handler, **uppercase it and validate membership in the `Source` StrEnum**, raising `InvalidParameter`
(422) if it is not a member; the md5 is then computed with the **uppercased** value. So public URLs are
accepted case-insensitively (`/recalls/cpsc/24-158` resolves identically to `/recalls/CPSC/24-158`):

```python
try:
    src = Source(source.upper())          # case-insensitive accept; storage is uppercase
except ValueError:
    raise InvalidParameter(f"unknown source {source!r}; expected one of {[s.value for s in Source]}")
```

A syntactically valid `{source}/{recall_id}` that matches no row → `404 ResourceNotFound`. The detail
projection is the **full wide row** (`RecallDetail`, Section B.6) — every column of Mart 1, with the
jsonb rollups deserialized into typed sub-models. No `match`-on-source is needed for the lookup (the md5
is source-agnostic once `source` is uppercased), but the **response** surfaces source-native fields
(`classification`, `risk_level`, `lifecycle_status`, `is_active`) exactly as stored.

**OpenAPI copy (verbatim):**

> Returns the complete record for a single recall, identified by its issuing agency and that
> agency's native recall id (e.g. `CPSC/24-001`, `NHTSA/24V-123`, `USDA/PHA-04-2026`). The **source** is
> accepted case-insensitively (`cpsc/24-001` resolves the same as `CPSC/24-001`); the id is then resolved
> by surrogate key, so it is an exact, case-sensitive match on the native recall id. **Field caveats:**
> `classification`, `risk_level`, and `lifecycle_status` are **source-native** (e.g. `risk_level` is
> USDA-only; `classification` differs per source); `is_active` is `null` for CPSC and NHTSA. `hazards`,
> `product_upcs`, and the geo arrays are arrays of strings/objects that may be empty or `null`.
> `distribution_states` is a single descriptive string (the agency's prose), distinct from
> `distribution_state_codes`, the parsed 2-letter USPS codes.

---

### A.3 `GET /products/search` (mart_product_search)

```python
@router.get(
    "/products/search",
    response_model=Page[ProductSearchHit],
    responses=LIST_ERRORS,  # 422 covers the require-one-of rule
    summary="Search recalled products by keyword (full-text) or exact identifier.",
)
async def search_products(
    db: Annotated[AsyncConnection, Depends(get_conn)],
    q: Annotated[str | None, Query(
        min_length=2, max_length=200,
        description="Free-text keywords (Postgres websearch syntax). Token/prefix match only — NO fuzzy/typo.",
    )] = None,
    hin: Annotated[str | None, Query(max_length=64, description="Exact USCG Hull ID.")] = None,
    model: Annotated[str | None, Query(max_length=128, description="Exact product model.")] = None,
    upc: Annotated[str | None, Query(
        max_length=32,
        description="UPC — matched at the RECALL level via containment (see caveat), not product-grain.",
    )] = None,
    source: Annotated[Source | None, Query(description="Optional source filter, AND-ed with the above.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query()] = None,
    with_total: Annotated[bool, Query()] = False,
) -> Page[ProductSearchHit]: ...
```

**Require-one-of rule (422).** At least one of `q | hin | model | upc` MUST be supplied; zero of them →
`422 InvalidParameter` with a clear message. Validate in a tiny dependency so it lands in the *same*
422 envelope as Query-constraint failures (and is testable without the DB):

```python
def require_one_search_term(
    q: str | None = None, hin: str | None = None,
    model: str | None = None, upc: str | None = None,
) -> None:
    if q is None and hin is None and model is None and upc is None:
        raise RequestValidationError([{
            "loc": ("query",), "type": "value_error.missing_any",
            "msg": "Provide at least one of: q, hin, model, upc.",
        }])
# router decorator: dependencies=[Depends(require_one_search_term)]
```

**Path dispatch (FTS vs identifier).** Use `match` over which terms are present (precedence:
identifiers are exact and cheap, so honor them when given; `q` is the keyword path). The paths differ in
**ordering** and **`rank`**:

| Path | Trigger | Predicate / column | Index (01 — Mart 2) | Order | `rank` |
|---|---|---|---|---|---|
| FTS | `q` present | `search_vector @@ websearch_to_tsquery('english', :q)` | `GIN(search_vector)` | `ts_rank_cd(search_vector, query) DESC, recall_product_id` | **float** |
| HIN | `hin` present | `hin = :hin` | `btree(hin)` | `published_at DESC, recall_product_id` | `None` |
| Model | `model` present | `model = :model` | `btree(model)` | `published_at DESC, recall_product_id` | `None` |
| UPC | `upc` present | `recall_product_upcs @> to_jsonb(array[:upc])` (containment) | none (jsonb scan) | `published_at DESC, recall_product_id` | `None` |
| + source | any path | `AND source = :source` | composite n/a | — | — |

> The query builder lives in **04**; when multiple terms are given they are AND-ed. The keyset cursor on
> the FTS path encodes `(rank, recall_product_id)` and is **application-level over the matched set** —
> `rank` is not an ordered btree path (GIN serves the `@@` match, not the sort), which is fine because
> the matched set is small (01 — Mart 2). The identifier/UPC paths keyset on `(published_at,
> recall_product_id)`.

**Honest caveats baked into the response** (Section B.7): `ProductSearchHit.rank` is `float | None`
(populated only on the `q` path); a constant `upc_is_recall_level: Literal[True]` documents that the
per-product `upc` column is **NULL for every row today** and that `?upc=` matched the recall-level
`recall_product_upcs` array via containment — so a UPC miss must **not** be read as "this UPC was never
recalled."

**OpenAPI copy (verbatim):**

> Searches recalled products two ways. **Keyword (`q`)** runs a Postgres full-text search over product
> name, description, recall title, and firm name, ranked by relevance (`rank`). It is **token/prefix
> matching only — there is NO fuzzy or typo-tolerant search** (trigram matching is not enabled), so
> spelling matters. **Identifier** lookups (`hin`, `model`) are exact matches. **`upc` is special:** the
> per-product UPC field is currently empty for every record, so `upc` is matched against the
> **recall-level** UPC list using containment, and every hit carries `upc_is_recall_level: true`. A miss
> therefore means "no recall lists this UPC at the recall level," not necessarily "this product was never
> recalled." You must supply at least one of `q`, `hin`, `model`, or `upc` (otherwise 422). Results are
> keyset-paginated; `rank` is present only for keyword searches.

---

### A.4 `GET /firms/{id}` — firm profile (mart_firm_profile)

```python
@router.get(
    "/firms/{firm_id}",
    response_model=FirmProfile,
    responses=ITEM_ERRORS,  # 404 + 422 + 503 (+429); no 400, no pagination
    summary="Fetch a canonical (cross-source) firm profile, including agency registration sidecars.",
)
async def get_firm(
    db: Annotated[AsyncConnection, Depends(get_conn)],
    firm_id: Annotated[str, Path(
        min_length=32, max_length=32,
        pattern=r"^[0-9a-f]{32}$",
        description="Opaque canonical firm id (md5 cluster id).",
    )],
) -> FirmProfile: ...
```

**Lookup (01 — Mart 3).** Single point read on `WHERE firm_id = :firm_id` → `UNIQUE(firm_id)`. `firm_id
= md5(upper(trim(name)))`; treat as opaque (the `^[0-9a-f]{32}$` pattern is a cheap shape guard — a
malformed id fails the pattern → 422 before touching the DB; a well-formed id with no row → 404). No
pagination. The three per-source sidecar arrays map straight from the source-aligned mart columns
`firm_usda_attributes` (USDA), `firm_uscg_attributes` (USCG), `firm_fda_attributes` (FDA) into three
distinct sub-model lists (Section B.8); CPSC/NHTSA have no sidecar.

**OpenAPI copy (verbatim):**

> Returns one canonical firm — the cross-source cluster, so a manufacturer that appears under several
> agencies (e.g. Honda under NHTSA and USCG) collapses to a single profile. Includes recall counts,
> per-source breakdown (`recalls_by_source`), observed name variants, and **agency registration
> sidecars**: `firm_usda_attributes` (USDA/FSIS establishments), `firm_uscg_attributes` (USCG boat
> manufacturer / MIC records), and `firm_fda_attributes` (FDA FEI firm records). **Caveats:** the three sidecar
> blocks have **different shapes** and any of them may be empty; CPSC and NHTSA contribute **no** sidecar
> (those sources are name-keyed with no registration anchor). `first_recall_at`/`last_recall_at` are
> `null` for a firm with no matched recalls. The id is opaque; obtain it from a recall's `firms[].firm_id`.

---

### A.5 `GET /health` — liveness (no DB)

```python
@router.get("/health", response_model=Health, responses={}, summary="Liveness probe (no DB touch).")
async def health() -> Health:
    return Health(status="ok", version=settings.app_version)
```

Pure, fast, no dependency on the DB pool. Always `200`. `Health` = `{status: Literal["ok"], version: str}`.
Used by Fly.io's `[[services.http_checks]]` for liveness (does **not** wake Neon).

### A.6 `GET /health/db` — readiness (DB)

```python
@router.get(
    "/health/db", response_model=DbHealth, responses={**ERR_503},
    summary="Readiness probe — verifies the read-only DB connection.",
)
async def health_db(db: Annotated[AsyncConnection, Depends(get_conn)]) -> DbHealth:
    # SELECT 1 with the same connect/command timeouts as real traffic;
    # a cold/asleep Neon -> 503 UpstreamUnavailable + Retry-After (decision 14), NOT a hang.
    await db.execute(text("SELECT 1"))
    return DbHealth(status="ok", database="reachable")
```

`200 {status:"ok"}` when the round-trip succeeds; `503 UpstreamUnavailable` (with `Retry-After`) when
Neon is cold/asleep or times out. `DbHealth` = `{status: Literal["ok"], database: Literal["reachable"]}`.
This is the readiness check; keep it **out** of the Fly liveness loop so a sleeping Neon doesn't kill the
app instance.

> **Open item (06 / decision 9):** `/health/db` runs as the dedicated **read-only** role
> (`recalls_readonly` or similar) over the `_RO` connection string — confirm the exact role name, grants,
> pooled-vs-direct endpoint, and env var (`NEON_DATABASE_URL` vs `NEON_DATABASE_URL_RO`) with the operator
> before wiring `db.py`. This doc assumes a `SecretStr`, fail-loud-at-boot settings field (decision 10).

---

## SECTION B — Pydantic v2 response models (field by field)

All response models set `model_config = ConfigDict(from_attributes=True)`. **Why:** SQLAlchemy Core
returns `Row` / `RowMapping` objects (a `Mapping` whose keys are the selected column labels); with
`from_attributes=True`, `RecallSummary.model_validate(row)` reads each field by attribute/key off the row
with no hand-written dict adapter, and Pydantic v2 coerces jsonb (already decoded to Python `list`/`dict`
by asyncpg) and `timestamptz` (→ `datetime`) automatically. We additionally rely on `populate_by_name`
nowhere — the model field names are chosen to **equal the mart column names** so the SELECT label and the
model field line up 1:1 (the few exceptions are aliased in the SELECT, noted per field). All models are
read-only DTOs; none mutate.

> **Null/default discipline (decisions 8, 01 NULL-vs-coalesce):** jsonb rollups the mart leaves
> *un-coalesced* are `NULL` when empty, so the model uses `Field(default_factory=list)` /
> `Field(default_factory=dict)` to normalize `None`→`[]`/`{}`. Because the row may literally contain
> `None` for those columns, we add a `@field_validator(..., mode="before")` that maps `None`→`[]`/`{}`
> (a bare `default_factory` only fills a *missing* key, not an explicit `None`). Scalars that are
> NULL-by-design are typed `| None`.

```python
# recalls_api/models/_coerce.py — shared validators (DRY)
from pydantic import field_validator
def none_to_list(v): return [] if v is None else v
def none_to_dict(v): return {} if v is None else v
```

### B.1 `Source` — the one closed enum

```python
from enum import StrEnum
class Source(StrEnum):
    CPSC = "CPSC"
    FDA = "FDA"
    USDA = "USDA"
    NHTSA = "NHTSA"
    USCG = "USCG"
```

**Why `Source` is a `StrEnum` but `classification`/`type`/`risk_level` are free strings (decision 7,
01):** `source` is a genuinely closed, conformed, cross-source domain of exactly 5 uppercase values
(confirmed `accepted_values` on all three serving marts) — making it a `StrEnum` gives free 422
validation on path/query and a clean OpenAPI enum. `classification`, `type`, and `risk_level` are
**source-native and disjoint** (ADR 0036 D2/D3): `classification` holds FDA `1/2/3/NC`, USDA `Class I/II/III`/`Public Health Alert` *and*
USCG `H/L/M/S` in the same column, `risk_level` is USDA-only, `type` has five disjoint per-source
domains. A global `StrEnum` over them would (a) be wrong (the value spaces don't conform) and (b) lie to
clients about what a value means independent of source. They are therefore **free-string** fields and
**free-string equality filters** whose semantics are documented as source-scoped.

### B.2 `Page[T]` envelope + `Cursor`

```python
from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field
T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)
    items: list[T]
    next_cursor: str | None = Field(default=None, examples=["eyJwIjoiMjAyNi0wMS0wMVQwMDowMDowMFoiLi4ufQ"])
    limit: int = Field(examples=[25])
    total: int | None = Field(default=None, description="Only when with_total=true.", examples=[None])
```

`Cursor` is **not** a response model — it is the opaque, base64url-encoded last-sort-tuple. The codec is
a `Cursor` class in `pagination.py` (**04**) with classmethods `Cursor.encode(...)` / `Cursor.decode(...)`
(pure functions; tamper → `BadCursor` = 400, round-trip + tamper tested in **05**). The router builds the
response envelope via the `build_page(items, limit, next_cursor)` helper (also `pagination.py`). Clients
only ever see/echo the string `next_cursor`; they never construct it.

### B.3 `FirmRef` — the `firms[]` jsonb element

Maps to the jsonb array element `{firm_id, name, role, match_confidence}` (01 — Mart 1, `firms`).

| Field | Python type | Mart source | Default | Notes |
|---|---|---|---|---|
| `firm_id` | `str` | `firms[].firm_id` | required | opaque md5 cluster id; link key to `/firms/{id}` |
| `name` | `str` | `firms[].name` | required | canonical name |
| `role` | `str` | `firms[].role` | required | role enum value as free string (`manufacturer`/`importer`/`distributor`/`establishment`/`filer`) |
| `match_confidence` | `str` | `firms[].match_confidence` | required | opaque confidence label (closed upstream, surfaced as free string) |

```python
class FirmRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    firm_id: str = Field(examples=["7d2c1e5b8a40f0a9f4c7e3a1e3a1c6f2"])
    name: str = Field(examples=["Acme Corporation"])
    role: str = Field(examples=["manufacturer"])
    match_confidence: str = Field(examples=["exact_name"])
```

> `role`/`match_confidence` are typed `str` (not enums) on purpose: they are closed *upstream* but the
> API does not let clients filter on them and should not break if the pipeline adds a value.

### B.4 `Health` / `DbHealth`

```python
from typing import Literal
class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = Field(examples=["1.0.0"])
class DbHealth(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["reachable"] = "reachable"
```

### B.5 `RecallSummary` — the LIST subset (mart_recall_summary)

The list projection (01 — Mart 1; plan §3 list projection). Not the full row — omits the heavy
narrative/geo/jsonb-array columns (those are in `RecallDetail`).

| Field | Python type | Mart column | Default | Notes / examples |
|---|---|---|---|---|
| `recall_event_id` | `str` | `recall_event_id` | required | NOT NULL, UNIQUE |
| `source` | `Source` | `source` | required | coerces the uppercase string into the enum |
| `source_recall_id` | `str` | `source_recall_id` | required | native id |
| `title` | `str \| None` | `title` | `None` | nullable |
| `url` | `str \| None` | `url` | `None` | CPSC/NHTSA may be null |
| `announced_at` | `datetime \| None` | `announced_at` | `None` | NULL-by-design (~20 FDA) |
| `published_at` | `datetime` | `published_at` | required | NOT NULL; sort key |
| `classification` | `str \| None` | `classification` | `None` | source-native free string |
| `risk_level` | `str \| None` | `risk_level` | `None` | USDA-only |
| `lifecycle_status` | `str \| None` | `lifecycle_status` | `None` | NULL for CPSC/NHTSA |
| `is_active` | `bool \| None` | `is_active` | `None` | **tri-state** |
| `reason_category` | `str \| None` | `reason_category` | `None` | USDA-only |
| `distribution_scope` | `str` | `distribution_scope` | required | NOT NULL enum (4 values) — `str`, not StrEnum (kept simple; not a filter) |
| `primary_firm_name` | `str \| None` | `primary_firm_name` | `None` | null for firmless recalls |
| `firm_count` | `int` | `firm_count` | required | coalesced NOT NULL |
| `product_count` | `int` | `product_count` | required | coalesced NOT NULL |
| `edit_event_count` | `int` | `edit_event_count` | required | coalesced NOT NULL |
| `has_been_edited` | `bool` | `has_been_edited` | required | NOT NULL |

```python
from datetime import datetime
class RecallSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    recall_event_id: str
    source: Source
    source_recall_id: str = Field(examples=["24-001"])
    title: str | None = Field(default=None, examples=["Acme Toaster Fire Hazard"])
    url: str | None = None
    announced_at: datetime | None = None
    published_at: datetime
    classification: str | None = Field(default=None, examples=["Class II"])
    risk_level: str | None = Field(default=None, examples=["Low - Class II"])
    lifecycle_status: str | None = None
    is_active: bool | None = Field(default=None, description="Tri-state; null for CPSC/NHTSA.")
    reason_category: str | None = None
    distribution_scope: str = Field(examples=["Nationwide"])
    primary_firm_name: str | None = None
    firm_count: int = 0
    product_count: int = 0
    edit_event_count: int = 0
    has_been_edited: bool = False
```

### B.6 `RecallDetail` — the FULL wide row (mart_recall_summary)

Extends the summary projection with the narrative, geo, lifecycle/observation, and jsonb-rollup columns
(01 — Mart 1, every column). Build it as its own model (not a subclass) so the SELECT and the field list
stay 1:1 and obvious. Summary fields repeat (omitted from the table below for brevity — they are
identical to B.5); the **additional** fields:

| Field | Python type | Mart column | Default | Notes |
|---|---|---|---|---|
| `recall_reason` | `str \| None` | `recall_reason` | `None` | defect narrative |
| `corrective_action` | `str \| None` | `corrective_action` | `None` | — |
| `consequence_of_defect` | `str \| None` | `consequence_of_defect` | `None` | — |
| `distribution_states` | `str \| None` | `distribution_states` | `None` | **SCALAR text** (agency prose) — distinct from the codes array |
| `distribution_state_codes` | `list[str] \| None` | `distribution_state_codes` | `None` | text[]; `None`=no rda row, `[]`=parsed-none |
| `distribution_country_codes` | `list[str] \| None` | `distribution_country_codes` | `None` | text[]; foreign-only (no `US`) |
| `hazards` | `list[Any] \| None` | `hazards` | `None` | opaque jsonb array (element shape unconfirmed — open item) |
| `product_upcs` | `list[str]` | `product_upcs` | `[]` (validator) | recall-level UPCs |
| `product_names` | `list[str]` | `product_names` | `[]` (validator) | un-coalesced jsonb → default `[]` |
| `models` | `list[str]` | `models` | `[]` (validator) | un-coalesced jsonb → default `[]` |
| `hins` | `list[str]` | `hins` | `[]` (validator) | un-coalesced jsonb (USCG Hull IDs) → default `[]` |
| `firms` | `list[FirmRef]` | `firms` | `[]` | coalesced NOT NULL (mart `'[]'`), but validator keeps it safe |
| `first_seen_at` | `datetime \| None` | `first_seen_at` | `None` | pipeline-observation time, **not** recall age |
| `last_seen_at` | `datetime \| None` | `last_seen_at` | `None` | — |
| `edit_count` | `int \| None` | `edit_count` | `None` | distinct content versions |
| `is_currently_active` | `bool \| None` | `is_currently_active` | `None` | USDA+NHTSA only |
| `was_ever_retracted` | `bool \| None` | `was_ever_retracted` | `None` | USDA+NHTSA only |

```python
from typing import Any
class RecallDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # --- identity / summary subset (same types as RecallSummary B.5) ---
    recall_event_id: str
    source: Source
    source_recall_id: str
    title: str | None = None
    url: str | None = None
    announced_at: datetime | None = None
    published_at: datetime
    classification: str | None = None
    risk_level: str | None = None
    lifecycle_status: str | None = None
    is_active: bool | None = None
    reason_category: str | None = None
    distribution_scope: str
    primary_firm_name: str | None = None
    firm_count: int = 0
    product_count: int = 0
    edit_event_count: int = 0
    has_been_edited: bool = False
    # --- detail-only narrative ---
    recall_reason: str | None = None
    corrective_action: str | None = None
    consequence_of_defect: str | None = None
    # --- geo: scalar string vs codes array (do NOT conflate) ---
    distribution_states: str | None = Field(
        default=None, description="Agency prose, e.g. 'Nationwide' or 'CA, OR, WA'.")
    distribution_state_codes: list[str] | None = Field(
        default=None, description="Parsed USPS 2-letter codes; null when unparseable.")
    distribution_country_codes: list[str] | None = Field(
        default=None, description="ISO alpha-2, foreign-only (US excluded by design).")
    # --- jsonb rollups (un-coalesced -> normalize None to []/[]) ---
    hazards: list[Any] | None = Field(default=None, description="Opaque hazard objects; may be null.")
    product_upcs: list[str] = Field(default_factory=list, description="Recall-level UPCs.")
    product_names: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    hins: list[str] = Field(default_factory=list, description="USCG Hull IDs.")
    firms: list[FirmRef] = Field(default_factory=list)
    # --- observation / lifecycle ---
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    edit_count: int | None = None
    is_currently_active: bool | None = None
    was_ever_retracted: bool | None = None

    _v1 = field_validator("product_upcs", "product_names", "models", "hins", "firms",
                          mode="before")(none_to_list)
```

### B.7 `ProductSearchHit` (mart_product_search)

01 — Mart 2 columns; `rank` is added only on the FTS path; `upc_is_recall_level` is a constant honesty
flag.

| Field | Python type | Mart column | Default | Notes |
|---|---|---|---|---|
| `recall_product_id` | `str` | `recall_product_id` | required | UNIQUE; opaque keyset key |
| `recall_event_id` | `str` | `recall_event_id` | required | link to detail (`recalls/{source}/{recall_id}`) |
| `source` | `Source` | `source` | required | — |
| `source_recall_id` | `str` | `source_recall_id` | required | — |
| `product_name` | `str \| None` | `product_name` | `None` | — |
| `product_description` | `str \| None` | `product_description` | `None` | — |
| `model` | `str \| None` | `model` | `None` | btree(model) |
| `type` | `str \| None` | `type` | `None` | disjoint per-source domain — free string |
| `model_year` | `str \| int \| None` | `model_year` | `None` | physical type FLAGGED (int vs text) — model permissively |
| `hin` | `str \| None` | `hin` | `None` | btree(hin), USCG Hull ID |
| `upc` | `str \| None` | `upc` | `None` | **NULL for every row today** (see flag) |
| `recall_title` | `str \| None` | `recall_title` | `None` | = recall summary title |
| `classification` | `str \| None` | `classification` | `None` | from recall_ctx |
| `risk_level` | `str \| None` | `risk_level` | `None` | USDA-only |
| `published_at` | `datetime` | `published_at` | required | NOT NULL |
| `url` | `str \| None` | `url` | `None` | — |
| `is_active` | `bool \| None` | `is_active` | `None` | tri-state |
| `firm_name` | `str \| None` | `firm_name` | `None` | = primary_firm_name; null for firmless |
| `recall_product_upcs` | `list[str]` | `recall_product_upcs` | `[]` (validator) | the real UPC-search target |
| `rank` | `float \| None` | computed `ts_rank_cd(...)` | `None` | **FTS path only**; null on identifier paths |
| `upc_is_recall_level` | `Literal[True]` | constant | `True` | honesty flag (see caveat) |

```python
class ProductSearchHit(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    recall_product_id: str
    recall_event_id: str
    source: Source
    source_recall_id: str
    product_name: str | None = None
    product_description: str | None = None
    model: str | None = None
    type: str | None = Field(default=None, examples=["Frozen ready-to-eat"])
    model_year: str | int | None = Field(default=None, examples=[2019])
    hin: str | None = None
    upc: str | None = Field(default=None, description="Product-grain UPC; currently null for all rows.")
    recall_title: str | None = None
    classification: str | None = None
    risk_level: str | None = None
    published_at: datetime
    url: str | None = None
    is_active: bool | None = None
    firm_name: str | None = None
    recall_product_upcs: list[str] = Field(default_factory=list)
    rank: float | None = Field(default=None, description="Relevance; present only for keyword (q) search.")
    upc_is_recall_level: Literal[True] = Field(
        default=True,
        description="UPC matches are at the recall level (recall_product_upcs), not product-grain.")
    _v = field_validator("recall_product_upcs", mode="before")(none_to_list)
```

### B.8 `FirmProfile` + the 3 per-source sidecars (mart_firm_profile)

01 — Mart 3. Top-level fields:

| Field | Python type | Mart column | Default | Notes |
|---|---|---|---|---|
| `firm_id` | `str` | `firm_id` | required | UNIQUE; path key |
| `canonical_name` | `str` | `canonical_name` | required | NOT NULL |
| `normalized_name` | `str` | `normalized_name` | required | NOT NULL; not unique |
| `observed_names` | `list[str]` | `observed_names` | `[]` (validator) | every raw spelling |
| `observed_company_ids` | `list[str]` | `observed_company_ids` | `[]` (validator) | FEI/`M1234`/MIC; sidecar join keys |
| `alternate_names` | `list[str]` | `alternate_names` | `[]` (validator) | DBA/brand aliases |
| `total_recalls` | `int` | `total_recalls` | required | coalesced NOT NULL |
| `active_recalls` | `int` | `active_recalls` | required | coalesced NOT NULL |
| `first_recall_at` | `datetime \| None` | `first_recall_at` | `None` | un-coalesced |
| `last_recall_at` | `datetime \| None` | `last_recall_at` | `None` | un-coalesced |
| `roles` | `list[str]` | `roles` | `[]` (validator) | un-coalesced jsonb |
| `recalls_by_source` | `dict[str, int]` | `recalls_by_source` | `{}` (validator) | jsonb_object_agg |
| `distinct_products` | `int` | `distinct_products` | required | numeric→int (integral; coalesced 0) |
| `firm_usda_attributes` | `list[UsdaEstablishment]` | `firm_usda_attributes` | `[]` (validator) | **USDA** sidecar |
| `firm_uscg_attributes` | `list[UscgManufacturer]` | `firm_uscg_attributes` | `[]` (validator) | **USCG** sidecar |
| `firm_fda_attributes` | `list[FdaAttributes]` | `firm_fda_attributes` | `[]` (validator) | **FDA** sidecar |

> **Field names are verbatim the mart columns (decision 6, 02 blocker).** The source-aligned names
> `firm_usda_attributes`=USDA, `firm_uscg_attributes`=USCG, `firm_fda_attributes`=FDA are the mart
> columns; the Pydantic fields match them 1:1.

> **NOTE — rename APPLIED (gold-readiness R5).** recommendation 07 #5 (rename the mart sidecar output
> columns to `firm_usda_attributes` / `firm_uscg_attributes` / `firm_fda_attributes`) was applied
> upstream pre-go-live and is live on the read-only role. The pre-rename names
> (`establishment_attributes`=USDA, `manufacturer_attributes`=USCG, `fda_attributes`=FDA) are historical
> only; C7's `queries/firms.py` and `models/firms.py` use the new names (verified live against the mart).

Per-source sub-models. Each jsonb element is a full government attribute row; the **shapes differ**, so
three models (a single shared model is wrong, per 02). **All fields optional except the join key**; type
loosely — the API does not validate every government attribute.

```python
# USDA establishment (firm_usda_attributes, join key establishment_id) — 01 sidecar table
class UsdaEstablishment(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    establishment_id: str                                   # join key (required)
    establishment_name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    county: str | None = None
    fips_code: str | None = None
    geolocation: str | None = None
    latest_mpi_active_date: str | None = None
    grant_date: str | None = None
    status_regulated_est: str | None = None                 # '' or 'Inactive'
    size: str | None = None
    district: str | None = None
    circuit: str | None = None
    activities: str | None = None
    dbas: str | None = None

# USCG manufacturer / MIC (firm_uscg_attributes, join key mic) — 01 sidecar table
class UscgManufacturer(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    mic: str                                                # join key (required)
    company_name: str | None = None
    dba: str | None = None
    parent_company: str | None = None
    parent_mic: str | None = None
    past_company_1: str | None = None
    past_company_2: str | None = None
    past_company_3: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None
    status: str | None = None
    in_business: str | None = None
    out_of_business: str | None = None
    date_modified: str | None = None
    uscg_directory_id: str | None = None
    detail_url: str | None = None
    mic_has_prior_holder: bool | None = None
    mic_oob_recycled: bool | None = None
    mic_renamed_not_recycled: bool | None = None
    prior_holders: list[str] = Field(default_factory=list)  # jsonb array of text

# FDA FEI firm (firm_fda_attributes, join key firm_fei_num cast to text) — 01 sidecar table
class FdaAttributes(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    firm_fei_num: int | str                                 # join key (required); FEI is bigint
    firm_legal_nam: str | None = None
    firm_city_nam: str | None = None
    firm_state_cd: str | None = None
    firm_state_prvnc_nam: str | None = None
    firm_country_nam: str | None = None
    firm_postal_cd: str | None = None
    firm_line1_adr: str | None = None
    firm_line2_adr: str | None = None
    firm_surviving_nam: str | None = None
    firm_surviving_fei: int | str | None = None

class FirmProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    firm_id: str
    canonical_name: str = Field(examples=["Acme Corporation"])
    normalized_name: str
    observed_names: list[str] = Field(default_factory=list)
    observed_company_ids: list[str] = Field(default_factory=list)
    alternate_names: list[str] = Field(default_factory=list)
    total_recalls: int = 0
    active_recalls: int = 0
    first_recall_at: datetime | None = None
    last_recall_at: datetime | None = None
    roles: list[str] = Field(default_factory=list)
    recalls_by_source: dict[str, int] = Field(default_factory=dict, examples=[{"CPSC": 3, "USDA": 1}])
    distinct_products: int = 0
    firm_usda_attributes: list[UsdaEstablishment] = Field(default_factory=list)  # USDA
    firm_uscg_attributes: list[UscgManufacturer] = Field(default_factory=list)   # USCG
    firm_fda_attributes: list[FdaAttributes] = Field(default_factory=list)       # FDA

    _vl = field_validator(
        "observed_names", "observed_company_ids", "alternate_names", "roles",
        "firm_usda_attributes", "firm_uscg_attributes", "firm_fda_attributes",
        mode="before")(none_to_list)
    _vd = field_validator("recalls_by_source", mode="before")(none_to_dict)
```

> `extra="ignore"` on the sidecars makes the API forward-compatible: if the pipeline adds a government
> column to a sidecar row, it is silently dropped rather than breaking deserialization. `prior_holders`
> (USCG) is itself a jsonb array → `list[str]`. FEI fields accept `int | str` because asyncpg returns the
> bigint as `int` even though the join expression casts to text.

---

## SECTION C — filter → SQL predicate → index (idiomatic Python 3.12)

Conditions are appended only when the param is non-`None`; the query builder lives in **04**. Parameters
are always bound (`:name` / SQLAlchemy `bindparam`) — never interpolated.

### C.1 `GET /recalls` (mart_recall_summary)

| Param (`Annotated[...]`) | SQL predicate (bound) | Index (01 — Mart 1) | Notes |
|---|---|---|---|
| `source: Source \| None` | `source = :source` | leads `btree(source, published_at)` | also unlocks index-backed ordering |
| `classification: str \| None` | `classification = :classification` | `btree(classification)` | **equality**, not ILIKE; source-scoped meaning |
| `is_active: bool \| None` | `is_active = :is_active` | `btree(is_active)` | NULL (CPSC/NHTSA) excluded by design |
| `published_after: date \| None` | `published_at >= :published_after::date` | `(source, published_at)` iff `source` present | inclusive from the start of that day (date vs timestamptz) |
| `published_before: date \| None` | `published_at < (:published_before::date + INTERVAL '1 day')` | same | inclusive of the ENTIRE published_before day (decision 4) |
| `firm: str \| None` | `primary_firm_name ILIKE '%' \|\| :firm \|\| '%'` | **none** | seq filter; convenience only |
| keyset `cursor` | `(published_at, recall_event_id) < (:c_pub, :c_id)` | rides ordering | from `Cursor.decode`; bad → 400 |
| ordering (always) | `ORDER BY published_at DESC, recall_event_id DESC` | `(source, published_at)` iff `source` present, else **full sort** | deterministic tiebreak |
| `limit` | `LIMIT :limit + 1` | — | fetch n+1 for `has_next` |
| `with_total` | extra `SELECT count(*)` over same `WHERE` | — | only when `true` |

```python
# 04 owns the builder; shape shown for the contract:
def recalls_predicates(*, source, classification, is_active,
                        published_after, published_before, firm) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    if source is not None:          conds.append(t.c.source == source.value)
    if classification is not None:  conds.append(t.c.classification == classification)
    if is_active is not None:       conds.append(t.c.is_active == is_active)  # == (excludes NULL rows by design)
    if published_after is not None: conds.append(t.c.published_at >= published_after)  # inclusive from start of day
    # inclusive of the ENTIRE published_before day (date vs timestamptz — decision 4):
    if published_before is not None:conds.append(t.c.published_at < (published_before + sa.text("INTERVAL '1 day'")))
    if firm is not None:            conds.append(t.c.primary_firm_name.ilike(f"%{firm}%"))
    return conds
```

### C.2 `GET /products/search` (mart_product_search) — path-dispatched

```python
# Idiomatic match on which term is present (identifiers exact & cheap first; q is the FTS path).
match (q, hin, model, upc):
    case (str(), _, _, _):            # FTS
        where  = sv.op("@@")(func.websearch_to_tsquery("english", bindparam("q")))
        rank   = func.ts_rank_cd(sv, func.websearch_to_tsquery("english", bindparam("q")))
        order  = (rank.desc(), t.c.recall_product_id)        # rank not an ordered index path
    case (None, str(), _, _):         # HIN exact
        where, rank, order = (t.c.hin == hin), None, (t.c.published_at.desc(), t.c.recall_product_id)
    case (None, None, str(), _):      # model exact
        where, rank, order = (t.c.model == model), None, (t.c.published_at.desc(), t.c.recall_product_id)
    case (None, None, None, str()):   # UPC -> recall-level containment
        where = t.c.recall_product_upcs.op("@>")(cast([upc], JSONB))
        rank, order = None, (t.c.published_at.desc(), t.c.recall_product_id)
    case _:
        raise RequestValidationError(...)  # require-one-of -> 422
# optional source filter AND-ed onto `where` on every path.
```

| Param | SQL predicate (bound) | Index (01 — Mart 2) | `rank`? | Order |
|---|---|---|---|---|
| `q: str \| None` | `search_vector @@ websearch_to_tsquery('english', :q)` | `GIN(search_vector)` | yes (`ts_rank_cd`) | `rank DESC, recall_product_id` |
| `hin: str \| None` | `hin = :hin` | `btree(hin)` | no | `published_at DESC, recall_product_id` |
| `model: str \| None` | `model = :model` | `btree(model)` | no | same |
| `upc: str \| None` | `recall_product_upcs @> to_jsonb(array[:upc])` | none (jsonb scan) | no | same |
| `source: Source \| None` | `AND source = :source` | — | — | — |
| keyset | FTS: `(rank, recall_product_id) <` (app-level); id paths: `(published_at, recall_product_id) <` | rides order | — | — |

> No `?upc=` hits the per-product `upc` btree (all-null); UPC always routes to `recall_product_upcs`
> containment. No fuzzy/typo path anywhere (pg_trgm disabled). `websearch_to_tsquery` is injection-safe
> and never raises on malformed input.

---

## Open items / judgment calls (for the build session)

1. **DB role / env var (decision 9, 02 MUST-re-verify):** exact read-only role name, `GRANT SELECT`
   target set, pooled-vs-direct Neon endpoint, `default_transaction_read_only=on`, and the env var
   (`NEON_DATABASE_URL` vs `NEON_DATABASE_URL_RO`). Confirm with the operator before wiring `db.py`
   (settings field is `SecretStr`, fail-loud at boot — decision 10). Carried to **06**.
2. **`hazards` element shape** unconfirmed (01) — modeled as `list[Any] | None`. If a typed shape is
   needed, inspect a live CPSC row; otherwise leave opaque.
3. **`model_year` physical type** FLAGGED int-vs-text — modeled `str | int | None` (permissive).
4. **slowapi / 429** is chosen here, not ADR-ratified (02). `RateLimited` stays in the contract; the
   limiter/limits are an API-repo decision tuned in **06**.
5. **`distinct_products`** is `numeric` in the mart but integer-valued — modeled `int` (safe per 02).
6. **Sidecar `extra="ignore"`** is a forward-compat judgment call so a new government column upstream
   does not break deserialization.
