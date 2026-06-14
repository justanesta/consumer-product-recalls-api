# 06 — Deployment & Ops (recalls-api)

> **Hardened build spec.** This is the deploy/runtime contract for the OPEN, READ-ONLY FastAPI repo
> `recalls-api` that serves the PostgreSQL gold marts built by the separate pipeline repo
> (`justanesta/consumer-product-recalls` @ `feature/pre-go-live-validation`, commit `39dcbda`).
> Schema facts come from **doc 01** (ground truth) and **doc 02** (reconciliation); deployment
> decisions are locked by **ADR 0024** (serving-layer design), **ADR 0025** (deploy target),
> **ADR 0005** (Neon storage), **ADR 0029** (observability), and pipeline migration **0033** (role posture).
>
> Sibling docs: **03** API contract · **04** implementation · **05** testing/CI · **07** gold-layer
> recommendations · **08** commit plan. Cross-refs use those numbers.

## 0. Scope and the load-bearing facts

This document specifies items the build session ships **as files in this repo**:

| File | Section | Purpose |
|---|---|---|
| `Dockerfile` | §1 | Multi-stage slim CPython 3.12 + uv, non-root, uvicorn entrypoint, HEALTHCHECK |
| `.dockerignore` | §1 | Keep build context tiny; never leak `.env`/secrets |
| `fly.toml` | §2 | Primary deploy target (ADR 0025) |
| `render.yaml` | §2 | Documented fallback stub (ADR 0025) |
| **NO** `wrangler.toml` | §2 | Cloudflare Workers **rejected** — Pyodide/WASM cannot load asyncpg (ADR 0025) |
| `src/recalls_api/settings.py` | §3 | `Settings(BaseSettings)`, `SecretStr` DSN, fail-loud at import |
| `src/recalls_api/db.py` | §3, §4 | Async engine factory, pool, cold-start 503 mapping |
| `src/recalls_api/middleware.py` | §6, §8 | request_id contextvar middleware; slowapi rate limit |
| `src/recalls_api/health.py` | §7 | `/health` (liveness) + `/health/db` (readiness) |
| `src/recalls_api/logging.py` | §8 | structlog JSON to stdout (mirrors pipeline `src/config/logging.py`) |
| `.github/workflows/deploy.yml` | §9 | `flyctl deploy` on push to `main` |

**Three facts drive everything in this doc:**

1. **The API gets ZERO write privilege.** The pipeline's `recalls_app` role (migration 0033) is the
   pipeline's **READ+WRITE** role (`GRANT SELECT, INSERT, UPDATE`). **The API MUST NOT reuse it.** A
   **new** dedicated read-only role must be provisioned by the pipeline repo/operator. See §3 — this is
   the single most load-bearing operational item, and the exact name/grants/endpoint is an **operator
   confirmation item**.
2. **Two cold starts stack** (Fly scale-to-zero × Neon auto-suspend). A cold request can take seconds
   or fail. We **fail fast to 503 + Retry-After** rather than hang. See §4.
3. **Gold rebuilds nightly ~03:00 UTC** (full silver+gold rebuild — `transform.yml`, architecture.md).
   That is the only freshness boundary the data has, and the anchor for HTTP cache headers (§5). Gold
   exposes **no rebuild-timestamp surface today** — see §5 + doc 07 recommendation.

---

## 1. Dockerfile (+ `.dockerignore`)

**Image strategy** (mirrors the docker skill `image-optimization.md` / `security-patterns.md`):

- **`python:3.12-slim`**, not Alpine: asyncpg ships a C extension; glibc (`-slim`) avoids the musl
  build friction Alpine forces. Not distroless: we want `/health` HEALTHCHECK + a shell for debugging
  a low-traffic personal API.
- **Multi-stage**: stage 1 (`builder`) holds `uv` and compiles the venv; stage 2 (runtime) copies only
  the resolved `.venv` and the app — no compiler, no `uv` in the final image.
- **`uv sync --frozen --no-dev`**: install from the committed `uv.lock` (the build/CI lockfile per the
  locked stack decision), production deps only. Fail the build if the lock is stale (`--frozen`).
- **Non-root**: dedicated `appuser` (uid 10001), `/sbin/nologin`, owns nothing it can write. App binds
  `:8080` (>1024, so no `NET_BIND_SERVICE` cap needed).
- **HEALTHCHECK** hits `/health` (liveness only — must NOT touch Neon; see §7) so Docker/Fly never wake
  the DB just to prove the process is up.
- **uv from the official distroless `uv` image** via `COPY --from=ghcr.io/astral-sh/uv` — pinned tag,
  no `curl | sh`.

```dockerfile
# syntax=docker/dockerfile:1
# ---- Stage 1: build the resolved virtualenv with uv -------------------------
FROM python:3.12-slim AS builder

# Pin uv by copying its static binary from the official image (no curl|sh).
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build

# Dependency layer first (changes less often than source) — see image-optimization.md.
# --no-install-project: resolve/install deps only; the app itself is added with source below.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Now the source, then install the project into the same venv.
COPY src/ ./src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- Stage 2: minimal runtime (no compiler, no uv) --------------------------
FROM python:3.12-slim AS runtime

# OCI provenance labels (build args injected by CI / flyctl).
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="recalls-api" \
      org.opencontainers.image.source="https://github.com/justanesta/consumer-product-recalls-api" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"

# Non-root system user: no login shell, no home it can write.
RUN groupadd -r appuser && \
    useradd -r -g appuser -u 10001 -d /app -s /sbin/nologin appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    LOG_FORMAT=json \
    PORT=8080 \
    GIT_SHA="${GIT_SHA}"

WORKDIR /app

# Resolved venv from the builder, then the app source. Both owned by appuser.
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /build/src ./src

USER appuser
EXPOSE 8080

# Liveness probe: /health is process-only (NEVER touches Neon — see §7), so a cold
# DB never makes the container look dead. start-period covers process boot, not DB wake.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).status==200 else 1)"]

# Exec form so uvicorn is PID 1 and receives SIGTERM for graceful shutdown.
# Single worker: a small async pool per process (§4); Fly scales by adding machines, not workers.
ENTRYPOINT ["uvicorn", "recalls_api.main:app", \
            "--host", "0.0.0.0", "--port", "8080", \
            "--workers", "1", "--timeout-graceful-shutdown", "20", \
            "--no-server-header", "--proxy-headers", "--forwarded-allow-ips", "*"]
```

**Why single worker, not gunicorn+N:** the app is async I/O-bound (DB round-trips), and each worker
holds its own pool. On Fly free-tier shared-cpu-1x with scale-to-zero, one async worker + a small pool
(§4) is correct; horizontal scale is "add a machine," not "add a worker." (The docker skill's
gunicorn `--workers 4` example targets sync WSGI — not our model.)

**`.dockerignore`** (whitelist-light; the critical lines are `.env*`, `.git`, tests, caches):

```
# Version control
.git
.gitignore

# Local virtualenv / build artifacts (the image builds its own venv)
.venv
venv
dist
build
*.egg-info

# Byte-compiled
__pycache__
*.pyc
*.pyo

# Test / lint / type caches (not needed at runtime; CI runs them separately)
tests/
.pytest_cache
.coverage
htmlcov
.ruff_cache
.pyright

# Docker / CI / deploy descriptors (not needed inside the image)
Dockerfile*
.dockerignore
fly.toml
render.yaml
.github/

# Project scope docs / markdown (do not bloat the build context)
project_scope/
documentation/
*.md
LICENSE

# Secrets & local env — MUST never enter an image layer
.env
.env.*
*.pem
*.key

# IDE / OS
.vscode
.idea
*.swp
.DS_Store
```

> **Note:** `src/` and `pyproject.toml`/`uv.lock` are NOT ignored — they are the build inputs. The
> committed `openapi.json` snapshot (doc 05) is a test fixture; it lives under `tests/` and is ignored
> from the image by the `tests/` line. If it lives at repo root, exclude it explicitly — the running
> API generates its own OpenAPI; it never reads the snapshot.

---

## 2. `fly.toml`, `render.yaml`, and the rejected Workers config

### 2a. `fly.toml` (primary — ADR 0025)

Decisions baked in:

| Setting | Value | Rationale |
|---|---|---|
| `primary_region` | `iad` (US-East / Ashburn) | Co-locate with Neon. Neon free-tier projects are commonly `us-east-*`; **confirm the actual Neon region with the operator (§3)** and set the nearest Fly region to minimize DB RTT. |
| `internal_port` | `8080` | Matches the Dockerfile non-root bind. |
| `force_https` | `true` | Open API, but never serve plaintext. |
| `auto_stop_machines` / `auto_start_machines` | `stop` / `true` | Scale-to-zero on idle, auto-wake on request — free-tier posture (ADR 0025 "scale-to-zero with wake"). This is **cold start #1** (§4). |
| `min_machines_running` | `0` (default) | Free-tier default. **Tradeoff:** `0` = no idle cost but every cold request eats Fly boot + Neon wake; `1` = always-warm Fly (removes cold start #1) at the cost of a continuously-running machine. Ship `0`; the keep-warm cron in §4 is the cheaper middle path. Flip to `1` only if the website commits to a freshness/latency SLO (ADR 0029 upgrade trigger). |
| `[[http_service.checks]]` | HTTP GET `/health`, not `/health/db` | Fly's health check must be **liveness** — it must not wake Neon or it defeats scale-to-zero and flaps on cold DB. Readiness (`/health/db`) is a caller/operator probe (§7). |
| concurrency | `type = "requests"`, `soft_limit = 50`, `hard_limit = 100` | Low-traffic personal API; per-machine async concurrency. Fly load-balances and starts a second machine when soft_limit is exceeded. Tune down if the read-only pool (§4, ~5+5) becomes the bottleneck before concurrency does. |

```toml
# fly.toml — recalls-api (Fly.io primary target, ADR 0025)
app = "recalls-api"
primary_region = "iad"   # co-locate with Neon; CONFIRM Neon region with operator (§3)

[build]
  dockerfile = "Dockerfile"

[env]
  APP_ENV = "production"
  LOG_FORMAT = "json"
  PORT = "8080"
  # NEON_DATABASE_URL_RO is a SECRET — set via `flyctl secrets set`, NOT here (§3, §9).

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0          # free-tier; see tradeoff table + keep-warm (§4)

  [http_service.concurrency]
    type = "requests"
    soft_limit = 50
    hard_limit = 100

  # Liveness only — MUST NOT hit Neon (would defeat scale-to-zero / flap on cold DB).
  [[http_service.checks]]
    method = "GET"
    path = "/health"
    interval = "30s"
    timeout = "4s"
    grace_period = "10s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"   # asyncpg + small pool + structlog fit comfortably; bump to 1gb if OOM observed
```

Deploy is `flyctl deploy` from CI (§9). Secrets are set **out-of-band** with `flyctl secrets set` (§3),
never committed to `fly.toml`.

### 2b. `render.yaml` (documented fallback stub — ADR 0025)

Render is "near-identical shape — a deploy hook instead of `flyctl`" (ADR 0025). Ship a committed stub
so the fallback is one `git push` + a dashboard connect away. Render's free web service also
scale-to-zero-sleeps after ~15 min idle — **same two-cold-start stack** (§4) applies.

```yaml
# render.yaml — DOCUMENTED FALLBACK ONLY (primary is Fly.io, ADR 0025).
# Not wired into CI; activate by connecting the repo in the Render dashboard.
services:
  - type: web
    name: recalls-api
    runtime: docker
    dockerfilePath: ./Dockerfile
    plan: free                 # free plan sleeps after ~15 min idle (cold start #1)
    region: virginia           # nearest to Neon us-east; match Neon region (§3)
    healthCheckPath: /health   # liveness only — must NOT touch Neon (§7)
    autoDeploy: false          # keep CD on Fly; flip to true only if Render becomes primary
    envVars:
      - key: APP_ENV
        value: production
      - key: LOG_FORMAT
        value: json
      - key: PORT
        value: "8080"
      - key: NEON_DATABASE_URL_RO
        sync: false            # set in the Render dashboard; never commit the secret
```

### 2c. NO `wrangler.toml`

**Cloudflare Workers is rejected (ADR 0025) and there is no `wrangler.toml` in this repo.** Reason:
the Workers Python runtime is Pyodide/WASM and **cannot load asyncpg's compiled C driver** nor hold a
durable connection pool. Adopting it would force an HTTP DB proxy rewrite, contradicting the locked
async-asyncpg stack (ADR 0024). Do not add Workers config "just in case" — it is a runtime dead end
for this stack.

---

## 3. DB connection & the read-only role (LOAD-BEARING — operator confirmation item)

This is the section the build session most needs to get right, and the one with a hard external
dependency on the operator/pipeline repo.

### 3a. Why the API must NOT reuse `recalls_app`

Pipeline migration `0033_recalls_app_role_posture.py` defines `recalls_app` as the pipeline's runtime
role with:

```sql
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO recalls_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO recalls_app;
GRANT TRUNCATE ON firm_crosswalk, quantity_crosswalk TO recalls_app;
```

That is **read + append + in-place update + TRUNCATE on two tables**. An open, unauthenticated API
holding that role is a write-amplified attack surface for zero benefit (the API issues only `SELECT`).
**The API uses a NEW, separate, read-only role.** ADR 0025 confirms: "Read-only Neon access uses a
dedicated restricted role … the API never holds write privileges."

### 3b. The new read-only role — recommended provisioning SQL (pipeline repo / operator)

The role is provisioned **by the pipeline repo or operator**, not by this API repo (the API owns no
migrations). It should mirror the 0033 pattern exactly — this is the recommended migration to add to
the pipeline repo (e.g. `0034_recalls_readonly_role.py`). The build session should request this from
the operator and treat the role as a precondition.

```sql
-- Provisioned by the PIPELINE repo / operator, NOT by recalls-api.
-- Mirrors migration 0033's posture: NOLOGIN SQL-created shell + explicit SELECT grants.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'recalls_readonly') THEN
        -- Refuse to proceed against a dirty/elevated pre-existing role (same guard as 0033):
        IF EXISTS (
            SELECT 1 FROM pg_roles
            WHERE rolname = 'recalls_readonly'
              AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
        ) OR EXISTS (
            SELECT 1 FROM pg_auth_members am
            JOIN pg_roles g ON g.oid = am.roleid
            JOIN pg_roles m ON m.oid = am.member
            WHERE m.rolname = 'recalls_readonly' AND g.rolname = 'neon_superuser'
        ) THEN
            RAISE EXCEPTION USING MESSAGE =
                'recalls_readonly exists with elevated privileges or neon_superuser membership; '
                || 'delete it in the Neon console and re-run to recreate clean via SQL.';
        END IF;
    ELSE
        -- SQL-created => NOT auto-added to neon_superuser (the write-all trap, see 3c) and gets
        -- restricted default attributes (NOSUPERUSER/NOCREATEDB/.../NOBYPASSRLS).
        CREATE ROLE recalls_readonly NOLOGIN;
    END IF;
END $$;

-- Read-only grants: SELECT on the gold marts ONLY (not bronze/silver/state tables).
GRANT USAGE ON SCHEMA public TO recalls_readonly;
GRANT SELECT ON
    mart_recall_summary,
    mart_product_search,
    mart_firm_profile
TO recalls_readonly;

-- Belt-and-suspenders: force read-only transactions at the role level, so even a future
-- accidental grant cannot let this role write. The API also sets read-only per-connection (3d).
ALTER ROLE recalls_readonly SET default_transaction_read_only = on;

-- NO INSERT/UPDATE/DELETE/TRUNCATE. NO sequence USAGE. NO default-privileges grant
-- (a new mart table is granted explicitly, mirroring how 0033 scopes its grants).
```

> **`/stats/*` is deferred from v1 (ADR 0024).** The above grants only the three v1 serving marts. When
> `/stats/*` ships, add `GRANT SELECT` on the specific `fct_*` / `dim_date` marts then — do not
> pre-grant the whole schema.

**The operator then activates the role out-of-band** (Neon rejects passwordless LOGIN and rejects
psql's client-hashed `\password`, exactly as documented in 0033 — set plaintext + LOGIN in one
statement):

```sql
ALTER ROLE recalls_readonly LOGIN PASSWORD '<strong generated password>';
```

### 3c. The `neon_superuser` trap (do not create the role via Neon Console/API/CLI)

Migration 0033 documents this and it applies identically here: **Neon auto-adds Console/API/CLI-created
roles to `neon_superuser`**, whose `pg_write_all_data` membership silently grants write on every table —
which would defeat the entire read-only posture. **The role MUST be created via SQL** (as above) so it
is NOT a `neon_superuser` member. If the operator created it in the console by mistake, the fix is
delete-and-recreate-via-SQL — a non-superuser owner cannot strip the membership.

### 3d. The API's connection settings (`settings.py` + `db.py`)

Mirror the pipeline's `src/config/settings.py` idiom: `pydantic-settings BaseSettings`, `SecretStr`
DSN, **fail-loud at construction** (a missing DSN raises `ValidationError` at boot). The pipeline's
canonical var is `NEON_DATABASE_URL`; the API uses a **read-only variant `NEON_DATABASE_URL_RO`** so
the two repos never confuse credentials.

```python
# src/recalls_api/settings.py
from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Read-only Neon DSN for the recalls_readonly role. SecretStr => never logged/repr'd.
    # Mirrors the pipeline's NEON_DATABASE_URL (ADR 0005/0016); the _RO suffix marks the
    # read-only role so the two repos never cross credentials. CONFIRM exact var name + role
    # + pooled-vs-direct endpoint with the operator before wiring db.py.
    neon_database_url_ro: SecretStr

    app_env: str = "production"
    log_format: str = "json"
    # Cold-Neon budget: how long a checkout/connect may take before we 503 (§4).
    db_connect_timeout_s: float = 5.0
    db_command_timeout_s: float = 10.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Constructed at first call (FastAPI lifespan / dependency), NOT at import, so the
    # missing-DSN ValidationError fires at boot with a clear message rather than on import
    # of a test module. Mirrors the pipeline's "no module-level Settings()" note.
    return Settings()  # raises ValidationError if NEON_DATABASE_URL_RO is unset -> fail loud
```

```python
# src/recalls_api/db.py  (engine factory — async, persistent small pool)
from __future__ import annotations

from collections.abc import AsyncIterator

from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from recalls_api.settings import get_settings


def _normalize_dsn(dsn: str) -> str:
    # asyncpg driver dialect. Neon DSNs are usually `postgresql://...?sslmode=require`.
    # asyncpg does NOT accept libpq `sslmode` as a query arg — strip it and pass ssl via
    # connect_args instead (see below). Also force the +asyncpg dialect.
    base = dsn.replace("postgresql+asyncpg://", "postgresql://")
    base = base.replace("postgresql://", "postgresql+asyncpg://", 1)
    # Drop libpq-only query params asyncpg rejects (sslmode/channel_binding handled via connect_args).
    for p in ("?sslmode=require", "&sslmode=require", "?channel_binding=require", "&channel_binding=require"):
        base = base.replace(p, "")
    return base.rstrip("?&")


def make_engine() -> AsyncEngine:
    """Single async engine for the API process. Small persistent pool sized for cold Neon.

    NOTE the contrast with the pipeline's src/config/db.py: that uses NullPool (batch jobs,
    one connection at a time). The API is a long-lived server, so it holds a SMALL persistent
    pool. pool_pre_ping validates at checkout; pool_recycle stays under Neon's ~300s idle reaper.
    """
    s = get_settings()
    dsn = _normalize_dsn(s.neon_database_url_ro.get_secret_value())
    return create_async_engine(
        dsn,
        # Cold-start posture (§4):
        pool_size=5,            # steady-state concurrency for a low-traffic API
        max_overflow=5,         # burst headroom; total <= 10 (free-tier connection budget)
        pool_pre_ping=True,     # SELECT 1 at checkout -> drop stale Neon connections
        pool_recycle=300,       # recycle under Neon's ~300s idle termination (ADR 0005)
        pool_timeout=s.db_connect_timeout_s,  # don't queue forever waiting for a slot
        connect_args={
            "ssl": True,                       # Neon requires TLS (sslmode=require equivalent)
            "timeout": s.db_connect_timeout_s, # asyncpg connect timeout — fail a cold/asleep Neon fast
            "command_timeout": s.db_command_timeout_s,  # per-statement ceiling
            "server_settings": {
                # Per-connection read-only enforcement, independent of the role default (3b).
                "default_transaction_read_only": "on",
                "application_name": "recalls-api",
            },
        },
    )


async def get_conn(request: Request) -> AsyncIterator[AsyncConnection]:
    # FastAPI request dependency: one read-only Core connection per request (NOT an ORM
    # Session). The engine/pool lives on app.state.engine (set in lifespan); this is the single
    # overridable DB seam tests patch (decision 6). SQLAlchemy CORE per the locked stack.
    engine: AsyncEngine = request.app.state.engine
    async with engine.connect() as conn:
        yield conn
```

> **asyncpg connect_args differ from the pipeline's psycopg2 args.** The pipeline `db.py` uses
> psycopg2 keys (`connect_timeout`, `keepalives*`). asyncpg uses `timeout` / `command_timeout` /
> `ssl` / `server_settings`. Do not copy the pipeline keys verbatim — they are silently ignored or
> error under asyncpg.

### 3e. Pooled (PgBouncer) vs direct Neon endpoint

Neon gives two hostnames: a **direct** endpoint (`ep-xxx.<region>.aws.neon.tech`) and a **pooled**
endpoint (`ep-xxx-pooler.<region>.aws.neon.tech`, PgBouncer in transaction mode).

| | Direct endpoint | Pooled (`-pooler`) endpoint |
|---|---|---|
| Best for | A few long-lived app connections (our case) | Many short-lived connections (serverless functions) |
| SQLAlchemy app-side pool | **Yes — own the pool ourselves** | Redundant double-pooling; PgBouncer txn-mode also forbids some session features (prepared statements, `SET`) |
| asyncpg note | Works cleanly | asyncpg prepared-statement caching can conflict with PgBouncer txn mode — needs `statement_cache_size=0` |

**Recommendation: use the DIRECT endpoint** and own the pool in SQLAlchemy (§3d). The API holds a
small, long-lived pool — exactly what the direct endpoint is for; PgBouncer adds a layer we'd have to
defang (`statement_cache_size=0`). If the operator insists on the pooled endpoint, add
`connect_args["statement_cache_size"] = 0` and drop `server_settings` `SET`-style entries that txn-mode
rejects.

### 3f. ⚠️ OPERATOR CONFIRMATION ITEM (blocking before `db.py` is wired)

Per doc 02 "MUST re-verify," the read ADRs do **not** pin these. Confirm with the operator/pipeline
repo before finalizing:

| Item | Default assumed here | Confirm |
|---|---|---|
| Read-only role **name** | `recalls_readonly` | Exact name the operator provisions |
| Grant target set | `SELECT` on the 3 v1 marts | Whether broader schema SELECT is wanted |
| `default_transaction_read_only` | set at role + per-connection | That the role-level `SET` is applied |
| Env var **name** | `NEON_DATABASE_URL_RO` | The operator-blessed var name |
| Endpoint | **direct** (not `-pooler`) | Direct vs pooled hostname |
| Neon **region** | `us-east` → Fly `iad` / Render `virginia` | Actual Neon project region for region co-location |

---

## 4. Cold-start strategy (the two-cold-start stack)

A request to an idle deployment can traverse **two** cold starts:

```
client → [Fly machine asleep: scale-to-zero]  →  boot container (~1–3s)
       → [Neon compute auto-suspended: ADR 0005] → wake Neon (~0.5–5s, occasionally more)
       → first SELECT
```

Either or both may be cold. **The cardinal rule: never hang.** A read-only public API that blocks for
20s on a cold DB is worse than one that returns a fast, honest 503.

### 4a. Pool + timeout posture (from §3d, restated as the cold-start contract)

| Setting | Value | Role in cold start |
|---|---|---|
| `pool_size` / `max_overflow` | 5 / 5 | Small, warm pool; total ≤ 10 stays inside free-tier connection budget |
| `pool_pre_ping` | `True` | `SELECT 1` at checkout discards a Neon-reaped connection instead of handing a dead socket to a query |
| `pool_recycle` | `300` | Recycle before Neon's ~300s idle termination (ADR 0005) — proactively avoid the reaper |
| `connect_args["timeout"]` | `5s` | asyncpg connect timeout — a cold/asleep Neon that won't wake in 5s is failed, not waited on |
| `connect_args["command_timeout"]` | `10s` | A query that hangs (lock, slow cold buffer cache) is aborted |
| `pool_timeout` | `5s` | Don't queue a request forever waiting for a pool slot under burst |

### 4b. Map cold-DB failures to **503 + Retry-After**, not a hang

Wrap the DB-touching code path so a connect/timeout failure becomes a clean 503 with a `Retry-After`
hint. The client (and the website's build-time pull, ADR 0025 consequence) retries with backoff.

```python
# src/recalls_api/db.py  (continued) — cold-Neon -> 503 mapping
import asyncpg
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, TimeoutError as SAPoolTimeout

# Cold/asleep Neon presents as connect timeout, pool checkout timeout, or asyncpg connection error.
_COLD_DB_EXC = (
    SAPoolTimeout,
    asyncpg.exceptions.CannotConnectNowError,
    asyncpg.exceptions.TooManyConnectionsError,
    TimeoutError,           # asyncpg connect timeout surfaces as asyncio.TimeoutError
    ConnectionError,
)

def to_http_503_if_cold(exc: BaseException) -> HTTPException | None:
    """Return a 503+Retry-After for cold/asleep-Neon failures; None to re-raise as 500."""
    cause = exc.orig if isinstance(exc, DBAPIError) else exc
    if isinstance(cause, _COLD_DB_EXC):
        # Retry-After: 2s — Neon wake is typically sub-5s; small enough to retry, honest about
        # the wake. The error envelope (doc 03) carries the request_id (§8).
        return HTTPException(
            status_code=503,
            detail="database waking; retry shortly",
            headers={"Retry-After": "2"},
        )
    return None
```

This is invoked from the exception handler / dependency in `main.py` (doc 04): catch `DBAPIError` /
timeout around every query, call `to_http_503_if_cold`, and either raise the 503 or re-raise as a 500.

### 4c. The keep-warm tradeoff

Two ways to reduce cold-start pain, each with a cost:

1. **`min_machines_running = 1`** (Fly) — kills cold start #1 (Fly boot) but runs a machine 24/7
   (eats more of the free allowance) and does **not** keep Neon warm (Neon suspends on DB idle, not
   Fly idle).
2. **Keep-warm cron** — a tiny external pinger (e.g. a GitHub Actions `schedule` cron, or
   cron-job.org) hits `GET /health/db` every ~4 minutes during expected-traffic hours. `/health/db`
   issues `SELECT 1` (§7), which keeps **both** Fly awake and Neon's compute from suspending — at the
   cost of preventing scale-to-zero during the warm window.

**Recommendation:** ship `min_machines_running = 0` and **no always-on keep-warm by default** (true
free-tier, ADR 0005's near-zero-cost stance). Document the keep-warm cron as the lever to pull if/when
the website commits to a latency/freshness SLO — which is itself an ADR 0029 upgrade trigger (§8). If a
keep-warm is added, scope it to a daily window, not 24/7, so most of the day still scales to zero.

> Do **not** wake Neon from the Fly **liveness** check (`/health`) — that would defeat scale-to-zero
> and re-introduce continuous DB cost through the back door. Keep-warm is a deliberate, separate,
> scheduled action against `/health/db`, never the platform liveness probe.

---

## 5. HTTP caching (keyed to the nightly ~03:00 UTC rebuild)

### 5a. The freshness model

Gold marts are **fully rebuilt nightly ~03:00 UTC** (`transform.yml`, architecture.md; both silver and
gold rebuilt each run). Between rebuilds the data is **immutable**. So responses are safe to cache for
hours, and the cache key is "which nightly build produced this."

| Header | Value | Rationale |
|---|---|---|
| `Cache-Control` | `public, max-age=3600` on data endpoints (`/recalls`, `/recalls/{…}`, `/products/search`, `/firms/{id}`) | Data changes at most once/day; 1h is conservative and lets CDNs/clients cache. Tune up toward `max-age` ≈ time-to-next-03:00 if a build-time surface lands (5c). |
| `Cache-Control` | `no-store` on `/health`, `/health/db` | Liveness/readiness must never be cached. |
| `ETag` | weak ETag over the response body, or (preferred) `W/"<build_id>"` once a build id exists (5c) | Enables conditional `GET` → `304 Not Modified` (cheap revalidation). |
| `Last-Modified` | the most-recent rebuild timestamp once exposed (5c); interim: process start time (5b) | Enables `If-Modified-Since`. |
| `Vary` | `Accept-Encoding` | Standard hygiene for compressed responses. |

The API should honor conditional requests: on `If-None-Match` / `If-Modified-Since`, return `304` with
no body when the ETag/Last-Modified matches.

### 5b. ⚠️ The data exposes NO rebuild-timestamp surface today

There is **no column or table** in the gold marts that reliably says "this is build N, finished at T."
`first_seen_at`/`last_seen_at` are pipeline-observation times **per recall**, not a global build stamp
(doc 01 — explicitly "NOT recall age"). So we cannot today derive a correct global `Last-Modified`/
build ETag from the data.

**Interim approach (ship this):**

- `Last-Modified` / build component of the ETag = **process start time** of the API container, written
  once at startup (`app.state.started_at`). Correct enough: the API restarts on every deploy, and a
  cold scale-to-zero machine starts fresh; the value is stable for a given running instance and
  monotonic. It is **conservative** (it changes more often than the data does — on every machine wake),
  which only ever causes a harmless cache miss, never stale data.
- `Cache-Control: public, max-age=3600` independent of the build stamp — bounded staleness regardless.

```python
# src/recalls_api/main.py (lifespan) — interim build stamp
from datetime import UTC, datetime

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = make_engine()
    app.state.started_at = datetime.now(UTC)          # interim Last-Modified anchor (5b)
    app.state.build_tag = os.getenv("GIT_SHA", "dev") # ETag component until a data build-id exists
    yield
    await app.state.engine.dispose()
```

### 5c. The correct fix is upstream (cross-ref doc 07)

**Doc 07 (gold-layer recommendations) should request a build-stamp surface** — e.g. a one-row
`gold_build_info(build_id text, built_at timestamptz)` mart (or a `mart_metadata` row) written at the
end of the nightly transform. Once that exists:

- `Last-Modified` = `built_at` (the real nightly boundary).
- ETag = `W/"<build_id>"` — exact, content-addressable revalidation.
- `Cache-Control: public, max-age=<seconds until 03:00 UTC + margin>` — clients cache precisely until
  the next rebuild.

Until that lands, §5b's interim is correct and safe (over-revalidates, never serves stale). Flag this
as an **open item** carried to doc 07.

---

## 6. Rate limiting (slowapi — API-repo choice, NOT ADR-ratified)

ADR 0024 §6 says only that "abuse control is platform/rate-limit level, not application auth." It does
**not** name slowapi or a limit (doc 02 flags this: "slowapi is an API-repo decision, not ratified by
an ADR"). We ship it as a sane default for an open, unauthenticated API, and label it as such.

- **Library:** `slowapi` (Starlette/FastAPI wrapper over `limits`), keyed per client IP.
- **Limit:** `60/minute` per IP on data endpoints — generous for legitimate browsing, throttles
  scrapers/loops that would hammer a cold free-tier DB. **Tune to the free-tier DB**, not to a big
  number; the bottleneck is Neon connections (§4), not CPU.
- **Exclude** `/health` and `/health/db` from the limit (operators/keep-warm/platform probes).
- **Response:** `429 Too Many Requests` + `Retry-After`, same error envelope (request_id) as everything
  else (§8). Behind Fly's proxy, derive the client IP from `X-Forwarded-For` (the Dockerfile passes
  `--proxy-headers --forwarded-allow-ips '*'`).

```python
# src/recalls_api/middleware.py (rate limit) — slowapi, per-IP. CHOSEN HERE, not ADR-ratified.
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    # Same NESTED error envelope as every other error (decision 7; doc 03 / doc 04 errors._envelope):
    #   {"error": {"type": <ApiError subclass name>, "detail": <message>, "request_id": <uuid>}}
    return JSONResponse(
        status_code=429,
        content={"error": {"type": "RateLimited", "detail": "too many requests", "request_id": rid}},
        headers={"Retry-After": "60"},
    )
# Wire in main.py: app.state.limiter = limiter;
#   app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
#   and exempt /health, /health/db via @limiter.exempt or a path check.
```

> **Caveat for OpenAPI copy (doc 03):** advertise the limit honestly ("requests are rate-limited per
> IP; a 429 with Retry-After means slow down"). Mark it in the doc as a v1 default, tunable, not a
> contractual SLA.

---

## 7. Health endpoints

Two endpoints, two purposes. The distinction is load-bearing for cold-start behavior (§4).

| Endpoint | Kind | Touches Neon? | Used by | Behavior |
|---|---|---|---|---|
| `GET /health` | **Liveness** | **No** | Docker HEALTHCHECK, Fly/Render health check | Always `200 {"status":"ok"}` if the process is up. Must be instant and DB-free so a cold Neon never makes the container look dead and the platform liveness probe never wakes the DB. |
| `GET /health/db` | **Readiness** | **Yes** (`SELECT 1`) | Operators, keep-warm cron (§4c), deploy smoke (§9) | `SELECT 1`, times the round-trip, reports cold-wake latency. `200` when reachable; `503 + Retry-After` (via §4b) when Neon is cold/unreachable. |

```python
# src/recalls_api/health.py
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api.db import get_conn, to_http_503_if_cold

router = APIRouter(tags=["operational"])

@router.get("/health")
async def health() -> dict[str, str]:
    # Liveness: process-only. No DB. Never cached (Cache-Control: no-store set by middleware).
    return {"status": "ok"}

@router.get("/health/db")
async def health_db(conn: Annotated[AsyncConnection, Depends(get_conn)]) -> dict[str, object]:
    # Readiness: proves Neon reachable and surfaces cold-wake latency. The get_conn dependency
    # (decision 6) yields one read-only Core connection from app.state.engine.
    start = perf_counter()
    try:
        await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — map cold DB to 503, else re-raise as 500
        http = to_http_503_if_cold(exc)
        if http is not None:
            raise http from exc
        raise
    elapsed_ms = round((perf_counter() - start) * 1000, 1)
    # cold_wake=True is a heuristic: a >1s SELECT 1 almost always means Neon was suspended.
    return {"status": "ok", "db_latency_ms": elapsed_ms, "cold_wake": elapsed_ms > 1000}
```

> Fly's `[[http_service.checks]]` and the Docker `HEALTHCHECK` both point at `/health` (liveness), per
> §1/§2 — **never** `/health/db`, or the platform would wake Neon on every probe and defeat
> scale-to-zero.

---

## 8. Observability (structlog JSON; v1 = operator reads platform logs)

### 8a. Stance (ADR 0021 + ADR 0029, mirrored from the pipeline)

v1 observability is **structured JSON logs to stdout**, read by the operator via the platform's log
viewer (`flyctl logs` / Render logs). **No Sentry, no Datadog, no OTel** in v1 — this mirrors ADR 0029
exactly. ADR 0029 explicitly names the FastAPI layer as the eventual home for `/health` + Sentry "when
Phase 8 ships," but defers it; we honor the deferral.

### 8b. structlog config (mirror the pipeline's `src/config/logging.py`)

Reuse the pipeline's pattern almost verbatim: JSON to stdout in production (`LOG_FORMAT=json`,
ConsoleRenderer only when a TTY / `LOG_FORMAT=console`), `merge_contextvars` first so per-request
context flows onto every line, third-party loggers (`sqlalchemy.engine`, `sqlalchemy.pool`, `uvicorn`,
`asyncpg`) pinned to `WARNING`. The one addition for an HTTP server vs a batch pipeline is a
**per-request `request_id`** bound via a contextvars middleware (the pipeline binds `run_id`; we bind
`request_id`).

```python
# src/recalls_api/middleware.py (request_id) — uuid per request, bound via contextvars.
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = structlog.get_logger()

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        request.state.request_id = request_id  # for the error envelope (doc 03) + 429/503 bodies
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id  # echo back for client correlation
        log.info("request.completed", status_code=response.status_code)
        return response
```

### 8c. Per-request JSON log fields

Every line carries (via `merge_contextvars` + the structlog processor chain):

| Field | Source | Notes |
|---|---|---|
| `timestamp` | `TimeStamper(fmt="iso")` | ISO-8601 UTC |
| `level` | `add_log_level` | info/warning/error |
| `logger` | `add_logger_name` | module |
| `event` | log call | e.g. `request.completed`, `db.cold_wake`, `query.slow` |
| `request_id` | middleware contextvar | the correlation id, **also echoed in the error envelope** (doc 03) and the `429`/`503` bodies |
| `method`, `path` | middleware contextvar | request line |
| `status_code` | on `request.completed` | response status |
| `exc_info` (structured) | `format_exc_info` | on errors, before JSONRenderer (mirrors pipeline) |

The error envelope returned to clients (defined in doc 03) **includes `request_id`** so a user can quote
it and the operator can grep `flyctl logs` for that exact id — the v1 "operator reads logs" loop.

### 8d. Named ADR 0029 upgrade triggers (when to add Sentry/OTel)

These are the **explicit thresholds from ADR 0029** that justify moving to a real observability stack
(Sentry / Datadog / Grafana / OTel — choice deferred to that supersession ADR). The build session does
**not** add any of these now; it documents them so the upgrade has a named gate:

| Trigger (ADR 0029) | Threshold | Relevance to recalls-api |
|---|---|---|
| **Sustained failure rate** | A workflow/path fails ≥3 consecutive days, OR ≥30% of runs over 14 days | For the API: sustained 5xx rate or repeated cold-DB 503 storms over days. |
| **Multi-source incident** | Two+ independent failures at once (not a shared "Neon is down") | Two unrelated API faults the operator can't triage by log-grep fast enough. |
| **Time-to-detection** | A real failure is found by a **downstream consumer / the user** before the operator | The website or an API consumer reports breakage first → the "operator looks" model broke. **Most likely first trigger for a public API.** |
| **Consumer SLO commitment** | Any external user / ADR-encoded plan commits to "freshness within X hours" | The website committing to a freshness/latency SLO (also the lever for keep-warm §4c / `min_machines_running=1`). |
| **Volume** | Sustained per-run >60 min, or a state table >~100K rows | API analogue: traffic where stdout-log scanning stops being usable. |
| **Operator change** | A second operator joins / handoff | Tribal "check logs weekly" doesn't survive a team — needs push alerting. |

When one fires: file the supersession ADR (next number) titled "Application observability v2: <stack>",
then add Sentry's ASGI middleware (catches unhandled exceptions) and/or OTel. structlog's field shape
and `request_id` correlation **do not change** — the upgrade is additive (ADR 0029 "what stays").

---

## 9. CD — `deploy.yml` (flyctl deploy on push to main)

Deploy is `flyctl deploy` from a GitHub Actions workflow on push to `main`, with the Fly API token in
repo secrets (ADR 0025). This is the **CD** workflow; the **CI gate** (uv sync → ruff → pyright →
pytest → openapi drift → pre-commit) lives in `ci.yml` and is specified in **doc 05** — this deploy
workflow runs only after CI is green on `main`.

```yaml
# .github/workflows/deploy.yml — CD to Fly.io on push to main (ADR 0025).
name: deploy
on:
  push:
    branches: [main]
  workflow_dispatch: {}   # manual re-deploy / rollback trigger

concurrency:
  group: deploy-fly        # never run two deploys at once
  cancel-in-progress: false

permissions:
  contents: read           # least privilege (secrets-management.md); no write needed

jobs:
  deploy:
    name: flyctl deploy
    runs-on: ubuntu-latest
    environment: production # scopes FLY_API_TOKEN to a protected environment
    steps:
      - uses: actions/checkout@v4

      - uses: superfly/flyctl-actions/setup-flyctl@master

      # Build args feed the Dockerfile's OCI labels (§1). The image builds on Fly's builder.
      - name: Deploy to Fly.io
        run: |
          flyctl deploy --remote-only \
            --build-arg GIT_SHA="${GITHUB_SHA::7}" \
            --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}   # repo/environment secret, never inline

      # Readiness smoke after release: prove the new machine can reach Neon (wakes it once).
      # Allowed to be slow / retry — first hit may pay both cold starts (§4).
      - name: Post-deploy readiness smoke
        run: |
          set +x
          for i in $(seq 1 6); do
            code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
              https://recalls-api.fly.dev/health/db || echo 000)
            echo "attempt $i: /health/db -> $code"
            [ "$code" = "200" ] && exit 0
            sleep 10
          done
          echo "::error::/health/db not healthy after deploy"; exit 1
```

**Secrets posture (secrets-management.md):**

- `FLY_API_TOKEN` is a GitHub **environment-scoped** secret (`environment: production`), passed via
  `env:`, never inlined into a `run:` string. Rotate with `flyctl tokens create deploy` +
  `gh secret set FLY_API_TOKEN`.
- The Neon DSN (`NEON_DATABASE_URL_RO`) is **NOT** a GitHub secret and **NOT** in `fly.toml` — it is a
  **Fly runtime secret** set out-of-band: `flyctl secrets set NEON_DATABASE_URL_RO='postgresql://recalls_readonly:…@ep-xxx.<region>.aws.neon.tech/recalls?sslmode=require'`.
  Fly injects it into the container env; CI never sees it.
- No OIDC/cloud-credential exchange is needed (Fly token is the only deploy credential).

**Render fallback CD (documented, not active):** if Render becomes primary, replace this job with a
`curl -X POST "$RENDER_DEPLOY_HOOK_URL"` step (deploy-hook secret) and set `autoDeploy: true` in
`render.yaml` (§2b). The smoke step is identical against the Render URL.

**Rollback:** `flyctl releases` to list, `flyctl releases rollback <version>` (or re-push the prior
green commit). The post-deploy smoke failing does **not** auto-rollback in v1 (the previous machine is
already replaced by the time the smoke runs) — the operator rolls back manually. Auto-rollback on
smoke failure is a documented future enhancement, not v1 scope.

---

## 10. Open items & judgment calls

| # | Item | Disposition |
|---|---|---|
| 1 | **Read-only role name/grants/endpoint/region** (§3f) | **Operator confirmation, blocking** `db.py`. Recommended `recalls_readonly` + `SELECT` on 3 marts + `default_transaction_read_only=on` + direct endpoint + `NEON_DATABASE_URL_RO`. From doc 02 "MUST re-verify." |
| 2 | **No rebuild-timestamp surface in gold** (§5) | Judgment call: interim `Last-Modified`=process start, ETag component=`GIT_SHA`; over-revalidates, never stale. **Cross-ref doc 07** to request a `gold_build_info`/`mart_metadata` build-stamp mart. |
| 3 | **slowapi limit `60/minute`** (§6) | Judgment call: not ADR-ratified (doc 02). Sane open-API default tuned to free-tier DB, not a contractual SLA; tunable. |
| 4 | **`min_machines_running=0` + no default keep-warm** (§4c) | Judgment call favoring ADR 0005 near-zero-cost. Keep-warm cron / `=1` are documented levers gated on a website SLO (an ADR 0029 trigger). |
| 5 | **Fly region `iad` / Render `virginia`** (§2) | Assumption pending the confirmed Neon region (§3f). |
| 6 | **Cold-DB timeouts (5s connect / 10s command, Retry-After 2s)** (§4) | Judgment call: Neon wake is typically sub-5s; values chosen to fail fast without flapping on a normal wake. Revisit if production cold waits exceed 5s (then raise connect_timeout per operations.md note, not remove the cap). |
| 7 | **Direct vs pooled Neon endpoint** (§3e) | Recommend **direct** (own the pool); if operator mandates pooled, add `statement_cache_size=0`. |
| 8 | **Auto-rollback on smoke failure** (§9) | Out of v1 scope; manual `flyctl releases rollback`. Documented as a future enhancement. |
