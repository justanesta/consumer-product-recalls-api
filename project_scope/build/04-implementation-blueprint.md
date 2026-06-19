# 04 — Implementation Blueprint (module-by-module skeletons)

> **⚠️ Post-apply reconciliation (2026-06-19, `feature/api-audit`).** The API **response** contract was narrowed *after* this blueprint was written. The provenance apply **pruned six observability fields** from the response models and the `queries/recalls.py` table literal / `_LIST_COLS` (`is_currently_active`, `was_ever_retracted`, `first_seen_at`, `last_seen_at`, `edit_count`, `edit_event_count`; **kept** `has_been_edited`) and **dropped the all-null per-product `ProductSearchHit.upc`** field from `_HIT_COLS` + the model. The `sa.column(...)`/`_LIST_COLS`/`_HIT_COLS` skeletons below that still include those columns are **pre-prune**; the gold marts still carry them and the `upc=` search path is unchanged. Trust the current `src/recalls_api/` source + [`openapi.json`](../../openapi.json).

> **Purpose.** Hand the build session a real, type-annotated skeleton for **every** module in
> `src/recalls_api/`, plus the per-module key decisions, async pitfalls, and `# TODO(build)` markers.
> This is the *how*. The *what* (column/type/null/enum facts) lives in **03 (API contract)** and is
> ultimately governed by **[01 — Ground Truth](./01-ground-truth-gold-marts.md)**; drift/decisions in
> **[02 — Plan Reconciliation](./02-plan-reconciliation.md)**. Testing/CI is **05**, deploy/ops is
> **06**, gold-layer asks are **07**, the commit plan is **08**.
>
> **Trust order for any fact:** 01 > 02 > the pipeline SQL at commit `39dcbda` > this doc's prose.
> Where this doc shows a column name/type, it is a *convenience copy*; if it ever disagrees with 01,
> 01 wins. Code below is **idiomatic and complete enough to implement against** — but every block
> carries explicit `# TODO(build)` markers the session must resolve (most importantly the read-only
> role/DSN, confirmed with the operator — see §db and 02 "MUST re-verify").

## Conventions applied everywhere (do not re-decide)

| Rule | Value |
|---|---|
| File header | `from __future__ import annotations` first line of every module |
| Types | `Annotated[...]` for FastAPI `Query`/`Path` **and** Pydantic constraints; `\|` unions, never `Optional[...]`; `StrEnum` for `source` only |
| Pydantic | v2; response models `model_config = ConfigDict(extra="ignore")` (gold rows are wider than we project; never `forbid` on responses); `Field(default_factory=list)` / `default_factory=dict` for the documented arrays/maps |
| SQLAlchemy | **Core** (`select()`, `text()`, `sa.column`, `bindparam`) — never ORM; queries are **pure** (build statement + params, no I/O) |
| Async | one event loop; one engine; `async with` everything; never a sync `time.sleep`, sync file/DB call, or un-awaited coroutine on the request path |
| Logging | `structlog` JSON to stdout; `request_id` bound via `contextvars`; mirror pipeline `src/config/logging.py` idiom |
| Errors | every handler emits `{"error": {"type", "detail", "request_id"}}`; the catch-all 500 logs the full traceback and returns an **opaque** body (never SQL/DSN) |
| Source casing | storage is **UPPERCASE**; the API path/filter accepts case-insensitively and uppercases before any md5/SQL |

Repo layout being filled in (plan §2):

```
src/recalls_api/
  __init__.py     settings.py   db.py        pagination.py   deps.py
  errors.py       logging.py    main.py
  routers/        recalls.py    products.py  firms.py        health.py
  models/         common.py     recalls.py   products.py     firms.py
  queries/        recalls.py    products.py  firms.py
```

`models/*` are specified in **03**; this doc gives the `queries/*`, `routers/*`, and the
infrastructure modules. Where a router needs a response model, it is referenced by name (03 owns the
field list).

---

## `settings.py` — pydantic-settings, fail-loud at import

**Key decisions**

- Mirror the pipeline (`src/config/settings.py`): `BaseSettings` + `SettingsConfigDict(env_file=".env", extra="ignore")`, DSN as `SecretStr`.
- **DSN env var:** `NEON_DATABASE_URL_RO` (read-only variant; mirrors the pipeline's `NEON_DATABASE_URL` shape but is a *distinct* var so the API can never be handed the read+write `recalls_app` DSN by accident — see §db and 02 MUST-re-verify item #1). `# TODO(build): confirm exact var name + pooled-vs-direct endpoint with the operator.`
- **Fail-loud:** no module-level instance. Provide `get_settings()` with `@lru_cache` so the *first* access (FastAPI lifespan, see `main.py`) raises `ValidationError` at boot if the DSN is missing — same posture as the pipeline. Do **not** construct at import (importing the module must not require secrets, e.g. for unit tests of pure code).
- Pool sizes, timeouts, cache TTL, and rate-limit knobs are settings (not hardcoded) so deploy can tune per platform without a code change.
- `slowapi` limits are an **API-repo decision, not ADR-ratified** (02) — expose as a knob; default conservatively for a free-tier DB.

```python
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database (read-only) -------------------------------------------------
    # asyncpg DSN: postgresql+asyncpg://recalls_readonly:<pw>@<host>/<db>?ssl=require
    # TODO(build): confirm var name / pooled vs direct endpoint / role with operator (02 #1).
    neon_database_url_ro: SecretStr

    # --- Pool (cold-start tuned for Neon serverless; see db.py) ----------------
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_recycle_seconds: int = Field(default=300, ge=30)  # < Neon idle reap (~300s)
    db_connect_timeout_seconds: float = Field(default=5.0, gt=0)   # cold Neon -> 503, never hang
    db_command_timeout_seconds: float = Field(default=10.0, gt=0)  # statement_timeout per conn

    # --- Runtime ---------------------------------------------------------------
    environment: str = "development"          # development | staging | production
    log_level: str = "INFO"
    log_format: str = ""                      # "" -> JSON in prod (isatty -> console)

    # --- HTTP cache (keyed off nightly ~03:00 UTC transform rebuild; see 06) ---
    cache_max_age_seconds: int = Field(default=300, ge=0)

    # --- Rate limit (slowapi; chosen here, not ADR; tune to free-tier DB) ------
    rate_limit_enabled: bool = True
    rate_limit_default: str = "60/minute"     # slowapi limit-string grammar

    # --- Pagination guards -----------------------------------------------------
    page_limit_default: int = Field(default=25, ge=1, le=100)
    page_limit_max: int = Field(default=100, ge=1, le=100)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Construct once; raises ValidationError at first call if the DSN is missing.

    Called from the FastAPI lifespan so a misconfigured deploy fails *at boot*,
    not on the first request.
    """
    return Settings()  # type: ignore[call-arg]  # fields are env-populated
```

`.env.example` (commit; no secrets):

```dotenv
NEON_DATABASE_URL_RO=postgresql+asyncpg://recalls_readonly:CHANGE_ME@HOST/neondb?ssl=require
ENVIRONMENT=development
LOG_LEVEL=INFO
```

**Async pitfalls:** none here (sync construction). The trap is constructing `Settings()` at module
import — keep it lazy/cached so importing `settings.py` in a unit test never demands a DSN.

---

## `db.py` — async engine, lifespan pool, read-only assertion, healthcheck

**Key decisions**

- **`create_async_engine`** with the `postgresql+asyncpg://` driver. The pipeline uses sync `NullPool`
  (batch jobs); the API is a long-lived server, so it uses a **small bounded async pool**
  (`pool_size~5`, `max_overflow~5`, `pool_pre_ping=True`, `pool_recycle~300`). Recycle MUST stay below
  Neon's idle reap (~300s) so we never hand out a server-closed socket.
- **Cold-start safety (06):** pass a short `connect timeout` and `command_timeout` to asyncpg via
  `connect_args`. A cold/asleep Neon must surface as a timeout we catch and translate to
  `UpstreamUnavailable` (503 + `Retry-After`) — **never hang the request**.
- **Read-only assertion:** the role is read-only by grant (no INSERT/UPDATE/DELETE) **and** ideally
  `default_transaction_read_only=on`. We do **not** trust that alone — at startup we assert the
  connection is read-only by reading `SHOW transaction_read_only` / `SHOW default_transaction_read_only`
  and log it; if a write somehow reaches the DB it fails at the engine (belt and suspenders). We also
  set `statement_timeout` per connection via an event hook (asyncpg has no DSN `options` for it the way
  libpq does, so set it on connect).
- **Lifespan, not events:** the engine is created in the FastAPI `lifespan` (see `main.py`) and stored
  on `app.state.engine`; `get_conn` reads it from the request. Dispose on shutdown.
- We expose **`get_conn`** (a `AsyncConnection`, Core, not ORM `AsyncSession`) — every query module is
  Core. One connection per request via `async with engine.connect()`; the route runs one keyed read.

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from recalls_api.settings import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI

log = structlog.get_logger(__name__)


def make_engine(settings: Settings) -> AsyncEngine:
    """Build the read-only async engine for Neon serverless Postgres.

    Small bounded pool with pre-ping + sub-reap recycle; short connect/command
    timeouts so a cold/asleep Neon fails fast (-> 503) instead of hanging.
    """
    return create_async_engine(
        settings.neon_database_url_ro.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle_seconds,
        connect_args={
            # asyncpg connect args (NOT libpq names):
            "timeout": settings.db_connect_timeout_seconds,        # connect timeout
            "command_timeout": settings.db_command_timeout_seconds,  # per-statement deadline
            "server_settings": {
                # Belt: ask the session itself to refuse writes. The role grant is
                # the suspenders. statement_timeout is a hard ceiling in ms.
                "default_transaction_read_only": "on",
                "statement_timeout": str(int(settings.db_command_timeout_seconds * 1000)),
                "application_name": "recalls-api",
            },
        },
    )


async def open_pool(app: FastAPI, settings: Settings) -> None:
    """Create the engine, verify connectivity + read-only posture once at boot."""
    engine = make_engine(settings)
    async with engine.connect() as conn:
        await _assert_read_only(conn)
    app.state.engine = engine
    log.info("db.pool_open", pool_size=settings.db_pool_size)


async def close_pool(app: FastAPI) -> None:
    engine: AsyncEngine | None = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()
        log.info("db.pool_closed")


async def _assert_read_only(conn: AsyncConnection) -> None:
    """Fail loud at boot if the connection can write. Read-only is a hard invariant."""
    row = (await conn.execute(sa.text("SHOW transaction_read_only"))).scalar_one()
    if row != "on":
        # TODO(build): decide hard-fail vs warn. Recommended: hard-fail in production
        # (the role/DSN is misconfigured); warn in dev where a superuser DSN is common.
        log.warning("db.not_read_only", transaction_read_only=row)


async def healthcheck(conn: AsyncConnection) -> bool:
    """SELECT 1 liveness probe used by GET /health/db."""
    return (await conn.execute(sa.text("SELECT 1"))).scalar_one() == 1


async def get_conn(request: "Request") -> AsyncIterator[AsyncConnection]:  # noqa: F821
    """FastAPI dependency: one read-only Core connection per request.

    Imported by deps.py and re-exported; routes depend on the deps.py alias so
    tests can override a single symbol.
    """
    engine: AsyncEngine = request.app.state.engine
    async with engine.connect() as conn:
        yield conn
```

**Async pitfalls (the big three this module must dodge):**

| Pitfall | How it bites here | Guard in the skeleton |
|---|---|---|
| **Blocking the loop** | a sync `psycopg2`/`sqlalchemy.create_engine` call, or `time.sleep` on cold-start backoff | use `create_async_engine` + asyncpg only; never import the sync engine; any wait is `await asyncio.sleep` |
| **Un-awaited coroutine** | `engine.connect()` returns a context manager; `conn.execute(...)` is a coroutine | always `async with` the engine; always `await conn.execute(...)`; pyright catches the rest |
| **Pool exhaustion on cold Neon** | a hung connect holds a slot; under load all 5+5 slots block forever | `timeout`/`command_timeout` make a cold Neon raise fast; `errors.py` maps `TimeoutError`/`OperationalError` -> 503 so the slot is released, not held |

**`# TODO(build)`:** confirm role name + grants + pooled (PgBouncer) vs direct endpoint with the
operator before wiring the DSN (02 #1). If pooled (PgBouncer transaction mode) is used, `server_settings`
that must persist across statements (`statement_timeout`) may not stick — in transaction-pooling mode
set them per-statement instead or use the *direct* endpoint for the API.

---

## `pagination.py` — pure keyset codec + WHERE/ORDER builders

**Key decisions**

- **Keyset (seek), never OFFSET** (ADR 0024 §3; locked). Cursor encodes the **last row's sort tuple**.
- **Opaque base64url** cursor; tamper/garbage decode raises **`BadCursor`** (-> 400). Round-trip via a
  small typed payload (we use JSON inside the b64 so the tuple types survive; datetimes as ISO strings).
- **`limit+1`** fetch to compute `has_next` without a COUNT. No COUNT by default; `?with_total=true` is
  an opt-in handled in the query module (a separate `count()` statement), not here.
- **Two order shapes** (01 "Keyset sort keys"):
  1. recalls list: `(published_at DESC, recall_event_id ASC)` — tiebreak on the UNIQUE key.
  2. product identifier path: `(published_at DESC, recall_product_id ASC)`.
  3. product FTS path: `(ts_rank_cd DESC, recall_product_id ASC)` — **rank is not an index path**
     (01); the keyset is application-level over the matched set. The cursor carries the float rank +
     the id. Floats in a cursor are fine (we compare with the *same* expression in the WHERE).
- These functions are **pure** (no DB handle) and fully unit-tested without a database (05).
- The keyset WHERE for a `DESC, ASC` compound is the row-value comparison:
  `(published_at, recall_event_id) < (:cur_pub, :cur_id)` — but Postgres row-value `<` would require
  matching ASC/ASC. With **DESC then ASC** we expand it explicitly:
  `published_at < :p OR (published_at = :p AND recall_event_id > :id)`. The builder returns this as a
  SQLAlchemy `ColumnElement` with **bound params** (never string-interpolated).

```python
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql.elements import ColumnElement

from recalls_api.errors import BadCursor


@dataclass(frozen=True, slots=True)
class Cursor:
    """The decoded last-row sort tuple. Field set depends on the order shape."""

    values: tuple[Any, ...]   # e.g. (published_at_iso, recall_event_id) or (rank, recall_product_id)

    def encode(self) -> str:
        raw = json.dumps(list(self.values), separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")  # drop padding

    @classmethod
    def decode(cls, token: str) -> "Cursor":
        try:
            pad = "=" * (-len(token) % 4)
            raw = base64.urlsafe_b64decode(token + pad)
            values = json.loads(raw)
            if not isinstance(values, list):
                raise BadCursor("cursor payload is not a tuple")
            return cls(values=tuple(values))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise BadCursor("malformed pagination cursor") from exc


def published_at_keyset_where(
    cursor: Cursor,
    pub_col: ColumnElement[datetime],
    id_col: ColumnElement[str],
) -> ColumnElement[bool]:
    """WHERE for ORDER BY (published_at DESC, id ASC) seek. Bound params only."""
    cur_pub, cur_id = cursor.values  # (iso8601 str, id)
    p = sa.bindparam("cur_pub", cur_pub)
    i = sa.bindparam("cur_id", cur_id)
    return sa.or_(pub_col < p, sa.and_(pub_col == p, id_col > i))


def rank_keyset_where(
    cursor: Cursor,
    rank_expr: ColumnElement[float],
    id_col: ColumnElement[str],
) -> ColumnElement[bool]:
    """WHERE for ORDER BY (ts_rank_cd DESC, recall_product_id ASC) seek."""
    cur_rank, cur_id = cursor.values
    r = sa.bindparam("cur_rank", cur_rank)
    i = sa.bindparam("cur_id", cur_id)
    return sa.or_(rank_expr < r, sa.and_(rank_expr == r, id_col > i))


def slice_page(rows: list[Any], limit: int) -> tuple[list[Any], bool]:
    """Given limit+1 rows, return (page_rows, has_next)."""
    has_next = len(rows) > limit
    return (rows[:limit], has_next)


def build_page(
    items: list[Any], limit: int, next_cursor: str | None, total: int | None = None
) -> "Page[Any]":
    """Construct the Page[T] envelope {items, next_cursor, limit (+ optional total)}.

    The single helper every router calls so the envelope shape is built in one place
    (replaces an ad-hoc `Page[...].build(...)` classmethod). `Page` is imported from
    models.common; the import is local to avoid a circular import with the pure codec.
    """
    from recalls_api.models.common import Page

    return Page(items=items, next_cursor=next_cursor, limit=limit, total=total)
```

**Async pitfalls:** none — this module is intentionally I/O-free and sync. The trap is *leaking* a DB
call in here; keep it pure so the unit tests need no Postgres (05).

`# TODO(build)`: the recalls cursor stores `published_at` as the ISO string that the row produced;
verify the round-trip compares equal in Postgres (timestamptz text vs param). Bind it as a `str` and
cast in SQL (`:cur_pub::timestamptz`) **or** bind a real `datetime` — pick one and unit-test the seam.

---

## `deps.py` — shared `Depends`

**Key decisions**

- Re-export `get_conn` from `db.py` as the single overridable symbol (tests override `deps.get_conn`).
- `PaginationParams` and `RecallFilters` are **`Annotated`-`Query` dataclasses** used as a sub-dependency
  so each router signature stays clean and the validation lives in one place. Clamp `limit` to
  `settings.page_limit_max`. Source is accepted case-insensitively and normalized to the `Source` enum.
- Filters carry **only** what the mart indexes/columns support (01): `source`, `classification`
  (free string), `is_active` (tri-state — `None` means "no filter", `True`/`False` filter and
  intentionally exclude NULL rows; document in 03 OpenAPI copy), `published_after`/`published_before`,
  `firm` (ILIKE substring, no index — accept the cost).

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, Query

from recalls_api.db import get_conn as get_conn  # re-export; tests override deps.get_conn
from recalls_api.models.common import Source
from recalls_api.pagination import Cursor
from recalls_api.settings import Settings, get_settings


@dataclass(slots=True)
class PaginationParams:
    limit: int
    cursor: Cursor | None
    with_total: bool


def pagination_params(
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query()] = None,
    with_total: Annotated[bool, Query()] = False,
) -> PaginationParams:
    clamped = min(limit, settings.page_limit_max)
    return PaginationParams(
        limit=clamped,
        cursor=Cursor.decode(cursor) if cursor else None,  # raises BadCursor -> 400
        with_total=with_total,
    )


@dataclass(slots=True)
class RecallFilters:
    source: Source | None
    classification: str | None
    is_active: bool | None
    published_after: date | None
    published_before: date | None
    firm: str | None


def recall_filters(
    source: Annotated[Source | None, Query()] = None,
    classification: Annotated[str | None, Query(max_length=100)] = None,
    is_active: Annotated[bool | None, Query()] = None,
    published_after: Annotated[date | None, Query()] = None,
    published_before: Annotated[date | None, Query()] = None,
    firm: Annotated[str | None, Query(min_length=2, max_length=200)] = None,
) -> RecallFilters:
    return RecallFilters(source, classification, is_active, published_after, published_before, firm)
```

**Async pitfalls:** keep dependencies thin and sync where possible (these are CPU-trivial); the only
async dependency is `get_conn`. Do not put a DB round-trip in a `Depends` that every route shares
unless it's intended (it isn't here — the route does the one keyed read).

---

## `queries/` — SQLAlchemy Core builders (PURE, no I/O)

**Shared key decisions for all three query modules**

- Each function returns a `sa.Select` (or a `(Select, params)` pair) — it **does not** execute. The
  router awaits `conn.execute(stmt)`. This is the pipeline's "pure-logic seam" (plan §2).
- We model the marts as lightweight **`sa.table(...)` / `sa.column(...)`** literals (no reflection, no
  ORM, no metadata round-trip at import). Column names are copied from 01; **01 is authoritative** if
  they ever drift. Use `# TODO(build)` to add any column 03's response model needs that is missing here.
- **Every** value is a bound param. Conditional `.where(...)` is appended **only when the param is set**
  (`if filters.source is not None: stmt = stmt.where(...)`).
- `published_at` is NOT NULL (01) so it is safe as the primary sort key; the keyset tiebreak is the
  UNIQUE id column.

### `queries/recalls.py`

```python
from __future__ import annotations

import hashlib

import sqlalchemy as sa
from sqlalchemy import Select

from recalls_api.deps import RecallFilters
from recalls_api.models.common import Source
from recalls_api.pagination import Cursor, published_at_keyset_where

# Mart literal — names per 01 Mart 1. extra columns the detail needs are added in DETAIL_COLS.
recall_summary = sa.table(
    "mart_recall_summary",
    sa.column("recall_event_id", sa.Text),
    sa.column("source", sa.Text),
    sa.column("source_recall_id", sa.Text),
    sa.column("title", sa.Text),
    sa.column("recall_reason", sa.Text),
    sa.column("url", sa.Text),
    sa.column("announced_at", sa.TIMESTAMP(timezone=True)),
    sa.column("published_at", sa.TIMESTAMP(timezone=True)),
    sa.column("classification", sa.Text),
    sa.column("risk_level", sa.Text),
    sa.column("lifecycle_status", sa.Text),
    sa.column("is_active", sa.Boolean),
    sa.column("reason_category", sa.Text),
    sa.column("distribution_scope", sa.Text),
    sa.column("distribution_states", sa.Text),                 # SCALAR text (01) — not the array
    sa.column("distribution_state_codes", sa.ARRAY(sa.Text)),  # text[]
    sa.column("distribution_country_codes", sa.ARRAY(sa.Text)),
    sa.column("hazards", sa.JSON),
    sa.column("product_upcs", sa.JSON),
    sa.column("corrective_action", sa.Text),
    sa.column("consequence_of_defect", sa.Text),
    sa.column("primary_firm_name", sa.Text),
    sa.column("firm_count", sa.BigInteger),
    sa.column("firms", sa.JSON),
    sa.column("product_count", sa.BigInteger),
    sa.column("product_names", sa.JSON),
    sa.column("models", sa.JSON),
    sa.column("hins", sa.JSON),
    sa.column("first_seen_at", sa.TIMESTAMP(timezone=True)),
    sa.column("last_seen_at", sa.TIMESTAMP(timezone=True)),
    sa.column("edit_count", sa.Integer),
    sa.column("is_currently_active", sa.Boolean),
    sa.column("was_ever_retracted", sa.Boolean),
    sa.column("edit_event_count", sa.BigInteger),
    sa.column("has_been_edited", sa.Boolean),
)

# List projection (small payload; plan §3). Detail uses recall_summary.c (full row).
_LIST_COLS = (
    recall_summary.c.recall_event_id, recall_summary.c.source,
    recall_summary.c.source_recall_id, recall_summary.c.title,
    recall_summary.c.recall_reason, recall_summary.c.url,
    recall_summary.c.announced_at, recall_summary.c.published_at,
    recall_summary.c.classification, recall_summary.c.risk_level,
    recall_summary.c.lifecycle_status, recall_summary.c.is_active,
    recall_summary.c.reason_category, recall_summary.c.primary_firm_name,
    recall_summary.c.firm_count, recall_summary.c.product_count,
    recall_summary.c.edit_event_count, recall_summary.c.has_been_edited,
)


def compute_recall_event_id(source: str, recall_id: str) -> str:
    """md5(f"{SOURCE_UPPER}|{recall_id}") — the detail-endpoint key (01, confirmed)."""
    return hashlib.md5(f"{source.upper()}|{recall_id}".encode()).hexdigest()


def detail_stmt(source: str, recall_id: str) -> Select:
    """Point read on UNIQUE(recall_event_id). No new index needed (01)."""
    key = compute_recall_event_id(source, recall_id)
    return sa.select(recall_summary).where(
        recall_summary.c.recall_event_id == sa.bindparam("rid", key)
    )


def list_stmt(filters: RecallFilters, cursor: Cursor | None, limit: int) -> Select:
    """Keyset list. Conditional .where only when a param is set. Fetch limit+1.

    CAVEAT (01 / 02 blocker): an UNFILTERED ORDER BY published_at DESC is NOT
    index-backed (only (source, published_at) composite exists). Index-backed
    only when ?source= leads. Document the full-sort cost; steer deep pagination
    behind ?source= in 03 OpenAPI copy.
    """
    stmt = sa.select(*_LIST_COLS)

    if filters.source is not None:
        stmt = stmt.where(recall_summary.c.source == sa.bindparam("source", filters.source.value))
    if filters.classification is not None:
        stmt = stmt.where(
            recall_summary.c.classification == sa.bindparam("classification", filters.classification)
        )
    if filters.is_active is not None:  # True/False filters; None = no filter (keeps NULL rows)
        stmt = stmt.where(recall_summary.c.is_active == sa.bindparam("is_active", filters.is_active))
    if filters.published_after is not None:
        # Inclusive from the start of the published_after calendar day.
        stmt = stmt.where(recall_summary.c.published_at >= sa.bindparam("pub_after", filters.published_after))
    if filters.published_before is not None:
        # Inclusive of the ENTIRE published_before calendar day: the params are calendar dates
        # compared against a timestamptz column, so a bare `<`/`<=` against the date would silently
        # drop same-day rows. Compare against (date + 1 day) with a strict `<` instead. (decision 4)
        stmt = stmt.where(
            recall_summary.c.published_at
            < (sa.bindparam("pub_before", filters.published_before) + sa.text("INTERVAL '1 day'"))
        )
    if filters.firm is not None:  # substring, no index (02 confirmed) — accept seq cost
        stmt = stmt.where(recall_summary.c.primary_firm_name.ilike(sa.bindparam("firm", f"%{filters.firm}%")))

    if cursor is not None:
        stmt = stmt.where(
            published_at_keyset_where(
                cursor, recall_summary.c.published_at, recall_summary.c.recall_event_id
            )
        )

    return stmt.order_by(
        recall_summary.c.published_at.desc(), recall_summary.c.recall_event_id.asc()
    ).limit(limit + 1)  # limit+1 -> has_next


def list_count_stmt(filters: RecallFilters) -> Select:
    """Optional COUNT for ?with_total=true. Reuses the same WHERE (sans cursor/limit)."""
    base = list_stmt(filters, cursor=None, limit=0).limit(None).order_by(None)
    return sa.select(sa.func.count()).select_from(base.subquery())
```

### `queries/products.py`

**Key decisions** (01 Mart 2): FTS via `websearch_to_tsquery('english', :q)` over `search_vector`
(GIN), ranked by `ts_rank_cd`. Identifier path = exact btree on `hin`/`model`. **UPC routes to
`recall_product_upcs` jsonb containment** (the per-row `upc` column is NULL for every row — do NOT
query it). Require at least one of `q|hin|model|upc` or the router 422s (`InvalidParameter`).

```python
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Select
from sqlalchemy.dialects.postgresql import JSONB

from recalls_api.pagination import Cursor, published_at_keyset_where, rank_keyset_where

product_search = sa.table(
    "mart_product_search",
    sa.column("recall_product_id", sa.Text),
    sa.column("recall_event_id", sa.Text),
    sa.column("source", sa.Text),
    sa.column("source_recall_id", sa.Text),
    sa.column("product_name", sa.Text),
    sa.column("product_description", sa.Text),
    sa.column("model", sa.Text),
    sa.column("type", sa.Text),
    sa.column("model_year", sa.Text),     # FLAGGED int|text (01) -> read as str; model permissively
    sa.column("hin", sa.Text),
    sa.column("upc", sa.Text),            # ALL-NULL today — never filter on this
    sa.column("recall_title", sa.Text),
    sa.column("classification", sa.Text),
    sa.column("risk_level", sa.Text),
    sa.column("published_at", sa.TIMESTAMP(timezone=True)),
    sa.column("url", sa.Text),
    sa.column("is_active", sa.Boolean),
    sa.column("firm_name", sa.Text),
    sa.column("recall_product_upcs", sa.JSON),  # recall-level UPC array — the real UPC path
    # search_vector (tsvector) is referenced via literal_column in the FTS predicate.
)

_HIT_COLS = (
    product_search.c.recall_product_id, product_search.c.recall_event_id,
    product_search.c.source, product_search.c.source_recall_id,
    product_search.c.product_name, product_search.c.product_description,
    product_search.c.model, product_search.c.type, product_search.c.model_year,
    product_search.c.hin, product_search.c.recall_title, product_search.c.classification,
    product_search.c.risk_level, product_search.c.published_at, product_search.c.url,
    product_search.c.is_active, product_search.c.firm_name,
)

_search_vector = sa.literal_column("search_vector")  # tsvector; GIN-indexed


def fts_stmt(q: str, cursor: Cursor | None, limit: int) -> Select:
    """Relevance FTS. websearch_to_tsquery is injection-safe and never raises (01)."""
    tsquery = sa.func.websearch_to_tsquery(sa.literal("english"), sa.bindparam("q", q))
    rank = sa.func.ts_rank_cd(_search_vector, tsquery).label("rank")
    stmt = sa.select(*_HIT_COLS, rank).where(_search_vector.op("@@")(tsquery))
    if cursor is not None:
        stmt = stmt.where(rank_keyset_where(cursor, rank, product_search.c.recall_product_id))
    # NOTE: rank is NOT an ordered index path (GIN serves @@, not the sort) — sort is
    # over the (small) matched set; keyset is application-level. (01)
    return stmt.order_by(rank.desc(), product_search.c.recall_product_id.asc()).limit(limit + 1)


def identifier_stmt(
    *, hin: str | None, model: str | None, cursor: Cursor | None, limit: int
) -> Select:
    """Exact identifier lookup (btree on hin/model). At least one provided (router enforces)."""
    stmt = sa.select(*_HIT_COLS)
    if hin is not None:
        stmt = stmt.where(product_search.c.hin == sa.bindparam("hin", hin))
    if model is not None:
        stmt = stmt.where(product_search.c.model == sa.bindparam("model", model))
    if cursor is not None:
        stmt = stmt.where(
            published_at_keyset_where(
                cursor, product_search.c.published_at, product_search.c.recall_product_id
            )
        )
    return stmt.order_by(
        product_search.c.published_at.desc(), product_search.c.recall_product_id.asc()
    ).limit(limit + 1)


def upc_stmt(upc: str, cursor: Cursor | None, limit: int) -> Select:
    """UPC search via jsonb CONTAINMENT on recall-level recall_product_upcs (the per-row
    upc column is all-null). recall_product_upcs @> '["<upc>"]'::jsonb. (01)
    """
    contains = sa.cast(product_search.c.recall_product_upcs, JSONB).op("@>")(
        sa.cast(sa.bindparam("upc_arr", [upc]), JSONB)
    )
    stmt = sa.select(*_HIT_COLS).where(contains)
    if cursor is not None:
        stmt = stmt.where(
            published_at_keyset_where(
                cursor, product_search.c.published_at, product_search.c.recall_product_id
            )
        )
    return stmt.order_by(
        product_search.c.published_at.desc(), product_search.c.recall_product_id.asc()
    ).limit(limit + 1)
```

`# TODO(build)`: confirm the jsonb containment param shape — `recall_product_upcs` is a jsonb array of
text; `@> '["012345678905"]'` matches if the UPC is an element. Verify against a seeded row that the
cast/bindparam path emits `$1::jsonb` with `["<upc>"]` and not a scalar.

### `queries/firms.py`

**Key decisions** (01 Mart 3): single point read on `UNIQUE(firm_id)`; no pagination. The three
sidecars use the source-aligned mart names (R5 applied) — `firm_usda_attributes` (USDA),
`firm_uscg_attributes` (USCG), `firm_fda_attributes` (FDA) — and feed per-source sub-models in 03.

```python
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Select

firm_profile = sa.table(
    "mart_firm_profile",
    sa.column("firm_id", sa.Text),
    sa.column("canonical_name", sa.Text),
    sa.column("normalized_name", sa.Text),
    sa.column("observed_names", sa.JSON),
    sa.column("observed_company_ids", sa.JSON),
    sa.column("alternate_names", sa.JSON),
    sa.column("total_recalls", sa.BigInteger),
    sa.column("active_recalls", sa.BigInteger),
    sa.column("first_recall_at", sa.TIMESTAMP(timezone=True)),
    sa.column("last_recall_at", sa.TIMESTAMP(timezone=True)),
    sa.column("roles", sa.JSON),
    sa.column("recalls_by_source", sa.JSON),
    sa.column("distinct_products", sa.Numeric),         # numeric, integer-valued -> model int (01)
    sa.column("firm_usda_attributes", sa.JSON),         # USDA — source-aligned name (R5)
    sa.column("firm_uscg_attributes", sa.JSON),         # USCG — source-aligned name (R5)
    sa.column("firm_fda_attributes", sa.JSON),          # FDA  — source-aligned name (R5)
)


def firm_stmt(firm_id: str) -> Select:
    """Point read on UNIQUE(firm_id). firm_id is an opaque md5 path param (01)."""
    return sa.select(firm_profile).where(
        firm_profile.c.firm_id == sa.bindparam("firm_id", firm_id)
    )
```

**Async pitfalls for `queries/*`:** these are pure (no `await`) — the trap is accidentally executing
here. Keep execution in routers. Also: never f-string a value into SQL; the one f-string allowed is the
ILIKE wildcard wrapper which is itself a **bound param value** (`f"%{firm}%"` is the *value* passed to
`bindparam`, not interpolated into SQL text).

---

## `routers/` — async routes, `Annotated` Query/Path, `responses=`

**Shared key decisions**

- Each route: `async def`, depends on `get_conn` (via `deps`) + the relevant params dependency, declares
  `response_model=...` (03) and `responses={404: ..., 422: ..., 503: ...}` so OpenAPI documents the error
  envelope. Set `Cache-Control`/`ETag` headers (06) on success.
- The **detail** route uppercases & validates `{source}` against `Source` (a 422 for an unknown source
  via `InvalidParameter`), computes the md5, runs `detail_stmt`, and on no row raises `ResourceNotFound`.
- The `match` statement is used in `products.py` to **dispatch the search path** (FTS vs identifier vs
  UPC) from the provided params — clearer than if/elif and exhaustive.

### `routers/recalls.py`

```python
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.errors import ResourceNotFound
from recalls_api.models.common import Page, Source
from recalls_api.models.recalls import RecallDetail, RecallSummary
from recalls_api.pagination import Cursor, build_page, slice_page
from recalls_api.queries import recalls as q

router = APIRouter(prefix="/recalls", tags=["recalls"])
log = structlog.get_logger(__name__)


@router.get("", response_model=Page[RecallSummary])
async def list_recalls(
    filters: Annotated[deps.RecallFilters, Depends(deps.recall_filters)],
    page: Annotated[deps.PaginationParams, Depends(deps.pagination_params)],
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
) -> Page[RecallSummary]:
    rows = (await conn.execute(q.list_stmt(filters, page.cursor, page.limit))).mappings().all()
    items, has_next = slice_page(list(rows), page.limit)
    next_cursor = (
        Cursor((items[-1]["published_at"].isoformat(), items[-1]["recall_event_id"])).encode()
        if has_next and items else None
    )
    total = None
    if page.with_total:
        total = (await conn.execute(q.list_count_stmt(filters))).scalar_one()
    return build_page(items, limit=page.limit, next_cursor=next_cursor, total=total)


@router.get("/{source}/{recall_id}", response_model=RecallDetail,
            responses={404: {"description": "Recall not found"}})
async def get_recall(
    source: Annotated[str, Path(description="One of CPSC/FDA/USDA/NHTSA/USCG (case-insensitive)")],
    recall_id: Annotated[str, Path(description="The source-native recall id")],
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
) -> RecallDetail:
    src = Source(source.upper())  # invalid -> ValueError; mapped to 422 (see TODO)
    row = (await conn.execute(q.detail_stmt(src.value, recall_id))).mappings().one_or_none()
    if row is None:
        raise ResourceNotFound(f"no recall for {src.value}/{recall_id}")
    return RecallDetail.model_validate(dict(row))
```

`# TODO(build)`: catch the `Source(source.upper())` `ValueError` and raise `InvalidParameter` (422) with
a list of valid sources — either a small `parse_source()` helper in `models/common.py` or a Path
validator. Don't let a raw `ValueError` reach the catch-all 500.

### `routers/products.py` (the `match` dispatch)

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.errors import InvalidParameter
from recalls_api.models.common import Page
from recalls_api.models.products import ProductSearchHit
from recalls_api.pagination import Cursor, build_page, slice_page
from recalls_api.queries import products as q

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/search", response_model=Page[ProductSearchHit])
async def search_products(
    page: Annotated[deps.PaginationParams, Depends(deps.pagination_params)],
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    q_text: Annotated[str | None, Query(alias="q", min_length=2, max_length=200)] = None,
    hin: Annotated[str | None, Query(max_length=64)] = None,
    model: Annotated[str | None, Query(max_length=128)] = None,
    upc: Annotated[str | None, Query(max_length=64)] = None,
) -> Page[ProductSearchHit]:
    # Require at least one selector; dispatch by precedence. (Locked decision #5)
    match (q_text, hin, model, upc):
        case (None, None, None, None):
            raise InvalidParameter("provide at least one of: q, hin, model, upc")
        case (str() as text, _, _, _):
            stmt = q.fts_stmt(text, page.cursor, page.limit)
            sort_keys = ("rank", "recall_product_id")
        case (None, _, _, str() as code):       # upc before id-only? choose precedence in 03
            stmt = q.upc_stmt(code, page.cursor, page.limit)
            sort_keys = ("published_at", "recall_product_id")
        case (None, h, m, None):
            stmt = q.identifier_stmt(hin=h, model=m, cursor=page.cursor, limit=page.limit)
            sort_keys = ("published_at", "recall_product_id")
        case _:
            raise InvalidParameter("unsupported combination of search parameters")

    rows = list((await conn.execute(stmt)).mappings().all())
    items, has_next = slice_page(rows, page.limit)
    next_cursor = _encode_cursor(items[-1], sort_keys) if has_next and items else None
    return build_page(items, limit=page.limit, next_cursor=next_cursor, total=None)


def _encode_cursor(row, keys: tuple[str, str]) -> str:
    a, b = keys
    val_a = row[a].isoformat() if a == "published_at" else row[a]
    return Cursor((val_a, row[b])).encode()
```

`# TODO(build)`: lock the **precedence** when several selectors are present (the contract in 03 should
say e.g. "`q` wins; else identifier; else `upc`") and reflect it in the `match` arms + OpenAPI. The
arms above sketch one ordering — make 03 and code agree.

### `routers/firms.py`

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.errors import ResourceNotFound
from recalls_api.models.firms import FirmProfile
from recalls_api.queries import firms as q

router = APIRouter(prefix="/firms", tags=["firms"])


@router.get("/{firm_id}", response_model=FirmProfile,
            responses={404: {"description": "Firm not found"}})
async def get_firm(
    firm_id: Annotated[str, Path(description="Opaque canonical firm id (md5 cluster key)")],
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
) -> FirmProfile:
    row = (await conn.execute(q.firm_stmt(firm_id))).mappings().one_or_none()
    if row is None:
        raise ResourceNotFound(f"no firm for id {firm_id}")
    return FirmProfile.model_validate(dict(row))
```

### `routers/health.py`

```python
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.db import healthcheck

router = APIRouter(tags=["ops"])
log = structlog.get_logger(__name__)


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: process is up. No DB touch — always 200 unless the process is dead."""
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    response: Response,
) -> dict[str, str]:
    """Readiness: a SELECT 1 to Neon. Cold/asleep Neon -> 503 + Retry-After, never hang."""
    try:
        ok = await healthcheck(conn)
    except (OperationalError, DBAPIError, TimeoutError) as exc:
        log.warning("health.db_unavailable", error=str(exc))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.headers["Retry-After"] = "5"
        return {"status": "degraded", "db": "unavailable"}
    return {"status": "ok", "db": "ok" if ok else "unexpected"}
```

**Async pitfalls for routers:** (1) **un-awaited** `conn.execute` — always `await`; (2) building a list
from a streaming result lazily — call `.mappings().all()` (materializes) before the `async with`
connection closes; (3) never call a sync/blocking lib in a route — Pydantic `model_validate` is CPU-only
and fine, but anything I/O must be `await`ed.

---

## `errors.py` — exception hierarchy + handlers + opaque catch-all

**Key decisions**

- One small base `ApiError` with `status_code` + `error_type` + a public `detail`. Subclasses set the
  status. The envelope is always `{"error": {"type", "detail", "request_id"}}`.
- The **catch-all** handler (registered for `Exception`) logs the full traceback (structlog
  `exc_info=True`) and returns a generic `internal_error` body with **only** the `request_id` — never
  the exception string, SQL, or DSN. This is the leak guard.
- `UpstreamUnavailable` (503) is raised by translating SQLAlchemy `OperationalError`/`DBAPIError`/
  asyncpg timeout in a dedicated handler; it sets `Retry-After`.
- `RateLimited` (429) bridges slowapi's `RateLimitExceeded` into the same envelope.
- `request_id` is pulled from the contextvar bound by the middleware in `logging.py`.

```python
from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError

from recalls_api.logging import get_request_id

log = structlog.get_logger(__name__)


class ApiError(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type: str = "internal_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ResourceNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "not_found"


class InvalidParameter(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_type = "invalid_parameter"


class BadCursor(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "bad_cursor"


class UpstreamUnavailable(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_type = "upstream_unavailable"


class RateLimited(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_type = "rate_limited"


def _envelope(error_type: str, detail: str, status_code: int,
              headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"type": error_type, "detail": detail, "request_id": get_request_id()}},
        headers=headers,
    )


async def _api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    headers = {"Retry-After": "5"} if isinstance(exc, UpstreamUnavailable) else None
    return _envelope(exc.error_type, exc.detail, exc.status_code, headers)


async def _db_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Cold/asleep/timed-out Neon -> 503; do NOT leak the SQLAlchemy/asyncpg message.
    log.warning("db.upstream_unavailable", error=str(exc))
    return _envelope("upstream_unavailable", "database temporarily unavailable",
                     status.HTTP_503_SERVICE_UNAVAILABLE, {"Retry-After": "5"})


async def _catch_all_handler(_: Request, exc: Exception) -> JSONResponse:
    # Full traceback to logs; OPAQUE body to client. Never leak SQL/DSN/exception text.
    log.error("unhandled_exception", exc_info=exc)
    return _envelope("internal_error", "an unexpected error occurred",
                     status.HTTP_500_INTERNAL_SERVER_ERROR)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(OperationalError, _db_error_handler)
    app.add_exception_handler(DBAPIError, _db_error_handler)
    app.add_exception_handler(Exception, _catch_all_handler)  # last resort
```

`# TODO(build)`: (1) decide whether FastAPI's own `RequestValidationError` (422 from `Query`/`Path`
constraints) should be reshaped into this envelope for consistency — add a handler if so; (2) wire
slowapi's `RateLimitExceeded` to a `RateLimited`/429 envelope handler (see `main.py`); (3) `BadCursor`
is raised deep in `Cursor.decode`/`pagination_params` (a `Depends`) — confirm a dependency-raised
`ApiError` reaches `_api_error_handler` (it does in FastAPI), and unit-test it.

---

## `logging.py` — structlog JSON + request-id contextvars middleware

**Key decisions**

- **Reuse the pipeline's `configure_logging` shape verbatim** (`src/config/logging.py`): shared
  processor chain, `merge_contextvars`, JSON to stdout in prod (console when `stderr.isatty()`),
  stdlib bridge so SQLAlchemy/uvicorn logs share one renderer. Silence `sqlalchemy.engine`,
  `sqlalchemy.pool`, `uvicorn.access` to WARNING.
- A `contextvars.ContextVar[str]` holds the `request_id`; the middleware binds it (and
  `structlog.contextvars.bind_contextvars`) per request so every log line and the error envelope carry
  it. `get_request_id()` is what `errors.py` reads.
- One INFO log line per request: method, path, status, latency_ms, and (where available) row_count.

```python
from __future__ import annotations

import time
import uuid
from contextvars import ContextVar

import structlog
import structlog.contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# configure_logging: copy from pipeline src/config/logging.py (JSON/stdout, stdlib bridge,
# merge_contextvars). Omitted here for brevity — mirror it 1:1, dropping the GHA-URL binding
# and silencing uvicorn.access in addition to sqlalchemy.*.
from recalls_api._logging_config import configure_logging  # TODO(build): inline or split file

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
log = structlog.get_logger(__name__)


def get_request_id() -> str:
    return _request_id.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a per-request uuid into contextvars; echo it on the response + every log line."""

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = _request_id.set(rid)
        structlog.contextvars.bind_contextvars(request_id=rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                # status is unknown if call_next raised — handler logs the 500 separately
                latency_ms=elapsed_ms,
            )
            structlog.contextvars.clear_contextvars()
            _request_id.reset(token)
        response.headers["X-Request-ID"] = rid
        return response
```

**Async pitfalls:** (1) the middleware must `await call_next(request)` — a missed await breaks the chain
silently; (2) reset the contextvar in `finally` so a long-lived worker doesn't leak the previous
request's id into the next; (3) do not log inside the hot path with blocking sinks — structlog JSON to
stdout is non-blocking enough for this scale.

`# TODO(build)`: decide whether to keep `configure_logging` inline in `logging.py` or in a tiny
`_logging_config.py` (the import above is a placeholder). Capturing the **response status** in the
per-request line requires reading `response.status_code` — move the `log.info` after the `await` and
include `status=response.status_code` on the success path; keep a separate branch for the exception
path.

---

## `main.py` — app factory, lifespan, registration order, slowapi

**Key decisions**

- **App factory** `create_app()` so tests build a fresh app and override `deps.get_conn`.
- **Lifespan** opens the pool (which forces `get_settings()` -> fail-loud) and disposes on shutdown.
- **Registration order matters:**
  1. `configure_logging()` first (before anything logs).
  2. add `RequestIdMiddleware` (outermost, so the id is bound before handlers run and the error
     envelope can read it).
  3. add slowapi limiter + its middleware/state.
  4. `register_error_handlers(app)`.
  5. include routers.
- **slowapi** is initialized with the configured limit; its `RateLimitExceeded` is wired to the 429
  envelope. (slowapi is an API-repo choice, not ADR — 02.)
- OpenAPI metadata (title, version, the honest data caveats from 01) is set here; the committed
  `openapi.json` snapshot is the contract test fixture (05).

```python
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from recalls_api import db
from recalls_api.errors import RateLimited, register_error_handlers
from recalls_api.logging import RequestIdMiddleware, configure_logging
from recalls_api.routers import firms, health, products, recalls
from recalls_api.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()           # fail-loud: missing DSN -> ValidationError at boot
    await db.open_pool(app, settings)   # verifies connectivity + read-only posture
    try:
        yield
    finally:
        await db.close_pool(app)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Consumer Product Recalls API",
        version="0.1.0",
        description=(
            "Read-only, public API over the recalls gold marts. "
            "Caveats: `is_active` is tri-state (CPSC/NHTSA carry no status -> null); "
            "`classification` is source-native (not comparable across sources); "
            "UPC search matches recall-level UPC arrays, not per-product UPC; "
            "no fuzzy/typo search. See /docs for per-field notes."
        ),
        lifespan=lifespan,
    )

    # --- middleware (outermost first) ---
    app.add_middleware(RequestIdMiddleware)

    # --- rate limit (slowapi; tune to free-tier DB) ---
    limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])
    app.state.limiter = limiter
    if settings.rate_limit_enabled:
        app.add_middleware(SlowAPIMiddleware)

    # --- error handlers ---
    register_error_handlers(app)
    app.add_exception_handler(  # bridge slowapi -> our envelope
        RateLimitExceeded,
        lambda req, exc: _raise_rate_limited(),  # TODO(build): proper handler returning 429 envelope
    )

    # --- routers ---
    app.include_router(health.router)
    app.include_router(recalls.router)
    app.include_router(products.router)
    app.include_router(firms.router)
    return app


def _raise_rate_limited() -> None:
    raise RateLimited("rate limit exceeded")


app = create_app()  # module-level for `uvicorn recalls_api.main:app`
```

**Async pitfalls:** (1) **never** open the pool at module import — only inside `lifespan` (import-time
DB connect blocks/leaks and breaks tests); (2) `create_app()` runs `get_settings()` twice (factory +
lifespan) — `@lru_cache` makes that a no-op, but don't construct `Settings()` directly anywhere; (3)
middleware order: adding `RequestIdMiddleware` last would make it *innermost* — add it first so it wraps
everything. Starlette applies middleware in reverse-add order, so verify the bound id is visible to the
error handlers (it is, because handlers run inside the middleware stack).

`# TODO(build)`: (1) replace the lambda slowapi bridge with a real `async def` handler returning the
429 envelope via `errors._envelope`; slowapi also needs the limiter on routes you actually decorate, OR
rely solely on `default_limits` + `SlowAPIMiddleware` (decide and document — middleware-only global
limits are simpler for v1). (2) Add `Cache-Control`/`ETag`/`Last-Modified` either as a small response
middleware keyed off the nightly ~03:00 UTC rebuild timestamp or per-route (06 owns the exact policy).

---

## Cross-module async pitfall checklist (the build session re-reads this before shipping)

| # | Pitfall | Where it lurks | Mitigation in this blueprint |
|---|---|---|---|
| 1 | **Blocking the event loop** | a sync DB driver, `time.sleep`, sync file I/O, a CPU-heavy validator | asyncpg only; `await asyncio.sleep`; no file I/O on the request path; Pydantic validation is fine (CPU-trivial) |
| 2 | **Un-awaited coroutine** | `conn.execute(...)`, `engine.connect()`, `call_next(...)` | `await` every coroutine; `async with` every async context manager; pyright in CI catches missed awaits |
| 3 | **Pool exhaustion on cold Neon** | a hung connect holds a slot; all 5+5 block | `connect timeout` + `command_timeout` raise fast; `_db_error_handler` -> 503 releases the slot; `pool_pre_ping` + sub-reap `pool_recycle` avoid dead sockets |
| 4 | **Pool opened at import** | top-level `make_engine()` call | engine lives in `lifespan`, stored on `app.state.engine`; nothing connects at import |
| 5 | **Lazy result after conn close** | returning a streaming result then closing `async with` | materialize with `.mappings().all()` inside the connection scope |
| 6 | **Contextvar leak across requests** | request_id bound but not reset | `finally: _request_id.reset(token)` + `clear_contextvars()` |
| 7 | **Secrets at import** | `Settings()` at module level | `@lru_cache get_settings()`; constructed first in `lifespan` |
| 8 | **SQL/DSN leak in errors** | passing the exception string to the client | catch-all returns opaque body; DB handler returns a fixed string; full detail only to logs |

---

## Open items / judgment calls (carried to 08 / operator)

1. **Read-only role + DSN env var (BLOCKER for `db.py`)** — exact role name (`recalls_readonly`
   assumed), `GRANT SELECT` target set, pooled (PgBouncer) vs direct endpoint, whether
   `default_transaction_read_only=on` is set server-side, and the env-var name. Provisioned by the
   pipeline repo/operator (mirror migration 0033's NOLOGIN-shell + grant pattern, but read-only). See
   02 MUST-re-verify #1. **Do not ship `db.py` against the read+write `recalls_app` DSN.**
2. **Cursor `published_at` round-trip** — bind as ISO `str` + `::timestamptz` cast vs bind a real
   `datetime`. Pick one in `pagination.py`; unit-test the equality seam (judgment call: ISO string is
   simpler and JSON-safe).
3. **Product search precedence** when multiple selectors are present — the `match` arms sketch
   `q > identifier > upc`; lock it in 03 and align code.
4. **slowapi handler + scope** — middleware-only global limits vs per-route decorators; replace the
   placeholder lambda with a real 429-envelope handler. slowapi is not ADR-ratified (02) — mark as an
   API-repo choice.
5. **`RequestValidationError` reshaping** — whether to map FastAPI's native 422 into our envelope for a
   uniform error shape (recommended for contract consistency).
6. **`hazards` / `model_year` typing** — modeled as opaque `JSON` / `str` here (01 FLAGGED); confirm
   against a seeded row if a stricter shape is wanted (03 owns the response-model decision).
7. **`statement_timeout` under PgBouncer transaction pooling** — `server_settings` may not persist; set
   per-statement or use the direct endpoint (depends on item #1).

> **Sibling docs:** field-level response shapes & OpenAPI copy → **03**; the seeded `seed_gold.sql`
> cassette, fixtures, coverage gate, and contract test → **05**; Dockerfile/fly.toml/render.yaml,
> cold-start 503, cache headers → **06**; the read-only role ask to the pipeline → **07**; the ordered
> commit plan that builds these modules → **08**.
