# 0009 - Testing strategy: unit (no DB) / testcontainers-postgres integration / OpenAPI-contract snapshot; 85% coverage gate

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

> Upstream framing: pipeline ADR 0015 (unit/integration/e2e pyramid, 85% floor, swappable `test_db_url` seam) and ADR 0018 (CI posture, gate sequence, branch protection) are the house standards this ADR adapts — not re-litigates.

---

## Context

This repo owns no dbt, no bronze/silver ingest, and makes no outbound HTTP calls. That eliminates `dbt parse`, `pytest-vcr`, `respx`, and the pipeline's Neon-branch e2e as relevant tooling. What remains is a pure async FastAPI service whose correctness depends on:

- **SQLAlchemy Core query builders** (`queries/*.py`) — pure Python, no I/O, but must produce bound parameters (never string-interpolated values) and the correct SQL shape for each filter combination.
- **Postgres-specific semantics** — GIN `tsvector` FTS (`@@`, `ts_rank_cd`), `jsonb` array containment (`@>`), `text[]` GIN containment, `timestamptz` comparison, tri-state `boolean` (NULL ≠ false), and the `UNIQUE(recall_event_id)` index hit for the md5 detail path. These cannot be faked with a mocked session.
- **A committed `openapi.json` snapshot** that the pipeline and frontend treat as a published contract artifact (pipeline ADR 0024 §4). Any model field rename, optionality flip, or description change that drifts the snapshot silently is a contract break.
- **Async test client** — `TestClient` (sync) is incompatible with the asyncpg/SQLAlchemy-Core-async event loop; `httpx.AsyncClient` over `ASGITransport` is the correct equivalent.

The 85% coverage floor (ADR 0015) is the house gate. The `--cov-fail-under` is intentionally absent from `pyproject.toml`'s `addopts` so early scaffold commits are not blocked; it is added only in the CI invocation. (the `addopts` in `pyproject.toml`; the coverage step in `ci.yml`)

---

## Decision

Three layers run in a single `pytest` invocation; coverage is measured over their union.

1. **Unit — `tests/test_*.py` (root level), no DB.** Covers:
   - Query-builder compiled SQL + bound params: assert via `stmt.compile(dialect=asyncpg_dialect)` → `str(compiled)` + `compiled.params`. Proves each filter predicate is present and all values are bound, not interpolated — the SQL-injection gate from `CLAUDE.md`. (`project_scope/build/05-testing-and-ci-plan.md §4.1`)
   - Cursor codec: `Cursor.encode`/`Cursor.decode` round-trip via Hypothesis property test; any garbage, truncated, or wrong-arity payload raises `BadCursor` (HTTP 400). (the `Cursor.encode`/`Cursor.decode` codec in `pagination.py`, `project_scope/build/05-testing-and-ci-plan.md §4.2`)
   - Pydantic null-coercion: mart `NULL` jsonb arrays coerce to `[]`; mart `NULL` boolean `is_active` is `None`, not `False` (tri-state honesty). (the `_none_to_list` validator on `RecallDetail` (`models/recalls.py`), `project_scope/build/05-testing-and-ci-plan.md §4.3`)
   - `recall_event_id` derivation: `hashlib.md5(f"{source.upper()}|{recall_id}".encode()).hexdigest()` matches Postgres `md5()` byte-for-byte. (`compute_recall_event_id()` in `queries/recalls.py`)

2. **Integration — `tests/integration/`, seeded `postgres:16` service container.** `httpx.AsyncClient` over `ASGITransport` drives the FastAPI lifespan in-process. The single overridable DB seam is `deps.get_conn`; the fixture overrides it to point at the seeded engine. The seed file `tests/fixtures/seed_gold.sql` is the **living documentation of the mart column contract**: it declares DDL matching the three serving marts' served-column subsets with the exact indexes the API depends on (`UNIQUE(recall_event_id)`, `GIN(search_vector)`, `GIN(recall_product_upcs)`), and seeds 12–16 rows covering every edge case (tri-state NULL, NULL-array coercion, FTS hit/miss, UPC containment, multi-firm jsonb rollup, cross-source firm sidecars). `search_vector` is built with real `to_tsvector('english', ...)` so FTS rank matches production. (`project_scope/build/05-testing-and-ci-plan.md §2-5`)

3. **Contract — `tests/contract/`, no DB for snapshot; DB for conformance.** Two checks:
   - **Snapshot**: `export_openapi.render()` output must be byte-identical to the committed `openapi.json`. Drift fails CI immediately. (`render()` in `export_openapi.py`; the OpenAPI drift step in `ci.yml`)
   - **Response conformance**: selected integration responses are validated against the named component schema pulled from the live-generated OpenAPI spec via `jsonschema`. Guards that `response_model` is set and correct without relying solely on FastAPI's serialization.

4. **CI gate sequence** (`.github/workflows/ci.yml`): the gate runs in the sequence documented in [development.md (quality gate section)](../development.md#quality-gate), minus `dbt parse` and the Neon-branch e2e, plus the OpenAPI drift step. (the gate steps in `.github/workflows/ci.yml`)

5. **`TEST_DB_PROVIDER` defaults to `local`** (reads `TEST_DATABASE_URL` from the CI postgres service container). The Neon-branch path is preserved behind `TEST_DB_PROVIDER=neon` for optional smoke; it is off by default because the gold marts have no pipeline deps to reproduce on a branch and a service container needs no Neon secrets. (`project_scope/build/05-testing-and-ci-plan.md §3, §11`)

6. **Schemathesis property fuzz** ships as a non-gating, `continue-on-error: true` optional job; promoted to gating once stable.

---

## Consequences

**Benefits:**

- Query-builder unit tests prove parameterization (no SQL injection vectors) without a DB round-trip and run in milliseconds.
- A model field rename, response_model optionality flip, or OpenAPI description edit that drifts the snapshot fails CI loudly via the `--check` step — not silently in a consumer.
- `seed_gold.sql` doubles as executable documentation of the exact mart column contract and index assumptions the API depends on; a mart column rename or index drop is caught at the integration layer before it reaches production.
- `deps.get_conn` as the single overridable seam keeps integration tests isolated from real Neon without mocking SQLAlchemy internals.
- The 85% floor covers unit + integration combined in one invocation, matching the pipeline's measurement methodology.

**Accepted costs:**

- The `seed_gold.sql` cassette must be updated whenever the API adds a new column projection or mart-side column is renamed; it is a manually maintained artifact, not auto-generated from the pipeline's DDL.
- `export_openapi.py` must not connect to the DB at import time (engine is created in the lifespan, not at module import) — if that invariant breaks, the OpenAPI drift CI step would require a live DB to run. (`generate()` in `export_openapi.py`)
- The EXPLAIN caveat test (asserting a Sort node exists for unfiltered `ORDER BY published_at DESC`) is a documentation-as-code sentinel, not a hard performance gate; on a 12-row seed the planner always sorts regardless of indexes. It is intentionally fragile in the direction of "flip this assertion when the `published_at` index lands."
- Testcontainers (`testcontainers[postgres]`) is a dev dependency but is not exercised in CI — CI uses the GitHub Actions `postgres:16` service container (already provisioned before pytest starts), so `TEST_DATABASE_URL` is set and `TEST_DB_PROVIDER=local` skips the testcontainer spin-up. Testcontainers is the local-development alternative when the developer has Docker but no running Postgres.
