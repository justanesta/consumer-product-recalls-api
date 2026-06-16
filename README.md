# consumer-product-recalls-api

An **open, read-only** FastAPI service over the consumer product recalls **gold marts** (CPSC, FDA,
USDA, NHTSA, USCG) produced by the separate pipeline repo
[`consumer-product-recalls`](https://github.com/justanesta/consumer-product-recalls). No auth, no
credentials — it only reads. This repo owns **no** schema, migrations, or dbt; the pipeline writes
gold, this reads it.

## Endpoints (v1)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/recalls` | List + filter recalls (keyset pagination) |
| `GET` | `/recalls/{source}/{recall_id}` | One recall (full detail) |
| `GET` | `/recalls/search` | Recall-grain keyword full-text search (ts_rank_cd), same filters as /recalls |
| `GET` | `/products/search` | "Is my product recalled?" — keyword FTS + exact `hin`/`model`, recall-level UPC |
| `GET` | `/firms/{id}` | One canonical firm profile |
| `GET` | `/health`, `/health/db` | Liveness / readiness |
| `GET` | `/openapi.json`, `/docs`, `/redoc` | Auto-generated spec + UIs |

For data-model root causes see [`documentation/data_contract.md`](documentation/data_contract.md); for per-endpoint caveats see [`documentation/api-reference.md`](documentation/api-reference.md).

## Stack

FastAPI · Pydantic v2 · SQLAlchemy **Core** (async) over **asyncpg** · structlog · slowapi · Python
3.12 · `uv`. Deploys to Fly.io (Render fallback). See `project_scope/build/` for the full build spec.

## Local setup

Requires [`uv`](https://docs.astral.sh/uv/) (it provisions Python 3.12 automatically) and, optionally,
`direnv`.

```bash
uv sync                       # create .venv, install deps (incl. dev group)
cp .env.example .env          # then set NEON_DATABASE_URL_RO (read-only role; see below)
uv run pre-commit install     # enable the lint/type/secret hooks
uv run uvicorn --factory recalls_api.main:create_app --reload   # http://127.0.0.1:8000/docs
```

> **Database role.** The API connects with a dedicated **read-only** Neon role
> (`recalls_readonly`), *not* the pipeline's read+write `recalls_app`. That role is provisioned in the
> pipeline repo — see its `project_scope/serving-layer-gold-readiness-plan.md` (R1). Until it exists,
> run tests (which use a throwaway seeded Postgres) rather than connecting to live Neon.

## Quality gate

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest                       # add --cov-fail-under=85 in CI
```

## Where the design lives

**Operational docs** (`documentation/`):
- [`architecture.md`](documentation/architecture.md) — request lifecycle, module responsibilities, diagrams
- [`development.md`](documentation/development.md) — local setup, quality gate, branching, how-to-add-an-endpoint
- [`operations.md`](documentation/operations.md) — CI→deploy pipeline, Fly.io config, runbook
- [`data_contract.md`](documentation/data_contract.md) — gold mart read contract, surrogate keys, data caveats
- [`api-reference.md`](documentation/api-reference.md) — exhaustive per-endpoint reference
- [`frontend-api-docs-handoff.md`](documentation/frontend-api-docs-handoff.md) — how to publish docs on the website
- [`decisions/`](documentation/decisions/) — ADR registry (local + upstream pipeline ADRs)

**Build specs** (`project_scope/build/`):
- `00-README-build-guide.md` — start here: provenance, conventions, prerequisites.
- `01` ground truth (gold-mart schema) · `02` plan reconciliation · `03` API contract + models ·
  `04` implementation blueprint · `05` testing/CI · `06` deploy/ops · `07` gold-layer asks ·
  `08` commit plan.

**Status:** deployed at `https://consumer-product-recalls-api.fly.dev`. Branch-per-feature with CI-gated auto-deploy to Fly.io on every green merge to `main`.
