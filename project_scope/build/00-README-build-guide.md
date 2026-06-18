# recalls-api — Build Guide (start here)

This directory is the **hardened, build-ready spec** for the `recalls-api` repo: an **open (no auth,
no credentials), read-only** FastAPI service over the PostgreSQL **gold marts** produced by the
separate pipeline repo `justanesta/consumer-product-recalls`. It hardens
[`../fastapi-serving-layer-plan.md`](../fastapi-serving-layer-plan.md) into something a long-running
Claude Code session can execute against without guessing.

> The original plan is the *design intent*. These `00`–`08` docs **supersede it on facts** — where they
> disagree with the plan, trust these docs. Where they state a schema fact, doc `01` is the source of truth.

## Provenance (what the facts are pinned to)

| Field | Value |
|---|---|
| Source repo | `justanesta/consumer-product-recalls` (the pipeline; **not** this repo) |
| Local checkout | `/home/justanesta/projects/consumer-product-recalls` |
| Authoritative branch | **`feature/pre-go-live-validation`** |
| Commit | `39dcbda3da7c1915b3c660327ebdd8b8dab09bb5` (2026-06-13) |
| `main` | 1 commit behind — lacks the CPSC `recall_product_id` stable-key migration + ADR 0041. **Do not** treat `main` as ground truth. |
| Note | The plan's references to branch `feature/phase-7-production-plus-todos` are **stale** (that branch is gone). |

**Re-verify** any schema fact by reading the dbt model SQL in the checkout at that commit:
`dbt/models/gold/mart_*.sql`, `dbt/models/silver/*.sql`, `dbt/models/gold/_gold.yml`,
`dbt/models/silver/_silver.yml`. `documentation/data_schemas.md` is a **glossary** — it does *not* declare
Postgres column types; the dbt SQL is the type-bearing source.

## How to use these docs

Read in order; each builds on the prior:

| Doc | What it is | When you need it |
|---|---|---|
| **00** (this) | Build guide, conventions, prerequisites, doc map | First |
| **01** `ground-truth-gold-marts` | Authoritative per-mart column/type/index/null/jsonb reference; enums; the `recall_event_id` md5 key; firm-sidecar shapes; compact `fct_*` table | The schema contract — keep open while coding |
| **02** `plan-reconciliation` | Drift report (plan vs reality), **Decisions-locked** + **MUST-re-verify** lists | To understand *why* a decision was made |
| **03** `api-contract-and-models` | Endpoint-by-endpoint contract (params, validation, error responses, OpenAPI copy) + every Pydantic v2 model field-by-field | Building routers + models |
| **04** `implementation-blueprint` | Module-by-module skeletons: `settings`/`db`/`pagination`/`deps`/`queries`/`routers`/`errors`/`logging`/`main` | Writing the code |
| **05** `testing-and-ci-plan` | 3 test layers, `seed_gold.sql` cassette spec + mart DDL, `conftest` fixtures, contract tests, full `ci.yml` | Writing tests + CI |
| **06** `deployment-and-ops` | Dockerfile, `fly.toml`/`render.yaml`, **read-only role**, cold-start, cache headers, slowapi, health, observability, `deploy.yml` | Deploy + ops |
| **07** `gold-layer-recommendations` | **Cross-repo** dbt/index/role changes for the pipeline operator (prioritized) | Coordinating with the pipeline repo |
| **08** `commit-plan-and-open-questions` | Phased branch/commit plan + per-branch gates + open-questions ledger + kickoff checklist | Sequencing the build |

## Canonical conventions (locked — already reconciled across all docs)

- **Stack:** FastAPI + Pydantic v2 + SQLAlchemy **Core** (not ORM) async over **asyncpg**; Python **3.12**; `uv`; `ruff` + `pyright`.
- **Package root:** `src/recalls_api/` (imports `from recalls_api.…`).
- **Settings:** `settings.py`, pydantic-settings `BaseSettings`, `extra="ignore"`, **fail-loud at boot**.
- **DB DSN env var:** **`NEON_DATABASE_URL_RO`** (`SecretStr`) — mirrors the pipeline's `NEON_DATABASE_URL`; the `_RO` encodes the read-only posture. **The API must use a dedicated read-only role, never the pipeline's `recalls_app` (which can write).**
- **Per-request DB seam:** dependency **`get_conn`** yielding a Core `AsyncConnection` (engine/pool live on `app.state`, opened/disposed in `lifespan`).
- **Detail lookup:** compute `recall_event_id = md5(f"{SOURCE_UPPER}|{recall_id}")`, hit `UNIQUE(recall_event_id)`. **No composite index** (plan's C0c-dbt is dropped).
- **`{source}` path param:** declared as `str`, uppercased + validated against the `Source` StrEnum in-handler (case-insensitive URLs work; lowercase is normalized, not rejected).
- **Pagination:** keyset/seek (never OFFSET); `Cursor.encode`/`Cursor.decode` (base64url, tamper → `BadCursor`); `build_page(...) -> Page[T]` envelope `{items, next_cursor: str | None, limit}`; fetch `limit+1` for `has_next`; no COUNT by default (`?with_total=true` opt-in). `limit`: `Query(ge=1, le=100)` default 25.
- **Date filters:** `published_after → published_at >= :d::date`; `published_before → published_at < (:d::date + INTERVAL '1 day')` (inclusive of the whole `before` day).
- **Search:** Postgres FTS via `websearch_to_tsquery('english', :q)` over the stored `search_vector` (GIN), ranked by `ts_rank_cd`; exact id via btree `hin`/`model`; **UPC via `recall_product_upcs` jsonb containment** (`@>`) — the per-product `upc` column is NULL for every row today; **no fuzzy/typo search** (pg_trgm off). `q`/`firm` `min_length=2`.
- **Error envelope:** `{"error": {"type", "detail", "request_id"}}`. Taxonomy: `ResourceNotFound`=404, `InvalidParameter`=422, **`BadCursor`=400**, `UpstreamUnavailable`=503 (+`Retry-After`), `RateLimited`=429 (+`Retry-After`); catch-all 500 logs the traceback and returns an opaque body (never leak SQL/DSN).
- **Logging/observability:** structlog JSON to stdout; per-request `request_id` via contextvars middleware, echoed in the envelope + `X-Request-ID`. v1 = operator reads platform logs; no Sentry/OTel (named upgrade triggers in 06/ADR 0029).
- **Testing/CI:** pytest, **`--cov-fail-under=85`**, offline/deterministic, never touches prod Neon; integration via `httpx.AsyncClient` + `ASGITransport` against a **seeded Postgres service container** (`seed_gold.sql`). CI gate: `uv sync → ruff check → ruff format --check → pyright → pytest → openapi drift → pre-commit run --all-files`.
- **OpenAPI:** FastAPI-generated is the source of truth; `python -m recalls_api.export_openapi` (writes the file directly, no redirect; `--check` to verify); committed snapshot is the contract-test fixture (fail on drift).
- **Deploy:** Fly.io (Render fallback; Cloudflare Workers rejected — asyncpg can't run on Pyodide/WASM). `min_machines_running=0`; cold DB → 503+`Retry-After` (never hang). HTTP cache headers keyed to the nightly ~03:00 UTC rebuild.

## Prerequisites & blockers

1. **THE ONE HARD BLOCKER for live deploy — a new read-only DB role.** The existing `recalls_app`
   (pipeline migration `0033`) has `GRANT SELECT, INSERT, UPDATE ON ALL TABLES` — it can **write**, so the
   API must not use it. The pipeline repo/operator must provision a dedicated read-only role
   (proposed `recalls_readonly`): `GRANT SELECT` on the gold marts + `ALTER ROLE … SET
   default_transaction_read_only = on`, following migration 0033's NOLOGIN-SQL-shell pattern (avoids
   Neon's `neon_superuser`/`pg_write_all_data` auto-membership trap; operator sets `LOGIN PASSWORD`
   out-of-band). See **07 #2** for the proposed migration `0034`. This does **not** block local/CI builds
   (they use a throwaway seeded container).
2. **Confirm with the operator** (does not block coding, blocks wiring `db.py`/deploy): exact role name,
   grant scope (gold-only vs all tables), `default_transaction_read_only` placement, the DSN env var name
   (`NEON_DATABASE_URL_RO` proposed), pooled (PgBouncer `-pooler`) vs **direct** Neon endpoint
   (direct recommended for an owned pool), and the Neon region (for Fly/Render co-location).
3. **Cache-header quality** depends on a gold **rebuild-timestamp surface** (07 #6) — until it exists, ship
   a coarse `max-age` + process-start `Last-Modified` fallback.

## Pre-go-live gold change — ✅ APPLIED (gold-readiness R5)

**Rename the firm-sidecar mart output columns** `establishment_attributes`/`manufacturer_attributes`/
`fda_attributes` → `firm_usda_attributes`/`firm_uscg_attributes`/`firm_fda_attributes` (the old names
were misleading: `establishment`=USDA, `manufacturer`=USCG). This is a **dbt model edit** (2 spots in
`mart_firm_profile.sql`) + `dbt build`, **not** an Alembic migration; verified **zero downstream
breakage** (only `fct_recalls_by_firm` reads the mart, and it doesn't use these columns). It is free now
(no API clients exist) and contract-breaking after the API ships. Full detail in **07 #5**. **This was
applied upstream (R5) before the API's openapi.json freeze**; `01`/`03` and the shipped API use the
source-aligned names `firm_usda_attributes`/`firm_uscg_attributes`/`firm_fda_attributes`.

## Open questions still to resolve (see 08 for the full ledger)

`R1` read-only role specifics (operator) · `R2` `hazards` jsonb element shape · `R3` `model_year` int-vs-text ·
`R4` per-mart row counts (don't hard-code "130k") · `R5` slowapi limits (API-repo choice, not ADR-ratified) ·
`R6` exact Neon Postgres major version · `R7` gold rebuild-timestamp surface for ETag/Last-Modified.

## Build-session kickoff checklist

1. Read `00`→`08` (this guide, then ground truth, then the rest).
2. Confirm the read-only role + endpoint + env var with the operator (prereq #1/#2); until then, build against the seeded container.
3. `uv init` + `pyproject.toml` (deps, ruff, pyright, pytest, `--cov-fail-under=85`); package `src/recalls_api/`.
4. Scaffold first: `settings.py`, `db.py` (lazy engine in `lifespan`), `errors.py`, `logging.py`, `main.py`, `/health` + `/health/db`.
5. Stand up `tests/fixtures/seed_gold.sql` + `conftest.py` (service-container DB) early — every endpoint test rides it.
6. Build per the branch plan in **08**: scaffold → recalls → (products ∥ firms) → openapi-contract → deploy.
7. Keep every endpoint's honest caveats in its OpenAPI `description` (no fuzzy search, recall-level UPC, tri-state `is_active`, source-native `classification`, unfiltered-sort cost).
8. Regenerate + commit `openapi.json` whenever the API surface changes; the contract test guards drift.
9. Don't reintroduce the dropped composite index or query the all-null `upc` column.
10. Treat `recall_event_id`/`recall_product_id`/`firm_id`/cursors as **opaque**.
