# 05 — Testing & CI Plan (recalls-api)

> **⚠️ Post-apply reconciliation (2026-06-19, `feature/api-audit`).** The API **response** contract was narrowed *after* this plan was written. The provenance apply **pruned six observability fields** from the response models (`is_currently_active`, `was_ever_retracted`, `first_seen_at`, `last_seen_at`, `edit_count`, `edit_event_count`; **kept** `has_been_edited`) and **dropped the all-null per-product `ProductSearchHit.upc`** field. The seed-table DDL and `INSERT` column lists below still include these columns **on purpose** — the seed mirrors the gold marts, which keep them — but the **expected-response** model dicts (e.g. those asserting `edit_event_count`) are **pre-prune**. Also note the FDA fixture classification was corrected to source-native `2` (FDA never emits `Class I`). Current expectations live in `tests/` + [`openapi.json`](../../openapi.json).

> **Hardened spec.** This doc tells the build session exactly how to test and gate the read-only
> serving API. It mirrors the house gate verbatim from pipeline **ADR 0015** (testing strategy) and
> **ADR 0018** (CI posture), adapted for an API repo that owns **no schema and no dbt** (so: no
> `dbt parse`, no Neon-branch e2e by default).
>
> **Cross-refs:** Pydantic response models → **doc 03** (API contract); modules under test
> (`main.py`, `db.py`, `settings.py`, `pagination.py`, `queries/*.py`, `models/*.py`,
> `errors.py`, the `/health` routes) → **doc 04** (implementation); deploy/ops (Fly.io, cold-start
> 503, cache headers) → **doc 06**; gold-layer recommendations → **doc 07**; commit plan → **doc 08**.
> Schema facts (columns/types/null/index) come from **doc 01**; locked decisions from **doc 02**.
> This doc does **not** redefine models or query modules — it references them by name.

---

## 0. Principles inherited from the house (do not re-litigate)

| Principle | Source | How this doc applies it |
|---|---|---|
| 85% line-coverage floor on `src/`, enforced in CI | ADR 0015 "Coverage target" | `--cov-fail-under=85`; explicit `.coveragerc` exclusions, reviewed in PR |
| Determinism over reality, but not mocked into uselessness | ADR 0015 Context | Unit = no DB; integration = **real** Postgres (service container), not a mocked session |
| No test ever touches prod Neon | ADR 0015 "Integration database strategy" | Integration DB is a CI **service container** seeded by `seed_gold.sql`; Neon-branch path stays available but **off by default** for this repo |
| Swappable test-DB provider seam | ADR 0015 `test_db_url` fixture | Keep the `test_db_url` session fixture; default provider = `local` (DSN from env), with the Neon path preserved for optional smoke |
| A test earns its place by catching an articulable bug class | ADR 0015 Context | Every test below names the bug it catches; no column-per-column coverage trophies |
| CI gate: ruff check → ruff format --check → pyright → pytest(unit+integration) → `pre-commit run --all-files` | ADR 0018 §1, §3 | Same sequence; **drop** `dbt parse` and the Neon-branch e2e (API repo has neither); **add** an OpenAPI-drift check job (ADR 0024 §4) |
| Pre-commit = defense-in-depth, also run in CI | ADR 0018 §3 | `pre-commit run --all-files` is the last gate step; hooks trimmed to the API repo's relevant subset |
| Branch protection requires the PR-check workflow to pass | ADR 0018 §4 | The single `ci.yml` workflow is the required status check |

**Tool versions** mirror the pipeline `pyproject.toml` at the pinned commit: Python `>=3.12`,
`pytest>=9,<10`, `pytest-cov>=7.1,<8`, `ruff>=0.15,<1`, `pyright>=1.1.410,<2`,
`sqlalchemy>=2.0.50,<3`, `httpx>=0.27,<1`. Add (API-repo specific): `pytest-asyncio` (async test
support; the pipeline is sync-tested so this is new here), `asgi-lifespan` is **not** needed
(`httpx.ASGITransport` drives lifespan via the app), `hypothesis>=6` (cursor property test),
`jsonschema>=4` (response-schema conformance), and optionally `schemathesis>=3` (property fuzz,
non-gating). Drop the pipeline-only deps: `pytest-vcr`, `respx`/`responses` (no outbound HTTP),
and all dbt tooling.

---

## 1. The three test layers — what each owns

| Layer | Dir | DB? | Owns (the bug class it catches) | ~Speed |
|---|---|---|---|---|
| **Unit** | `tests/unit/` | **No** | Pure logic: keyset cursor codec round-trip + tamper rejection, query-builder *compiled SQL + bound params* per filter combo, Pydantic null→`[]`/`{}` coercion + tri-state `is_active`, the `recall_event_id = md5(...)` derivation, source-enum validation, error-envelope shape. | ms |
| **Integration** | `tests/integration/` | **Yes** (seeded Postgres) | Real wire behavior end-to-end through `httpx.ASGITransport`: filters return the right rows, keyset paging walks the seed set, **FTS actually matches** (`websearch_to_tsquery` + GIN), UPC `recall_product_upcs` containment, detail md5 lookup hits `UNIQUE(recall_event_id)`, 404/422 envelopes, `/health` + `/health/db`, cache headers. | <1s/test |
| **Contract** | `tests/contract/` | No (snapshot) + Yes (conformance) | The published surface: committed `openapi.json` is byte-identical to what the live app generates (drift = fail); every integration response validates against the schema FastAPI emits; optional Schemathesis fuzz. | ms–s |

**Layer boundaries (decisive):**

- **Unit never imports `db.py`'s engine.** Query-builder tests assert against
  SQLAlchemy Core `Select` objects via `.compile(dialect=asyncpg_dialect, compile_kwargs={"literal_binds": False})`
  — string SQL + `compiled.params`. No connection. This is the layer that proves the SQL the build
  session writes in doc 04's `queries/*.py` is *exactly* the SQL intended, with parameters bound (not
  interpolated) — the CLAUDE.md "never string interpolation" gate, testable offline.
- **Integration owns everything that depends on Postgres semantics** the ORM-less query builder cannot
  fake: GIN/`tsvector` FTS ranking, `jsonb` containment (`@>`), `text[]` array round-trip, `md5()`
  index hit, tri-state `is_active` filter behavior (CPSC/NHTSA `NULL` rows excluded by `is_active=true`).
- **Contract owns the OpenAPI snapshot** so a field rename in a doc-03 model fails CI loudly (ADR 0024
  §4: "FastAPI generator is source of truth; committed `openapi.json` snapshot = contract-test fixture;
  drift = fail").

---

## 2. `seed_gold.sql` — the integration cassette

This is the **only** schema the integration DB has: three stand-in tables matching the three serving
marts' *served columns* (doc 01 Marts 1/2/3), with the **exact indexes the API relies on** — most
critically the `GIN(search_vector)` so FTS runs, the `UNIQUE(recall_event_id)` so the md5 detail path
is an index hit, and the `tsvector` column populated by a real `to_tsvector('english', ...)` so
`websearch_to_tsquery` matches the same way prod does.

> **Why stand-in DDL, not the real mart DDL?** The marts are `materialized='table'` with no committed
> DDL file (doc 01 "Type provenance rule"); the API repo owns no migrations. We hand-author the minimal
> served subset. We deliberately seed only the columns the API selects (doc 03/04 projections) plus the
> indexes the query plans assume — not the full wide mart. Types follow doc 01: `jsonb` for
> arrays/objects, `tsvector` for `search_vector`, `text[]` for the geo arrays, `timestamptz` for dates,
> `boolean` for tri-state flags (so `NULL` is representable).

### 2.1 DDL (committed at `tests/fixtures/seed_gold.sql`)

```sql
-- =====================================================================
-- seed_gold.sql — integration cassette for recalls-api
-- Stand-in for the 3 serving marts at pipeline commit 39dcbda.
-- Served-column subset + the exact indexes the API depends on.
-- Idempotent: safe to re-run against a fresh service-container DB.
-- =====================================================================
BEGIN;

DROP TABLE IF EXISTS mart_product_search CASCADE;
DROP TABLE IF EXISTS mart_firm_profile   CASCADE;
DROP TABLE IF EXISTS mart_recall_summary CASCADE;

-- ---- Mart 1: mart_recall_summary  (GET /recalls list + detail) -------
CREATE TABLE mart_recall_summary (
    recall_event_id          text        NOT NULL,
    source                   text        NOT NULL,
    source_recall_id         text        NOT NULL,
    title                    text,
    recall_reason            text,
    url                      text,
    announced_at             timestamptz,            -- NULL by design (~20 FDA)
    published_at             timestamptz NOT NULL,   -- sort/filter key
    classification           text,                   -- source-native, btree
    risk_level               text,                   -- USDA-only
    lifecycle_status         text,
    is_active                boolean,                -- TRI-STATE: NULL for CPSC/NHTSA
    reason_category          text,
    distribution_scope       text        NOT NULL,
    distribution_states      text,                   -- SCALAR string (not array!)
    distribution_state_codes text[],                 -- NULL = no rda row
    distribution_country_codes text[],
    hazards                  jsonb,                  -- opaque jsonb
    product_upcs             jsonb,                  -- recall-level UPC array
    corrective_action        text,
    consequence_of_defect    text,
    primary_firm_name        text,
    firm_count               bigint      NOT NULL DEFAULT 0,
    firms                    jsonb       NOT NULL DEFAULT '[]'::jsonb,
    product_count            bigint      NOT NULL DEFAULT 0,
    product_names            jsonb,                  -- NOT coalesced -> NULL -> API []
    models                   jsonb,                  -- NOT coalesced -> []
    hins                     jsonb,                  -- NOT coalesced -> []
    first_seen_at            timestamptz,
    last_seen_at             timestamptz,
    edit_count               integer,
    is_currently_active      boolean,                -- USDA+NHTSA only -> None
    was_ever_retracted       boolean,                -- USDA+NHTSA only -> None
    edit_event_count         bigint      NOT NULL DEFAULT 0,
    has_been_edited          boolean     NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX mrs_recall_event_id_ux ON mart_recall_summary (recall_event_id);
CREATE INDEX mrs_source_published_ix       ON mart_recall_summary (source, published_at);
CREATE INDEX mrs_is_active_ix              ON mart_recall_summary (is_active);
CREATE INDEX mrs_classification_ix         ON mart_recall_summary (classification);
-- NOTE: deliberately NO standalone published_at index (doc 01) -> an unfiltered
-- ORDER BY published_at DESC is a full sort. We assert this in an EXPLAIN test (3.5).

-- ---- Mart 2: mart_product_search  (GET /products/search) -------------
CREATE TABLE mart_product_search (
    recall_product_id   text        NOT NULL,
    recall_event_id     text        NOT NULL,
    source              text        NOT NULL,
    source_recall_id    text        NOT NULL,
    product_name        text,
    product_description text,
    model               text,                       -- btree (exact id lookup)
    type                text,
    model_year          text,                       -- FLAGGED int|text -> text here
    hin                 text,                       -- btree (USCG Hull ID)
    upc                 text,                       -- ALL NULL today (do not seed non-null)
    recall_title        text,
    classification      text,
    risk_level          text,
    published_at        timestamptz NOT NULL,
    url                 text,
    is_active           boolean,
    firm_name           text,
    recall_product_upcs jsonb,                      -- recall-level UPC array (containment path)
    search_vector       tsvector    NOT NULL        -- GIN; built by to_tsvector below
);
CREATE UNIQUE INDEX mps_recall_product_id_ux ON mart_product_search (recall_product_id);
CREATE INDEX mps_recall_event_id_ix          ON mart_product_search (recall_event_id);
CREATE INDEX mps_hin_ix                       ON mart_product_search (hin);
CREATE INDEX mps_model_ix                     ON mart_product_search (model);
CREATE INDEX mps_upc_ix                       ON mart_product_search (upc);
CREATE INDEX mps_search_vector_gin           ON mart_product_search USING gin (search_vector);

-- ---- Mart 3: mart_firm_profile  (GET /firms/{id}) --------------------
CREATE TABLE mart_firm_profile (
    firm_id                  text   NOT NULL,
    canonical_name           text   NOT NULL,
    normalized_name          text   NOT NULL,
    observed_names           jsonb,
    observed_company_ids     jsonb,
    alternate_names          jsonb,
    total_recalls            bigint NOT NULL DEFAULT 0,
    active_recalls           bigint NOT NULL DEFAULT 0,
    first_recall_at          timestamptz,           -- NOT coalesced -> None
    last_recall_at           timestamptz,
    roles                    jsonb,                 -- NOT coalesced -> []
    recalls_by_source        jsonb,                 -- NOT coalesced -> {}
    distinct_products        numeric NOT NULL DEFAULT 0,  -- integer-valued
    firm_usda_attributes     jsonb,                 -- USDA sidecar (R5 source-aligned name)
    firm_uscg_attributes     jsonb,                 -- USCG sidecar (R5 source-aligned name)
    firm_fda_attributes      jsonb                  -- FDA  sidecar (R5 source-aligned name)
);
CREATE UNIQUE INDEX mfp_firm_id_ux        ON mart_firm_profile (firm_id);
CREATE INDEX        mfp_normalized_name_ix ON mart_firm_profile (normalized_name);
```

### 2.2 Seed rows — the coverage matrix

Every row below exists to exercise a specific edge. `recall_event_id` is the **real md5** so the
detail-endpoint test can compute it the same way: `md5('CPSC|24-001')` etc. (use Postgres `md5()` in
the INSERT so the test and the seed agree byte-for-byte). `search_vector` is built with a real
`to_tsvector('english', ...)` so FTS ranking matches prod.

| # | Mart | Row identity | Edge it covers |
|---|---|---|---|
| R1 | recall_summary | CPSC `24-001`, `is_active=NULL` | **Tri-state**: excluded by `?is_active=true`, included unfiltered |
| R2 | recall_summary | FDA `F-1001`, `is_active=true`, `classification='2'` | Active recall; classification source-native equality filter (FDA emits `2`, never `Class I`) |
| R3 | recall_summary | USDA `065-2024`, `is_active=false`, `was_ever_retracted=true`, `is_currently_active=false` | **Retracted/inactive**; tri-state flags non-NULL |
| R4 | recall_summary | FDA `F-1002`, `product_names/models/hins = NULL` | **NULL-array** row → API must coerce to `[]` |
| R5 | recall_summary | NHTSA `25V-100`, `firms`=2-element jsonb, `firm_count=2` | **Multi-firm jsonb rollup**; `announced_at=NULL` ok |
| R6 | recall_summary | USDA `065-2024` (=R3) carries `product_upcs='["012345678905"]'` | **Recall-level-UPC** recall (containment target) |
| R7 | recall_summary | USCG `BUC-9` and NHTSA `25V-100` (=R5) | parents for the HIN / model product rows |
| P1 | product_search | USCG product, `hin='ABC12345D404'`, `model=NULL` | **USCG HIN** exact btree lookup |
| P2 | product_search | NHTSA product, `model='CR-V'`, `hin=NULL` | **NHTSA model** exact btree lookup |
| P3 | product_search | FDA product, name "Acme Peanut Butter 16oz", `recall_product_upcs='["012345678905"]'`, `upc=NULL` | **FTS hit** ("peanut butter") + **UPC containment** + proves `upc` col is null |
| P4 | product_search | FDA product, name "Garden Hose Reel" | **FTS miss** for "peanut butter" (negative control) |
| F1 | firm_profile | Firm "Acme Foods", `recalls_by_source='{"FDA":3,"USDA":1}'`, all 3 sidecars non-null | **Cross-source** firm + populated `establishment/manufacturer/fda` sidecars |
| F2 | firm_profile | Firm "Lonely LLC", `roles=NULL`, `recalls_by_source=NULL`, `first/last_recall_at=NULL`, sidecars NULL | **Null→[]/{}/None** firm (zero matched recalls) |

> The build session should write the INSERTs inline in `seed_gold.sql`. A representative slice (the
> two load-bearing tricks — `md5()` event ids and `to_tsvector` vectors — shown so they are not
> guessed):

```sql
-- R2: active FDA recall, classification '2' (FDA source-native; FDA never emits Roman Class I)
INSERT INTO mart_recall_summary
  (recall_event_id, source, source_recall_id, title, published_at, announced_at,
   classification, is_active, distribution_scope, firm_count, firms, product_count,
   product_names, edit_event_count, has_been_edited)
VALUES
  (md5('FDA|F-1001'), 'FDA', 'F-1001', 'Acme Peanut Butter recall',
   '2026-05-01T00:00:00Z', '2026-04-29T00:00:00Z', '2', true, 'Nationwide',
   1, '[{"firm_id":"acmefoods","name":"Acme Foods","role":"establishment","match_confidence":"fei_exact"}]'::jsonb,
   1, '["Acme Peanut Butter 16oz"]'::jsonb, 0, false);

-- R4: NULL-array FDA recall (product_names/models/hins NULL on purpose)
INSERT INTO mart_recall_summary
  (recall_event_id, source, source_recall_id, title, published_at, distribution_scope,
   is_active, firm_count, firms, product_count, edit_event_count, has_been_edited,
   product_names, models, hins)
VALUES
  (md5('FDA|F-1002'), 'FDA', 'F-1002', 'Unspecified product action',
   '2026-05-02T00:00:00Z', 'Unspecified', false, 0, '[]'::jsonb, 0, 0, false,
   NULL, NULL, NULL);

-- R1: CPSC tri-state is_active = NULL
INSERT INTO mart_recall_summary
  (recall_event_id, source, source_recall_id, title, published_at, distribution_scope,
   is_active, classification, firm_count, firms, product_count, edit_event_count, has_been_edited)
VALUES
  (md5('CPSC|24-001'), 'CPSC', '24-001', 'CPSC widget recall',
   '2026-05-03T00:00:00Z', 'Unspecified', NULL, NULL, 1,
   '[{"firm_id":"widgetco","name":"Widget Co","role":"manufacturer","match_confidence":"exact_name"}]'::jsonb,
   1, 0, false);

-- P3: FTS hit + recall-level UPC containment; product-grain upc stays NULL
INSERT INTO mart_product_search
  (recall_product_id, recall_event_id, source, source_recall_id, product_name,
   product_description, recall_title, firm_name, published_at, upc, recall_product_upcs,
   search_vector)
VALUES
  ('fda-f1001-0', md5('FDA|F-1001'), 'FDA', 'F-1001', 'Acme Peanut Butter 16oz',
   'Creamy peanut butter jar', 'Acme Peanut Butter recall', 'Acme Foods',
   '2026-05-01T00:00:00Z', NULL, '["012345678905"]'::jsonb,
   to_tsvector('english',
     'Acme Peanut Butter 16oz' || ' ' || 'Creamy peanut butter jar' || ' ' ||
     'Acme Peanut Butter recall' || ' ' || 'Acme Foods'));

-- P4: FTS negative control (no 'peanut'/'butter' tokens)
INSERT INTO mart_product_search
  (recall_product_id, recall_event_id, source, source_recall_id, product_name,
   recall_title, published_at, search_vector)
VALUES
  ('fda-f1003-0', md5('FDA|F-1003'), 'FDA', 'F-1003', 'Garden Hose Reel',
   'Garden Hose Reel recall', '2026-05-04T00:00:00Z',
   to_tsvector('english', 'Garden Hose Reel Garden Hose Reel recall'));

-- F2: firm with everything NULL (zero matched recalls)
INSERT INTO mart_firm_profile
  (firm_id, canonical_name, normalized_name, total_recalls, active_recalls,
   distinct_products, roles, recalls_by_source, first_recall_at, last_recall_at)
VALUES
  (md5(upper(trim('Lonely LLC'))), 'Lonely LLC', 'lonely llc', 0, 0, 0,
   NULL, NULL, NULL, NULL);
```

> **Coverage guarantee:** active (R2), retracted/inactive (R3), tri-state NULL (R1), multi-firm rollup
> (R5), NULL-array (R4), USCG HIN (P1), NHTSA model (P2), recall-level UPC (R6/P3), cross-source firm
> (F1), FTS hit (P3) + miss (P4), and the all-`[]`/`{}`/`None` firm (F2) are all present. Keep total
> rows small (~12–16) so the suite stays sub-second and the keyset cursor walk has a deterministic order.

---

## 3. `conftest.py` fixtures

`tests/conftest.py` (shared). Scope choices are deliberate: **session** for the DB URL + seeded
schema (one provision per run), **function** for the engine/connection used by app overrides only
where isolation matters; the app + ASGI client are cheap so they're **function**-scoped for clean
dependency-override teardown.

```python
# tests/conftest.py
from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_SEED_SQL = Path(__file__).parent / "fixtures" / "seed_gold.sql"


# ---- ADR 0015 swappable test_db_url seam -----------------------------------
@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    """Yield an async DSN to a throwaway gold-marts DB (ADR 0015 seam).

    Provider via TEST_DB_PROVIDER:
      - "local" (default for this repo): use TEST_DATABASE_URL (the CI postgres service or a
        local docker compose). Async DSN: postgresql+asyncpg://...
      - "neon": optional smoke against an ephemeral Neon branch (kept for parity; OFF by default).
    NEVER prod Neon.
    """
    provider = os.getenv("TEST_DB_PROVIDER", "local")
    if provider == "local":
        dsn = os.getenv("TEST_DATABASE_URL")
        if not dsn:
            pytest.skip("TEST_DATABASE_URL not set — integration tests require a seeded Postgres")
        yield dsn
    elif provider == "neon":  # pragma: no cover - optional smoke path
        from tests.helpers.neon import provision_branch, teardown_branch

        branch_id, dsn = provision_branch()
        try:
            yield dsn
        finally:
            teardown_branch(branch_id)
    else:
        raise ValueError(f"Unknown TEST_DB_PROVIDER: {provider}")


@pytest_asyncio.fixture(scope="session")
async def seeded_engine(test_db_url: str) -> AsyncIterator[AsyncEngine]:
    """Create the 3 stand-in marts + seed rows once per session, then dispose."""
    engine = create_async_engine(test_db_url, pool_pre_ping=True)
    sql = _SEED_SQL.read_text(encoding="utf-8")
    async with engine.begin() as conn:
        # exec_driver_sql runs the multi-statement script as one batch via asyncpg
        await conn.exec_driver_sql(sql)
    yield engine
    await engine.dispose()


# ---- App under test, wired to the seeded engine ----------------------------
@pytest_asyncio.fixture
async def client(seeded_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """httpx.AsyncClient over ASGITransport (in-process, no socket).

    Overrides doc-04's `get_conn` request dependency so the app reads the seeded DB instead of
    building one from settings. ASGITransport drives FastAPI lifespan, so startup/shutdown (pool
    creation in doc 04) run exactly as in prod — minus the real Neon DSN.
    """
    from collections.abc import AsyncIterator

    from recalls_api import deps  # doc 04: re-exports get_conn as the overridable symbol
    from recalls_api.main import create_app  # doc 04 app factory

    async def _override_get_conn() -> AsyncIterator[sa.Connection]:
        async with seeded_engine.connect() as conn:
            yield conn

    app = create_app()
    app.dependency_overrides[deps.get_conn] = _override_get_conn
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_conn(seeded_engine: AsyncEngine) -> AsyncIterator[sa.Connection]:
    """Raw async connection for tests that assert DB-side behavior directly (EXPLAIN, FTS)."""
    async with seeded_engine.connect() as conn:
        yield conn
```

**Notes the build session must honor:**

- The app factory `create_app()` and the `get_conn` request dependency are **doc 04** deliverables —
  this conftest assumes they exist and are overridable (standard FastAPI `dependency_overrides`).
  `get_conn` (re-exported from `deps.py`) is the single overridable DB seam — the override is the contract.
- `pytest-asyncio` in **auto** mode (`asyncio_mode = "auto"` in `pyproject.toml`) so `async def test_*`
  needs no per-test marker. Set a single event loop policy; do not create nested loops.
- Use `exec_driver_sql` (not `text()`) for the multi-statement seed so asyncpg runs it as a script.
- The `client` fixture is the **only** way integration tests reach the app — no `TestClient`
  (sync) is used; everything is async to match the asyncpg/SQLAlchemy-Core-async stack (doc 02 #2).

---

## 4. Unit tests (no DB)

### 4.1 Query-builder: compiled SQL + bound params (parametrized over filter combos)

The build session's `queries/recalls.py`, `queries/products.py`, `queries/firms.py` (doc 04) build
SQLAlchemy Core `Select` objects. The bug class: a filter silently not applied, a wrong column, or —
the CLAUDE.md cardinal sin — a value string-interpolated instead of bound. We compile the statement
for the asyncpg dialect and assert on the SQL text + `compiled.params`.

```python
# tests/unit/test_query_builder.py
import pytest
from sqlalchemy.dialects.postgresql import asyncpg as pg_asyncpg

from recalls_api.queries.recalls import build_recalls_query  # doc 04

DIALECT = pg_asyncpg.dialect()


def _compile(stmt):
    c = stmt.compile(dialect=DIALECT)
    return str(c), dict(c.params)


@pytest.mark.parametrize(
    "filters, expect_sql_contains, expect_params",
    [
        # source equality -> uses (source, published_at) index path
        ({"source": "FDA"}, ["source ="], {"source_1": "FDA"}),
        # tri-state is_active=true MUST be an "IS true"/"= true" predicate, NOT include NULLs
        ({"is_active": True}, ["is_active"], {"is_active_1": True}),
        # classification is a FREE-STRING equality (not an enum), parameter-bound
        ({"classification": "Class I"}, ["classification ="], {"classification_1": "Class I"}),
        # combined filters AND together
        ({"source": "USDA", "is_active": False},
         ["source =", "is_active"], {"source_1": "USDA", "is_active_1": False}),
        # no filters -> no WHERE on source/is_active; still ORDER BY published_at DESC, recall_event_id
        ({}, ["order by", "published_at"], {}),
    ],
)
def test_recalls_query_compiles(filters, expect_sql_contains, expect_params):
    stmt = build_recalls_query(**filters, limit=25)  # limit+1 handled inside per doc 04
    sql, params = _compile(stmt)
    low = sql.lower()
    for frag in expect_sql_contains:
        assert frag.lower() in low
    for k, v in expect_params.items():
        assert params[k] == v
    # No value ever appears as a literal in the SQL (injection guard / CLAUDE.md)
    for v in filters.values():
        if isinstance(v, str):
            assert v not in sql  # bound, not interpolated
```

Mirror for products (`q`/`hin`/`model`/`upc` routing — assert FTS path uses `websearch_to_tsquery`
and the bound `:q`; assert UPC routes to a `recall_product_upcs @> ...` containment, never the
all-null `upc` column) and for firms (point-lookup `firm_id = :firm_id`). The 422 "require at least
one of `q|hin|model|upc`" rule (doc 02 #5) is unit-tested at the validation layer (a builder called
with all-None raises the API's `InvalidParameter`/422 error type from doc 04's `errors.py`).

### 4.2 Pagination codec: round-trip + hypothesis property + tamper → `BadCursor`

`pagination.py` (doc 04) is pure: a `Cursor` class with classmethods `Cursor.encode(...)` /
`Cursor.decode(...)` (base64url of the JSON last-sort tuple), raising `BadCursor` on garbage. The bug
class: a cursor that doesn't round-trip (drops a deep page) or a tampered/garbage cursor that 500s
instead of **400**-ing (`BadCursor` → 400, decision 5).

```python
# tests/unit/test_pagination.py
import datetime as dt

import pytest
from hypothesis import given, strategies as st

from recalls_api.errors import BadCursor       # doc 04: BadCursor lives in errors.py (status 400)
from recalls_api.pagination import Cursor       # doc 04: Cursor.encode / Cursor.decode codec

# sort tuples are (published_at: datetime, recall_event_id: str) for /recalls,
# or (rank: float, recall_product_id: str) for FTS, or (published_at, recall_product_id).
sort_tuples = st.tuples(
    st.datetimes(min_value=dt.datetime(1940, 1, 1), max_value=dt.datetime(2030, 1, 1)),
    st.text(min_size=1, max_size=64),
)


@given(sort_tuples)
def test_cursor_round_trip(tpl):
    # values are JSON-encoded, so datetimes round-trip as their ISO strings (see doc 04 codec).
    values = (tpl[0].isoformat(), tpl[1])
    assert Cursor.decode(Cursor(values=values).encode()).values == values


@pytest.mark.parametrize("bad", ["", "!!!notbase64!!!", "YWJj", "Zm9vYmFy", "{}", "[1,2,3,4,5]"])
def test_tampered_cursor_raises(bad):
    with pytest.raises(BadCursor):
        Cursor.decode(bad)
```

The route layer turns `BadCursor` into a **400** (malformed/tampered `cursor` param) via doc 04's
exception handler — assert that mapping in an integration test (3.x) so the error envelope + `request_id`
echo is covered. (`InvalidParameter` stays 422; only the bad-cursor case is 400 — decision 5.)

### 4.3 Pydantic null→`[]`/`{}` coercion + tri-state (doc 03 models)

The bug class: a `NULL` jsonb array surfacing as `null` in JSON instead of `[]`, or `is_active`
collapsing tri-state to `false`. Construct doc-03 models from raw mart-shaped dicts (mimicking a DB
row) and assert the serialized shape.

```python
# tests/unit/test_model_coercion.py
from recalls_api.models.recalls import RecallSummary   # doc 03
from recalls_api.models.firms import FirmProfile        # doc 03


def test_null_arrays_coerce_to_empty_list():
    # mart row with product_names/models/hins = None (the R4 shape)
    m = RecallSummary.model_validate(
        {"recall_event_id": "x", "source": "FDA", "source_recall_id": "F-1002",
         "published_at": "2026-05-02T00:00:00Z", "distribution_scope": "Unspecified",
         "is_active": False, "firm_count": 0, "firms": [], "product_count": 0,
         "edit_event_count": 0, "has_been_edited": False,
         "product_names": None, "models": None, "hins": None}
    )
    assert m.product_names == [] and m.models == [] and m.hins == []


def test_is_active_is_tristate():
    m = RecallSummary.model_validate({  # CPSC -> NULL
        "recall_event_id": "y", "source": "CPSC", "source_recall_id": "24-001",
        "published_at": "2026-05-03T00:00:00Z", "distribution_scope": "Unspecified",
        "is_active": None, "firm_count": 0, "firms": [], "product_count": 0,
        "edit_event_count": 0, "has_been_edited": False})
    assert m.is_active is None  # NOT False


def test_firm_profile_defaults():
    p = FirmProfile.model_validate({  # F2: everything null
        "firm_id": "z", "canonical_name": "Lonely LLC", "normalized_name": "lonely llc",
        "total_recalls": 0, "active_recalls": 0, "distinct_products": 0,
        "roles": None, "recalls_by_source": None, "first_recall_at": None,
        "last_recall_at": None, "firm_usda_attributes": None,
        "firm_uscg_attributes": None, "firm_fda_attributes": None})
    assert p.roles == [] and p.recalls_by_source == {}
    assert p.firm_usda_attributes == [] and p.firm_uscg_attributes == []
    assert p.firm_fda_attributes == [] and p.first_recall_at is None
```

> The default mechanism (doc 02 #8): `Field(default_factory=list)` / `Field(default_factory=dict)`
> plus a `field_validator(mode="before")` that maps incoming `None` → the empty container (Pydantic v2
> `default_factory` fires on *absent* keys, not on explicit `None`, so the before-validator is required
> for DB `NULL`). These unit tests are exactly what prove that validator exists and works.

### 4.4 `recall_event_id` derivation + source enum

```python
# tests/unit/test_event_id.py
import hashlib
import pytest
from recalls_api.models.common import Source     # doc 03 StrEnum
from recalls_api.queries.recalls import recall_event_id  # doc 04 md5 helper

@pytest.mark.parametrize("source,rid", [("CPSC", "24-001"), ("FDA", "F-1001"), ("USCG", "BUC-9")])
def test_event_id_matches_pg_md5(source, rid):
    expected = hashlib.md5(f"{source}|{rid}".encode()).hexdigest()
    assert recall_event_id(source, rid) == expected  # source already uppercase

def test_source_enum_is_closed_uppercase():
    assert {s.value for s in Source} == {"CPSC", "FDA", "USDA", "NHTSA", "USCG"}
    with pytest.raises(ValueError):
        Source("cpsc")          # the enum itself only accepts uppercase values
    # but the {source} path param is a str the handler uppercases first, so a lowercase
    # public URL (e.g. /recalls/cpsc/24-001) is accepted, not rejected (decision 10):
    assert Source("cpsc".upper()) is Source.CPSC
```

---

## 5. Integration tests (httpx ASGITransport over seeded Postgres)

These use the `client` fixture. The bug class: real Postgres semantics the unit layer can't fake.
Group by endpoint; each assertion ties to a seed row from §2.2.

| Test | Seed rows | Asserts |
|---|---|---|
| `test_recalls_list_default_order` | all R* | 200; rows ordered `published_at DESC`; `is_active` is `true`/`false`/`null` preserved; null-array R4 returns `product_names: []` |
| `test_recalls_filter_is_active_true_excludes_null` | R1, R2 | `?is_active=true` returns R2, **not** the CPSC `NULL` R1 (tri-state honesty) |
| `test_recalls_filter_classification` | R2, R3 | `?classification=2` returns the FDA R2 row and `?classification=Class I` the USDA R3 row (FDA emits `2`, not `Class I`); free-string source-native equality |
| `test_recalls_keyset_paging_walks_set` | all R* | `?limit=2` → `has_next=true` + `next_cursor`; following the cursor yields the next page with **no overlap, no gap**; final page `has_next=false` |
| `test_recalls_with_total_opt_in` | all R* | default response omits `total`; `?with_total=true` includes an accurate COUNT |
| `test_recalls_bad_cursor_400` | — | `?cursor=garbage` → 400 envelope with `request_id`, not 500 (BadCursor=400, decision 5) |
| `test_recall_detail_md5_hit` | R2 | `GET /recalls/FDA/F-1001` → 200; equals `md5('FDA|F-1001')` row. Source is accepted case-insensitively: `GET /recalls/fda/F-1001` resolves the **same** row (path param is `str`, uppercased before hashing — decision 10), NOT a 404/422 |
| `test_recall_detail_404` | — | unknown `(source, recall_id)` → 404 envelope |
| `test_products_search_fts_hit_and_miss` | P3, P4 | `?q=peanut butter` returns P3, **not** P4; results ranked; `websearch_to_tsquery` never raises on punctuation (`?q=peanut, butter!`) |
| `test_products_search_hin_exact` | P1 | `?hin=ABC12345D404` → 200 with the USCG product |
| `test_products_search_model_exact` | P2 | `?model=CR-V` → 200 with the NHTSA product |
| `test_products_search_upc_containment` | P3 | `?upc=012345678905` routes to `recall_product_upcs @>` and returns P3, **never** matches the all-null `upc` column; response carries the `upc_is_recall_level` note |
| `test_products_search_requires_a_param_422` | — | no `q|hin|model|upc` → 422 |
| `test_firms_cross_source_profile` | F1 | `GET /firms/{md5}` → 200; `recalls_by_source == {"FDA":3,"USDA":1}`; the 3 sidecars present with their **verbatim** field names and per-source sub-model shapes |
| `test_firms_empty_defaults` | F2 | `roles == []`, `recalls_by_source == {}`, sidecars `== []`, `first_recall_at is None` |
| `test_firms_404` | — | unknown `firm_id` → 404 |
| `test_health` | — | `GET /health` → 200, no DB hit (liveness) |
| `test_health_db` | — | `GET /health/db` → 200 after `SELECT 1`; the cold-DB → 503+`Retry-After` path is doc 06's concern, exercised by a fault-injection test that overrides the engine to raise on connect |
| `test_cache_headers` | R2 | list/detail responses carry `Cache-Control: max-age=...` + `ETag`/`Last-Modified` keyed off the rebuild anchor (doc 06); a conditional `If-None-Match` → 304 |

### 5.x EXPLAIN guard for the unfiltered-sort caveat (the doc-01 blocker)

One targeted test documents the most important index caveat in executable form using the `db_conn`
fixture: an unfiltered `ORDER BY published_at DESC` is a **full sort** (no standalone index), but with
`?source=` it is index-backed. This is a regression sentinel for doc 07's gold-layer recommendation
(adding a `published_at` index later should flip the assertion).

```python
# tests/integration/test_index_caveat.py
import sqlalchemy as sa

async def test_unfiltered_published_at_sort_is_full_sort(db_conn):
    plan = (await db_conn.exec_driver_sql(
        "EXPLAIN SELECT recall_event_id FROM mart_recall_summary "
        "ORDER BY published_at DESC, recall_event_id LIMIT 26"
    )).scalars().all()
    text = "\n".join(plan).lower()
    assert "sort" in text  # no standalone published_at index -> Sort node (doc 01 caveat)
```

> On a 12-row seed the planner may pick a seq-scan+sort regardless of indexes, so this test asserts
> the *presence of a Sort node*, which is the honest behavior at any scale without a `published_at`
> index. Keep it as documentation-as-code; don't over-assert node types that vary with row counts.

---

## 6. Contract tests

> **🔄 Implemented differently (corrected 2026-06-17).** The shipped
> `src/recalls_api/export_openapi.py` supersedes the stdout-based sketches in this section: it
> **writes `openapi.json` directly** (it does not print the spec to stdout) and exposes a **`--check`**
> flag that does the drift comparison internally. The real commands are
> `uv run python -m recalls_api.export_openapi` to regenerate and
> `uv run python -m recalls_api.export_openapi --check` to verify — **never** the `> openapi.json` /
> `> /tmp/…` redirect forms shown below in §6.1–§6.2, the CI drift step, and the `openapi-snapshot`
> pre-commit hook (redirecting would capture the script's `wrote …` stdout line and corrupt the file).
> The live CI step (`.github/workflows/ci.yml`) and the `openapi-drift` pre-commit hook
> (`.pre-commit-config.yaml`) both use `--check`. Authoritative home:
> [ADR 0010](../../documentation/decisions/0010-openapi-committed-snapshot-drift-contract.md) and
> [development.md](../../documentation/development.md). The sketches below are retained as historical
> design context.

### 6.1 `src/recalls_api/export_openapi.py` — generator is source of truth (ADR 0024 §4)

A **module under the package** (not a `scripts/` script), invoked as
`python -m recalls_api.export_openapi > openapi.json` — consistent with doc 08's commit-plan gate.
It writes the generated spec to **stdout**; the caller redirects to the file.

```python
# src/recalls_api/export_openapi.py
"""Print the app's generated OpenAPI doc to stdout.

Run by the maintainer after any intentional surface change:
    uv run python -m recalls_api.export_openapi > openapi.json
CI runs it to a temp file and diffs against the committed snapshot (drift = fail)."""
from __future__ import annotations

import json
import sys

from recalls_api.main import create_app  # doc 04


def render() -> dict:
    return create_app().openapi()


def main() -> int:
    sys.stdout.write(json.dumps(render(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`sort_keys=True` + `indent=2` make the snapshot deterministic and the diff readable. Commit
`openapi.json` at repo root; it is the published contract artifact.

### 6.2 Snapshot diff (drift = fail)

```python
# tests/contract/test_openapi_snapshot.py
import json
from pathlib import Path

from recalls_api.export_openapi import render

SNAPSHOT = Path(__file__).parents[2] / "openapi.json"


def test_openapi_matches_committed_snapshot():
    current = json.loads(json.dumps(render(), indent=2, sort_keys=True))
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert current == committed, (
        "OpenAPI drift: a model/route/param/description changed. "
        "If intentional, run `uv run python -m recalls_api.export_openapi > openapi.json` and commit it."
    )
```

This is what makes any doc-03 model change (a renamed field, a flipped optionality, an edited honest
caveat in the OpenAPI `description`) a **loud CI failure** rather than a silent contract break.

### 6.3 Response-schema conformance

Every integration response should validate against the schema FastAPI emits for that operation. The
cheapest robust form: pull the named component schema out of the generated OpenAPI and validate the
JSON body with `jsonschema`. The bug class: a route returning data the declared response_model
wouldn't accept (e.g., `is_active` as a string, a sidecar with the wrong shape) without FastAPI's own
serialization catching it (it can, but only if `response_model` is set — this guards that it is and is
correct).

```python
# tests/contract/test_response_conformance.py
import jsonschema
import pytest
from recalls_api.export_openapi import render

SPEC = render()


def _schema_for(component: str) -> dict:
    s = dict(SPEC["components"]["schemas"][component])
    s["components"] = {"schemas": SPEC["components"]["schemas"]}  # resolve $ref
    return s


@pytest.mark.parametrize("path, component", [
    ("/recalls/FDA/F-1001", "RecallDetail"),
    ("/firms/{firm_id}", "FirmProfile"),  # firm_id substituted in the test body
])
async def test_response_conforms_to_schema(client, path, component):
    ...  # GET, then jsonschema.validate(body, _schema_for(component))
```

### 6.4 Optional: Schemathesis (non-gating)

Schemathesis can property-fuzz every endpoint from the OpenAPI spec (random params, malformed cursors,
boundary `limit`s) and assert no 500s + schema conformance. Run it as a **separate, non-required** CI
job (`continue-on-error: true` initially) so its flakiness never blocks merge; promote to gating once
stable.

```bash
uv run schemathesis run --base-url http://localhost:8000 --checks all openapi.json
```

(Requires the app served against the seeded DB — only worth it in the integration job; keep it
optional per ADR 0029's "don't over-engineer before earned".)

---

## 7. Coverage

- Floor: **85%** on `src/` (= `recalls_api` package), mirroring ADR 0015. Enforced by
  `--cov-fail-under=85` in CI (the local `addopts` keeps `--cov=recalls_api --cov-report=term-missing`; the
  `--cov-fail-under` is added in the CI invocation so a local quick run isn't blocked).
- `.coveragerc` exclusions are **explicit and PR-reviewed** (ADR 0015): the Neon-branch optional smoke
  path (`pragma: no cover`), defensive `except` branches for unreachable connect errors, and
  `if TYPE_CHECKING:` blocks.
- Integration + unit coverage **combine** (run in one `pytest` invocation over `tests/`) — the 85% is
  measured against the union, exactly as the pipeline does it.

`.coveragerc`:

```ini
[run]
source = recalls_api
branch = true
omit =
    tests/*

[report]
show_missing = true
exclude_lines =
    pragma: no cover
    if TYPE_CHECKING:
    raise NotImplementedError
    \.\.\.
```

---

## 8. `.github/workflows/ci.yml` (full)

Single workflow = the required status check (ADR 0018 §4). Gate sequence mirrors ADR 0018 §1 exactly,
minus `dbt parse` (no dbt) and the Neon-branch e2e (replaced by a seeded **service container** per the
doc 02 reconciliation), plus the OpenAPI-drift check (ADR 0024 §4). Postgres 16 service container is
seeded by `seed_gold.sql` before pytest runs.

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

env:
  # asyncpg DSN to the service container; TEST_DB_PROVIDER=local makes conftest read this.
  TEST_DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/recalls_test
  TEST_DB_PROVIDER: local

jobs:
  ci:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: recalls_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Set up Python 3.12
        run: uv python install 3.12

      - name: Sync deps (locked)
        run: uv sync --frozen --all-extras --dev

      # ---- Lint / format / types (ADR 0018 §1) ----
      - name: Ruff check
        run: uv run ruff check .

      - name: Ruff format --check
        run: uv run ruff format --check .

      - name: Pyright
        run: uv run pyright

      # ---- Seed the service container with the gold-mart cassette ----
      - name: Seed test database
        env:
          PGPASSWORD: postgres
        run: psql -h localhost -U postgres -d recalls_test -v ON_ERROR_STOP=1 -f tests/fixtures/seed_gold.sql

      # ---- Tests: unit + integration + contract, with coverage floor ----
      - name: Pytest (unit + integration + contract)
        run: uv run pytest tests/ --cov=recalls_api --cov-report=term-missing --cov-fail-under=85

      # ---- OpenAPI drift check (ADR 0024 §4) ----
      - name: OpenAPI drift
        run: |
          uv run python -m recalls_api.export_openapi > /tmp/openapi.generated.json
          diff -u openapi.json /tmp/openapi.generated.json \
            || { echo "::error::OpenAPI drift — run 'python -m recalls_api.export_openapi > openapi.json' and commit it"; exit 1; }

      # ---- Defense in depth: all pre-commit hooks (ADR 0018 §3) ----
      - name: Pre-commit (all files)
        run: uv run pre-commit run --all-files
```

**Notes:**

- The integration tests **also** open their own asyncpg connections to the same service container via
  `seeded_engine` (which re-runs `seed_gold.sql` in `exec_driver_sql`). The `psql` seed step is a
  belt-and-suspenders so the OpenAPI/conformance jobs and any `psql`-level smoke see a populated DB;
  if you prefer a single seed path, drop the `psql` step and let `seeded_engine` own it — but keep the
  service container's health check so pytest doesn't race a cold Postgres. **Decision: keep the `psql`
  pre-seed** (it makes the EXPLAIN test and any future `psql` smoke independent of fixture ordering).
- `uv sync --frozen` enforces lockfile reproducibility (ADR 0017) — equivalent to the pipeline's
  `uv-lock-check` intent at install time; the `uv lock --check` pre-commit hook (below) is the diff-time
  guard.
- `timeout-minutes: 10` matches ADR 0018's runtime budget trigger; if it's consistently exceeded,
  split the contract/Schemathesis job out (ADR 0018 "Open for revision").
- **OpenAPI-check job:** kept **inline** as a step (not a separate job) so it shares the synced
  environment and is a hard gate. If a faster PR loop is wanted later, promote it to a parallel job
  that only needs `uv sync` (no DB) since `render()` builds the app without connecting — the app
  factory must not connect to the DB at import/`openapi()` time (doc 04: lazy engine in lifespan, not
  at module import). That is also what lets the contract snapshot test run with **no DB**.

### 8.1 `.pre-commit-config.yaml` (API-repo subset of ADR 0018 §3)

Trim the pipeline's six hooks to those that apply: ruff + ruff-format, pyright, gitleaks (still
useful — the read-only DSN is a secret), and `uv-lock-check`. **Drop** `cassette-secret-scrub` (no
VCR cassettes here) and `check-pydantic-strict` (that hook enforces *bronze ingest* models'
`extra='forbid', strict=True`; the API's *response* models are output-shaping and should be lenient on
extra DB columns, so this hook does not apply — see §9 judgment call). **Add** an `openapi-snapshot`
local hook so drift is caught pre-commit too.

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.16
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/RobertCraigie/pyright-python
    rev: v1.1.410
    hooks:
      - id: pyright

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.0
    hooks:
      - id: gitleaks

  - repo: local
    hooks:
      - id: uv-lock-check
        name: Verify uv.lock matches pyproject.toml
        entry: uv lock --check
        language: system
        pass_filenames: false
        files: ^(pyproject\.toml|uv\.lock)$

      - id: openapi-snapshot
        name: Verify openapi.json matches the app's generated spec
        entry: bash -c 'uv run python -m recalls_api.export_openapi > /tmp/oa.json && diff -q openapi.json /tmp/oa.json'
        language: system
        pass_filenames: false
        files: ^(src/recalls_api/|openapi\.json)
```

---

## 9. `pyproject.toml` test/tooling stanzas (API repo)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--cov=recalls_api --cov-report=term-missing"   # --cov-fail-under=85 added in CI invocation

[tool.ruff]
target-version = "py312"

[tool.pyright]
# match the pipeline's strictness posture; pin via pyproject so CI + pre-commit + local agree
typeCheckingMode = "standard"
pythonVersion = "3.12"
```

`[dependency-groups]` (or `[project.optional-dependencies]`, matching the pipeline's layout): `pytest`,
`pytest-asyncio`, `pytest-cov`, `hypothesis`, `jsonschema`, `ruff`, `pyright`, `pre-commit`, and
optionally `schemathesis`. **No** `pytest-vcr`, `respx`, `responses`, or any dbt package.

---

## 10. Observability hooks under test (ADR 0021 / 0029)

- `request_id` correlation (doc 02 #13, ADR 0021): one integration test asserts the **error envelope**
  echoes a `request_id`, and that a client-supplied `X-Request-ID` is honored (or a UUID minted when
  absent). The bug class: a 500/422 without a correlation id, which makes "operator reads platform
  logs" (ADR 0029) useless.
- **No** Sentry/OTel test surface in v1 (ADR 0029). The named upgrade triggers (sustained failure rate,
  multi-source incident, time-to-detection regression, consumer SLO, volume, second operator) live in
  doc 06's ops section, not in tests. Do not add an observability SaaS test that asserts something the
  v1 stance deliberately omits.

---

## 11. Judgment calls & open items

**Judgment calls (decided here, flagged for the build session):**

1. **Test-DB provider default flipped to `local`.** The pipeline conftest defaults `TEST_DB_PROVIDER`
   to `neon`; this API repo defaults to `local` (the CI service container / `TEST_DATABASE_URL`)
   because the gold marts have no pipeline deps to reproduce on a branch and a service container is
   faster + needs no Neon secrets (doc 02 Testing/CI reconciliation). The Neon path is preserved
   behind `TEST_DB_PROVIDER=neon` for an optional smoke, exactly honoring the ADR 0015 swappable seam.
2. **Dropped `check-pydantic-strict` and `cassette-secret-scrub` pre-commit hooks.** They enforce
   bronze-ingest invariants (strict Pydantic, VCR cassette scrubbing) that have no analog in a
   read-only API with lenient response models and no outbound HTTP. Kept gitleaks (the DSN is still a
   secret) and `uv-lock-check`. Added an `openapi-snapshot` hook.
3. **OpenAPI drift kept as an inline CI step, not a separate job.** Simpler and a hard gate; the doc
   notes the promotion path to a DB-less parallel job once a faster loop is wanted. This assumes doc 04
   builds the engine lazily in lifespan (so `create_app().openapi()` needs no DB) — stated as a
   requirement on doc 04.
4. **EXPLAIN test asserts only "a Sort node exists"** for the unfiltered `published_at` order, not a
   specific plan, because on a tiny seed the planner ignores indexes. It is documentation-as-code for
   the doc-01 caveat and a sentinel for doc 07's potential `published_at` index addition.
5. **`psql` pre-seed step retained** alongside the fixture-level `seeded_engine` seed (belt-and-
   suspenders) so `psql`-level/EXPLAIN paths don't depend on fixture ordering. A single-seed variant is
   noted if the build session prefers it.

**Open items (confirm during build / with the operator):**

- **Dependency-override seam** is `deps.get_conn` (the per-request DB dependency, re-exported from
  `db.py`; decision 6) and the **app factory** signature is `create_app()` — both are doc 04's; this
  conftest overrides `deps.get_conn`.
- **`RecallDetail` vs `RecallSummary` component names** in §6.3 are placeholders for doc 03's actual
  model names; align before writing conformance params.
- **Cache-header anchor** (ETag/Last-Modified keyed off the nightly ~03:00 UTC rebuild) is specified in
  doc 06; the §5 `test_cache_headers` assertion must match doc 06's exact header strategy.
- **Read-only DSN env-var name** (`NEON_DATABASE_URL_RO` vs reusing `NEON_DATABASE_URL`) is an operator
  open item (doc 02 "MUST re-verify"); CI uses `TEST_DATABASE_URL` regardless, so it does not block the
  test plan — but `tests/unit/test_settings.py` (settings fail-loud at boot, doc 02 #10) must use
  whatever name doc 04 settles on.
- **Schemathesis gating.** Ships non-gating (`continue-on-error`); promote once stable per ADR 0029's
  "don't over-engineer before earned."
