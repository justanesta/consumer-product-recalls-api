Purpose: ADR registry for the `consumer-product-recalls-api` repo — index, writing rules, and next free number.

# Architecture Decision Records

Every non-trivial design decision is captured as an ADR using Michael Nygard's template: **Status / Date / Context / Decision / Consequences**.

ADRs are **immutable once Accepted.** A new ADR supersedes rather than edits an old one; the old ADR's Status line is updated to `Superseded by ADR NNNN` and it stays in place. This preserves the record of how thinking evolved.

Write an ADR when someone reading the code six months later would ask "why this and not the obvious alternative?" Trivial choices (lint config, variable naming) do not get ADRs; substantive tradeoffs do.

> For how docs *other than ADRs* are organized (the ownership map, single-home rule, doc types), see [`documentation/documentation_model.md`](../documentation_model.md).
> The pipeline repo's ADR registry (the upstream authority) is at [`consumer-product-recalls/documentation/decisions/README.md`](../../../consumer-product-recalls/documentation/decisions/README.md).

---

## By topic

### Security / DB Access

- [0001 — Read-only by construction](./0001-read-only-by-construction.md) — dedicated `recalls_readonly` role + per-connection `default_transaction_read_only=on` session guard; writable connection in production is a hard boot refusal

### Data Access Layer

- [0002 — SQLAlchemy Core async over asyncpg; no ORM, no reflection](./0002-sqlalchemy-core-async-asyncpg-no-orm.md) — lightweight `sa.table()` literals targeting fixed gold mart columns; stateless pure query-builder modules; asyncpg driver

### API Contract / Error Handling

- [0003 — Uniform error envelope](./0003-uniform-error-envelope.md) — `{"error":{"type","detail","request_id"}}` on every non-2xx; cold-DB → 503 + `Retry-After: 5`; catch-all → opaque 500; traceback to logs only
- [0010 — Committed `openapi.json` snapshot as drift-detection contract](./0010-openapi-committed-snapshot-drift-contract.md) — generator (`recalls_api.export_openapi`) is source of truth; snapshot checked into repo; pre-commit + CI fail on drift

### Browser access (CORS)

- [0014 — Open CORS for the public, read-only API](./0014-open-cors-public-read-only-api.md) — `CORSMiddleware` outermost with `allow_origins=["*"]`, `allow_methods=["GET"]`; safe because the API is public + credential-free; enables direct browser `fetch()` from the website

### Pagination

- [0004 — Keyset (seek) pagination](./0004-keyset-cursor-codec.md) — opaque base64url 2-tuple cursor; two shapes (`published_at DESC, id ASC` and `rank DESC, id ASC`); tampered payload → 400 before DB

### Configuration / Secrets

- [0005 — pydantic-settings config; single required secret; fail-loud at boot](./0005-pydantic-settings-fail-loud-at-boot.md) — `NEON_DATABASE_URL_RO` as `SecretStr`; `lru_cache` singleton called in lifespan so missing DSN surfaces at startup, not mid-request

### Abuse Control

- [0006 — Per-IP rate limiting via slowapi](./0006-per-ip-rate-limiting-slowapi.md) — in-process `MemoryStorage`; 60 req/min default; per-machine (not global) caveat documented; health endpoints exempted

### HTTP Caching

- [0007 — HTTP `Cache-Control` keyed to nightly rebuild](./0007-http-cache-control-nightly-rebuild.md) — `public, max-age=300` on 200 GETs; weak ETag per startup (`W/"version-startup_id"`); `no-store` on `/health*`; per-rebuild ETag deferred to R6

### Observability

- [0008 — structlog JSON logging + per-request `request_id` correlation](./0008-structlog-request-id-correlation-middleware.md) — `RequestIdMiddleware` mints/reads `X-Request-ID`, binds to structlog contextvars, echoes on response, logs access line with latency

### Testing

- [0009 — Testing strategy: unit / integration / contract; 85% gate](./0009-testing-strategy-unit-integration-contract.md) — unit tests run without DB; testcontainers-postgres for integration; OpenAPI snapshot as contract test; `pytest --cov-fail-under=85` in CI

### Search

- [0011 — Recall-grain full-text search (Option B)](./0011-recall-grain-fts-option-b.md) — `search_vector` tsvector GIN on `mart_recall_summary`; `websearch_to_tsquery('english', ...)`; `ts_rank_cd` with explicit `{D,C,B,A}` weights; keyset on `(rank DESC, recall_event_id ASC)`

### Operational / Deployment

- [0012 — Health/readiness split](./0012-health-readiness-split.md) — `GET /health` is process-only (no DB); `GET /health/db` fires `SELECT 1`; Fly.io liveness probe targets `/health` only so probes never wake sleeping Neon compute
- [0013 — CI-gated auto-deploy: `workflow_run` trigger on CI success](./0013-ci-gated-workflow-run-auto-deploy.md) — green CI on `main` triggers `flyctl deploy --remote-only`; SHA-pinned checkout ensures exact tested commit is deployed; scale-to-zero on Fly.io

---

## By number

| # | Title | Topic |
|---|-------|-------|
| [0001](./0001-read-only-by-construction.md) | Read-only by construction: dedicated `recalls_readonly` role + per-connection `transaction_read_only` guard | Security / DB Access |
| [0002](./0002-sqlalchemy-core-async-asyncpg-no-orm.md) | SQLAlchemy Core async over asyncpg; no ORM, no reflection | Data Access Layer |
| [0003](./0003-uniform-error-envelope.md) | Uniform error envelope: `{error:{type,detail,request_id}}`, cold-DB → 503, opaque 500 | API Contract / Error Handling |
| [0004](./0004-keyset-cursor-codec.md) | Keyset (seek) pagination: opaque base64url 2-tuple cursor, DESC-then-ASC seek WHERE | Pagination |
| [0005](./0005-pydantic-settings-fail-loud-at-boot.md) | pydantic-settings config with `SecretStr` DSN; single required secret; fail-loud at boot | Configuration / Secrets |
| [0006](./0006-per-ip-rate-limiting-slowapi.md) | Per-IP rate limiting via slowapi (in-process `MemoryStorage`; per-machine caveat documented) | Abuse Control |
| [0007](./0007-http-cache-control-nightly-rebuild.md) | HTTP `Cache-Control` keyed to nightly rebuild; weak ETag per startup; no server-side cache v1 | HTTP Caching |
| [0008](./0008-structlog-request-id-correlation-middleware.md) | structlog JSON logging + per-request `request_id` correlation via contextvars middleware | Observability |
| [0009](./0009-testing-strategy-unit-integration-contract.md) | Testing strategy: unit (no DB) / testcontainers-postgres integration / OpenAPI-contract snapshot; 85% coverage gate | Testing |
| [0010](./0010-openapi-committed-snapshot-drift-contract.md) | Committed `openapi.json` snapshot as drift-detection contract; generator is source of truth | API Contract |
| [0011](./0011-recall-grain-fts-option-b.md) | Recall-grain full-text search (Option B): `search_vector` on `mart_recall_summary`, `ts_rank_cd` weighting | Search |
| [0012](./0012-health-readiness-split.md) | Health/readiness split: DB-free `/health` liveness vs `SELECT 1` `/health/db` readiness | Operational / Deployment |
| [0013](./0013-ci-gated-workflow-run-auto-deploy.md) | CI-gated auto-deploy: `workflow_run` trigger on CI success; scale-to-zero on Fly.io | CI/CD |
| [0014](./0014-open-cors-public-read-only-api.md) | Open CORS for the public, read-only API: `CORSMiddleware` outermost, `allow_origins=["*"]`, GET-only | Browser access (CORS) |

---

## Upstream decisions (pipeline repo)

The following decisions were made in the pipeline repo and govern this API repo. Do not restate them here — link to the originals.

| Pipeline ADR | Title | What it governs for this repo |
|---|---|---|
| [pipeline:0024](../../../consumer-product-recalls/documentation/decisions/0024-serving-layer-api-design.md) | Serving-layer API design | FastAPI + SQLAlchemy-Core-async over the gold marts; four endpoints (recalls list/detail/search, products/search, firms/detail); keyset pagination (no OFFSET); no ORM; open/no-auth v1; committed `openapi.json` snapshot as contract artifact; generator is source of truth |
| [pipeline:0025](../../../consumer-product-recalls/documentation/decisions/0025-api-deployment-target.md) | API deployment target | Fly.io as primary; Render as documented fallback; Cloudflare Workers rejected (Pyodide/WASM cannot load asyncpg); read-only Neon access via dedicated restricted role; scale-to-zero with auto-wake posture |
| [pipeline:0039](../../../consumer-product-recalls/documentation/decisions/0039-frontend-framework.md) | Frontend framework | Astro (islands architecture) on a free static host as the consumer-facing website; separate repo from this one; this repo has no frontend concerns |
| [pipeline:0042](../../../consumer-product-recalls/documentation/decisions/0042-gold-serving-marts-published-read-contract.md) | Gold serving marts are a published read contract | Names the load-bearing invariants of `mart_recall_summary` / `mart_product_search` / `mart_firm_profile` / `gold_meta` that this API depends on; breaking changes require API coordination and a `gold_meta.schema_version` bump; column names, nullability, index shapes, and surrogate-key recipes that `sa.table()` literals and keyset sort assume are pinned here |

---

## Writing new ADRs

1. Pick the next sequential number. **The next free number is `0015`.** (This line is the single source of truth — do not reserve numbers in plan docs.)
2. File name: `NNNN-kebab-case-title.md`.
3. Use the Nygard template: **Status / Date / Context / Decision / Consequences**. Any existing ADR is a valid model.
4. Add an entry under the appropriate topic section above **and** in the numeric table.
5. If the new ADR supersedes a previous one, update the superseded ADR's Status line to `Superseded by ADR NNNN` and add a link. The old file stays.
6. Use amendment (updating a section in the original) when the core decision stands but needs refinement. Use supersession when the decision itself changes.
