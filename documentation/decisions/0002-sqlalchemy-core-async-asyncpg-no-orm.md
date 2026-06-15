# 0002 - SQLAlchemy Core async over asyncpg; no ORM, no reflection

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

> Upstream framing: this decision implements the stack ratified in [pipeline ADR 0024](../../../consumer-product-recalls/documentation/decisions/0024-serving-layer-api-design.md).

---

## Context

The API is a long-lived async server that reads three read-only gold marts it does not own and never writes to. FastAPI's native async model requires an async DB driver. Four forces shaped the choice:

1. **Persistent pool vs. NullPool.** The pipeline uses sync `psycopg2` + `NullPool` for batch jobs — connections are cheap and bursty. The API is request-driven and benefits from a warm pool so each request does not pay a cold-connect penalty. These are different workloads; the pipeline pattern must not be copied blindly. (`db.py:1-5`)

2. **ORM overhead is pure cost here.** SQLAlchemy ORM adds an identity map, lazy-load machinery, and mapper introspection. The API executes narrow projections (18-column list, one full-wide point read) over stable, pre-joined gold views. There is no graph traversal, no change tracking, and no N+1 query to guard against. ORM features would be dead weight.

3. **Reflection is incompatible with a fast, cold-safe boot.** Reflecting the gold mart schema at startup requires a live DB round-trip before the server can serve the liveness probe (`GET /health`). A cold or sleeping Neon would delay startup or crash it. Column definitions are governed by a published read contract (ADR 0042) and change infrequently.

4. **asyncpg mirrored an existing dependency.** `asyncpg` was already present in the pipeline environment. `psycopg3` is a viable alternative but introduces a new dependency for no net gain.

---

## Decision

1. Use `create_async_engine` with the `postgresql+asyncpg` driver (`db.py:47`). The engine is constructed once in the FastAPI `lifespan`, stored on `app.state.engine`, and disposed on shutdown.

2. Pool settings: `pool_size=5`, `max_overflow=5`, `pool_pre_ping=True`, `pool_recycle=300 s` (below Neon's idle-reap threshold). Connect timeout `5.0 s` and command timeout `10.0 s` are passed as `connect_args` so a cold Neon surfaces as a fast 503, never a hung request (`db.py:53-65`).

3. Express every gold table as a lightweight `sa.table(...)` / `sa.column(...)` literal — no `MetaData.reflect`, no ORM declarative base. Column names track the mart schema declared in ADR 0042 (`queries/recalls.py:20-50`, `queries/products.py:21-44`).

4. Every query module (`queries/recalls.py`, `queries/products.py`, `queries/firms.py`) is **pure**: it returns a `sa.Select` object and performs no I/O. Routers call `conn.execute(stmt)` and `.mappings()` to materialize rows.

5. One `AsyncConnection` per request via `async with engine.connect() as conn` in the `get_conn` FastAPI dependency (`db.py:107-111`). Never an ORM `AsyncSession`.

6. At boot, assert read-only by executing `SHOW transaction_read_only` on the first connection. A reachable-but-writable connection in production is a hard boot refusal (`RuntimeError`). An unreachable DB at boot is tolerated — pool pre-ping validates connections lazily and per-request paths map failures to 503 (`db.py:80-91`).

---

## Consequences

**Accepted benefits:**

- Query modules are unit-testable without a database: compile the `Select` to SQL and inspect bound parameters.
- No ORM import overhead, no session lifecycle, no lazy-load footguns.
- Boot is DB-free (no reflection): the liveness probe is always reachable even when Neon is cold.
- `pool_pre_ping` + short timeouts convert cold-Neon scenarios to 503 + `Retry-After` instead of hung requests or crash loops.

**Accepted costs:**

- `sa.table()` column literals must be kept in sync with mart schema changes manually. No automatic drift detection exists at the DB layer; ADR 0042 governs the published read contract and is the change coordination mechanism.
- A new gold column not declared in the `sa.table()` literal is invisible to the API until the literal is updated and redeployed.
- The pipeline's sync `NullPool` pattern is intentionally not reused here — a reviewer unfamiliar with both repos may find the divergence surprising.
