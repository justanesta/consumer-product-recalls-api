# 08 — Commit Plan, Prerequisites & Open Questions (recalls-api)

> **Purpose.** The execution map for the build session: what must be true *before* code can ship live,
> the exact phased branch+commit sequence to write the API, the per-branch gates and acceptance
> criteria, the cross-branch dependency order, and the resolved-vs-remaining decision ledger with a
> concrete "how to resolve" for each open item.
>
> **Reads.** Plan §§13–14 (phased commit plan + open questions) and doc `02` "Decisions locked" +
> "MUST re-verify" lists. Schema facts come from doc `01` (the contract). Sibling docs referenced by
> number: **03** API contract, **04** implementation, **05** testing/CI, **06** deploy/ops, **07**
> gold-layer recommendations.
>
> **Provenance for the cross-repo facts below:** pipeline repo `justanesta/consumer-product-recalls`
> @ `feature/pre-go-live-validation`, commit `39dcbda` — same commit as doc `01`. The role pattern is
> read off `migrations/versions/0033_recalls_app_role_posture.py`; the settings pattern off
> `src/config/settings.py`; the observability triggers off `documentation/decisions/0029-*.md`.

---

## 1. Prerequisites (cross-repo) — what must exist before live deploy

This API **owns no schema and no migrations.** Everything it depends on is produced by the pipeline
repo or provisioned by the operator. There is exactly **one hard blocker** for a live deploy; the rest
are soft (the build proceeds against the seeded test container regardless) or are nice-to-haves.

| # | Prerequisite | Owner | Blocking? | Status / how to land it |
|---|---|---|---|---|
| P1 | **Dedicated read-only DB role** (e.g. `recalls_readonly`) + `GRANT SELECT` on the gold marts + `default_transaction_read_only=on`, provisioned in the **pipeline repo** as a migration mirroring `0033` (operator-activated NOLOGIN shell). | Pipeline repo / operator | **HARD BLOCKER for live deploy only** | Doc `07` #2 specifies it. Until it exists the API cannot connect to prod Neon read-only. **Does NOT block local/CI build** (CI uses a throwaway container with its own superuser). See §1.1. |
| P2 | **Confirm the connection env var name, the pooled endpoint, and the exact grants** with the operator. | Operator | Soft (decide before wiring `db.py` against prod) | The build can wire `db.py` against the *seeded container* first; the prod DSN is only needed at deploy. See §1.1 + open item R1. |
| P3 | **Gold rebuild-timestamp surface** (a queryable "last transform completed at" value) so the API can emit correct `ETag` / `Last-Modified` / `Cache-Control` keyed off the nightly ~03:00 UTC rebuild. | Pipeline repo | Soft (unblocks *proper* cache headers) | Doc `07` #6. Without it, the API falls back to a coarse `Cache-Control: max-age` only (no rebuild-pinned validators). Build can ship with the fallback and upgrade later — see `06`. |
| P4 | **NO composite index is needed.** The `(source, source_recall_id)` C0c-dbt index is **dropped** — the detail endpoint computes `recall_event_id = md5(f"{SOURCE_UPPER}\|{recall_id}")` and hits the existing `UNIQUE(recall_event_id)`. | (nobody) | Not a prerequisite | Explicitly **do not** request a pipeline index change. Documented here so the build session does not re-raise it. |
| P5 | Gold marts are stable at commit `39dcbda` (doc `01` is the frozen contract). | Pipeline repo | Already satisfied | Doc `01` is authoritative; the build trusts it over "re-read at build time". |

### 1.1 The read-only role — the one hard blocker, in detail

The existing **`recalls_app`** role (pipeline migration `0033`) is the **pipeline's READ+WRITE** role:
`GRANT SELECT, INSERT, UPDATE ON ALL TABLES` plus `TRUNCATE` on two crosswalk tables and append-only
on `*_rejected`. **The API MUST NOT reuse it** — that would hand a public, unauthenticated read-only
service write credentials to production.

A **new dedicated read-only role** must be provisioned by the pipeline repo / operator, following the
*exact* `0033` posture pattern (it is the proven Neon-safe shape):

- **Create as a NOLOGIN shell via SQL** (not the Neon Console/API/CLI) — a SQL-created role is **not**
  auto-added to `neon_superuser`, so it does **not** inherit `pg_write_all_data`. This is the load-bearing
  reason `0033` creates the role in-migration rather than in the console.
- **Grants:** `GRANT USAGE ON SCHEMA public` + `GRANT SELECT ON ALL TABLES IN SCHEMA public` (or, tighter,
  only the `mart_*` serving tables) + `ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES` so a future
  mart is readable without a re-grant. **No INSERT/UPDATE/DELETE/TRUNCATE.**
- **`ALTER ROLE recalls_readonly SET default_transaction_read_only = on;`** — defense-in-depth; every
  session is read-only even if a future code path tries a write.
- **Operator activates LOGIN out-of-band** (Neon requires a plaintext password in a single statement):
  `ALTER ROLE recalls_readonly LOGIN PASSWORD '<strong pw>';` — the password is **never** committed.

The build session **cannot author this migration** (wrong repo). Its job is to: (a) flag P1 to the
operator at kickoff, (b) wire `db.py` and `settings.py` to *consume* a read-only DSN with the pipeline's
fail-loud `SecretStr` pattern (§1.2), and (c) **not** block local/CI work on it — the CI service
container is a throwaway Postgres the test suite owns outright.

### 1.2 Env var + settings posture (mirror the pipeline)

The pipeline's canonical DB var is **`NEON_DATABASE_URL`** (`src/config/settings.py`:
`neon_database_url: SecretStr`, `pydantic-settings BaseSettings`, no module-level instance →
constructed at call time → **missing var raises `ValidationError` at boot, not a `KeyError`
mid-request**). The API mirrors this with a **read-only variant** to make the posture self-documenting:

```python
# src/recalls_api/settings.py  (skeleton — see doc 04 for the full module)
from __future__ import annotations
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    # Read-only Neon DSN for the dedicated recalls_readonly role. SecretStr => never logged.
    # Naming mirrors the pipeline's NEON_DATABASE_URL; the _RO suffix encodes the role posture.
    neon_database_url_ro: SecretStr
    # pool sizing (cold-start tuned — see locked decision 14 / doc 06)
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_s: int = 300
    db_command_timeout_s: float = 10.0
    db_connect_timeout_s: float = 5.0
```

> **Decision (judgment call, documented):** use **`NEON_DATABASE_URL_RO`**. Rationale: the `_RO` suffix
> makes the read-only contract explicit at every call site and prevents anyone from pasting the
> read+write `recalls_app` DSN into this service by muscle memory. **Confirm the final var name, the
> pooled (PgBouncer) endpoint string, and the role name/grants with the operator** before deploy
> (open item R1) — these are an out-of-band coordination, not a code decision.

---

## 2. Phased branch + commit plan

**Conventions.** One feature branch per phase, one PR per branch, Conventional Commits. Commit messages
end with the Co-Authored-By trailer. The build session **writes** the code in these commits; the operator
**runs** anything that touches live infra (Fly app create, secrets, prod deploy, the P1 role migration).
Every branch must be **green on its own gates** (§2.1) before its PR opens; OpenAPI is regenerated and
committed on any branch that changes a route or response model.

### 2.1 Per-branch gates (run before opening the PR — identical to CI, see `05`)

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov=recalls_api --cov-fail-under=85   # unit + integration + contract
uv run python -m recalls_api.export_openapi > openapi.json   # regen; must be a no-op diff if unchanged
git diff --exit-code openapi.json                            # fail if spec drifted un-committed
uv run pre-commit run --all-files
```

> The OpenAPI regen+diff step is a **no-op on branches that change no routes** (scaffold, deploy). On
> route/model branches it produces a real diff that **must be committed in the same branch** — that is
> how the committed snapshot stays the contract (locked decision 11).

### Branch `feature/api-scaffold` — settings, db, errors, logging, health

| Commit | Type | What Claude Code writes |
|---|---|---|
| C1 | `chore: init repo with uv + tooling gate` | `pyproject.toml` (deps: fastapi, pydantic v2, pydantic-settings, sqlalchemy[asyncio], asyncpg, structlog, uvicorn; dev: pytest, pytest-asyncio, pytest-cov, httpx, ruff, pyright, pre-commit, hypothesis; **slowapi** marked "chosen here, not ADR-ratified"), `uv.lock`, `.envrc`, `.env.example` (documents `NEON_DATABASE_URL_RO`), `ruff`/`pyright`/`pytest`/`coverage` config, `.pre-commit-config.yaml`, `README.md` (points at pipeline gold docs + docs `01`/`03`), empty `src/recalls_api/__init__.py` with `__version__`. |
| C2 | `feat: settings + async db pool with fail-loud boot` | `settings.py` (§1.2, fail-loud `ValidationError`), `db.py` (`create_async_engine` with `pool_size`/`max_overflow`/`pool_pre_ping=True`/`pool_recycle`, lifespan open/close, `get_conn` request dep, `SELECT 1` healthcheck), unit test that a missing DSN raises at construction. |
| C3 | `feat: structlog json logging + request_id middleware` | `logging.py` (structlog JSON to stdout), contextvars `request_id` (uuid) middleware bound to every log line. Unit test: a log line carries `request_id`. |
| C4 | `feat: error taxonomy + json envelope handlers` | `errors.py` (`ResourceNotFound`→404, `InvalidParameter`→422, `BadCursor`→400, `UpstreamUnavailable`→503+`Retry-After`, `RateLimited`→429, catch-all→500 opaque). Envelope `{"error":{"type","detail","request_id"}}`. Unit tests: each handler shapes the envelope; 500 never leaks SQL/DSN/traceback. |
| C5 | `feat: app factory + health and health/db endpoints` | `main.py` (FastAPI app factory, lifespan, router includes, exception handler registration), `routers/health.py` (`GET /health` liveness; `GET /health/db` runs `SELECT 1` and maps a cold/asleep/timeout Neon to **503 + `Retry-After`**, never hangs). First **integration** test via `httpx.AsyncClient + ASGITransport`: `/health`=200, `/health/db`=200 against the seeded container. |
| C6 | `test: seed_gold.sql cassette + conftest fixtures` | `tests/fixtures/seed_gold.sql` (the deterministic gold cassette — minimal rows covering: an active recall, a retracted one, a multi-firm jsonb rollup, a USCG HIN product, an NHTSA model product, a firm spanning two sources, an FTS hit + miss, plus a populated `search_vector`), `tests/conftest.py` (async client fixture + seeded-DB fixture wired to the service container DSN). |

**Acceptance:** all six gates green; `/health` + `/health/db` covered by integration tests against the
seeded container; boot fails loudly with no DSN; no test touches prod Neon.

### Branch `feature/api-recalls` — pagination + list + detail

| Commit | Type | What Claude Code writes |
|---|---|---|
| C7 | `feat: keyset pagination codec + Page envelope` | `pagination.py` (pure encode/decode of an **opaque base64url** cursor over the last sort tuple; tamper/garbage → `BadCursor`), `models/common.py` (`Page[T]` = `{items, next_cursor, limit}`, `Source` `StrEnum`, `FirmRef`). Unit + **hypothesis** round-trip: `decode(encode(x)) == x`; boundary empties. |
| C8 | `feat: GET /recalls list with keyset + filters` | `queries/recalls.py` (pure SQLAlchemy Core builder; conditional `.where()` per set filter; **bind params only, never f-string SQL**), `models/recalls.py` `RecallSummary` (list projection per doc `01`/`03`; `classification`/`risk_level` free strings; `is_active: bool \| None` tri-state; `firm_count`/`product_count`/`edit_event_count` `int`), `routers/recalls.py`. Order `published_at DESC, recall_event_id`. Unit: SQL+params for every filter combo. Integration: filtered + paged against seed. **OpenAPI regen+commit** — description carries the [unfiltered-sort caveat](#caveat). |
| C9 | `feat: GET /recalls/{source}/{recall_id} detail (md5 key)` | Detail handler computes `recall_event_id = md5(f"{source.value.upper()}\|{recall_id}")` and hits `UNIQUE(recall_event_id)`; `RecallDetail` (full wide row; `distribution_states: str \| None` **scalar**; `distribution_state_codes`/`distribution_country_codes: list[str] \| None`; `hazards` opaque `list \| None`; `product_names`/`models`/`hins` default `[]`; `firms: list[FirmRef]`). 404 on miss. Integration: hit + miss + multi-firm rollup. **OpenAPI regen+commit.** |

<a name="caveat"></a>**Honest caveat baked into the `/recalls` OpenAPI description (locked decision 4):**

> "An **unfiltered** `/recalls` sorted by `published_at DESC` is **not index-backed** — only a
> `(source, published_at)` composite exists, with no standalone `published_at` index. Deep unfiltered
> pagination pays a full sort. Add `?source=` to make the sort index-backed; deep pagination is steered
> behind a `source` filter."

**Acceptance:** gates green; list+detail covered by pure builder unit tests + seeded integration
(filtered, paged, hit, miss, multi-firm); the unfiltered-sort caveat is in the OpenAPI copy; the md5 key
is computed in-API (no composite-index dependency).

### Branch `feature/api-products` — search

| Commit | Type | What Claude Code writes |
|---|---|---|
| C10 | `feat: GET /products/search (FTS + identifier + upc-jsonb)` | `queries/products.py` (FTS path: `search_vector @@ websearch_to_tsquery('english', :q)` ranked by `ts_rank_cd`, keyset on `(rank DESC, recall_product_id)`; identifier path: btree equality on `hin`/`model`; **UPC routes to `recall_product_upcs` jsonb containment**, NOT the all-null per-product `upc` column), `models/products.py` `ProductSearchHit` (`model_year: str \| int \| None`; `type: str \| None`; `rank: float \| None` on FTS), router. **Require at least one of `q\|hin\|model\|upc` else 422.** Integration: FTS hit/miss, HIN exact, UPC-via-jsonb, the 422-no-param case. **OpenAPI regen+commit** with the caveats below. |

**Honest caveats baked into the `/products/search` OpenAPI description (locked decision 5):**

> "**No fuzzy/typo search** — `pg_trgm` is not enabled (ADR 0037); queries must match stored tokens.
> The per-product `upc` column is **NULL for every row today**; `?upc=` matches recall-level UPCs via
> `recall_product_upcs` jsonb containment, surfaced with `upc_is_recall_level: true` so a miss is not
> misread as 'not recalled'."

**Acceptance:** gates green; all three search paths + the 422-no-param guard covered by seeded
integration (the seed includes a populated `search_vector` so FTS runs for real); no-fuzzy and
recall-level-UPC caveats in OpenAPI.

### Branch `feature/api-firms` — firm profile

| Commit | Type | What Claude Code writes |
|---|---|---|
| C11 | `feat: GET /firms/{id} with per-source sidecars` | `queries/firms.py` (keyed read on `firm_id` `UNIQUE`), `models/firms.py` `FirmProfile` + **three per-source sub-models** `UsdaEstablishment` / `UscgManufacturer` / `FdaAttributes` mapping the source-aligned mart columns `firm_usda_attributes` / `firm_uscg_attributes` / `firm_fda_attributes` (R5 rename applied upstream), each array default `[]`; `recalls_by_source: dict[str,int]` default `{}`; `roles` default `[]`; `first_recall_at`/`last_recall_at: datetime \| None`. 404 on miss. Integration: a firm spanning two sources (cross-source rollup) + `recalls_by_source` dict + each sidecar shape. **OpenAPI regen+commit.** |

**Acceptance:** gates green; firm profile covered by seeded integration including a cross-source firm and
each of the three sidecar shapes; the three sidecar field names match the mart verbatim.

### Branch `feature/api-openapi-contract` — spec hardening + contract tests

| Commit | Type | What Claude Code writes |
|---|---|---|
| C12 | `feat: openapi enrichment + export script` | Per-endpoint `summary`/`description` (carrying every honest caveat), `response_model` on every route, `responses={404,422,503}` so error shapes are in the spec, `Field(examples=[...])` on filter params + response models. `src/recalls_api/export_openapi.py` (imports the app, dumps `app.openapi()` — pure, testable). Commit the regenerated `openapi.json`. |
| C13 | `test: openapi snapshot diff + response-schema conformance` | `tests/contract/`: (a) `app.openapi()` == committed `openapi.json` (drift = fail); (b) each endpoint's live response validates against its Pydantic `response_model` (a **gold-schema-drift canary**). |

**Acceptance:** gates green; the committed `openapi.json` is the contract; the snapshot-diff test fails on
any un-committed spec change; every endpoint's honest caveat is present in its OpenAPI description.

### Branch `feature/api-deploy` — image, platform config, CI/CD, caching, rate limit

| Commit | Type | What Claude Code writes |
|---|---|---|
| C14 | `feat: dockerfile + fly.toml + render.yaml stub` | `Dockerfile` (slim CPython 3.12, uv-installed deps, uvicorn entrypoint, **non-root** user), `fly.toml` (health check on `/health`, region near Neon, `min_machines_running=0` — free-tier default; keep-warm cron is the documented lever, see doc 06 §4c/§14), `render.yaml` stub (documented fallback). **No `wrangler.toml`** (Workers rejected — Pyodide/WASM can't load asyncpg). |
| C15 | `feat: http cache headers + retry-after + rate limit` | `Cache-Control: public, max-age=...` + `ETag`/`Last-Modified` keyed off the gold rebuild timestamp (or coarse `max-age` fallback if P3 not yet landed), `Retry-After` on 503/429, slowapi IP rate limit (tuned to free-tier DB; commented "chosen here, not ADR-ratified"). |
| C16 | `ci: github actions ci + deploy workflows` | `.github/workflows/ci.yml` (`uv sync` → `ruff check` → `ruff format --check` → `pyright` → `pytest` with `services: postgres` seeded by `seed_gold.sql` + `--cov-fail-under=85` → openapi drift check → `pre-commit run --all-files`; **no dbt steps**), `.github/workflows/deploy.yml` (`flyctl deploy` on push to `main`, Fly token from secrets), README run/deploy instructions. |

**Acceptance:** gates green; CI mirrors the local gate exactly and runs against a seeded service
container (never prod Neon); deploy workflow exists but the **operator** runs first `fly app create` +
secrets + deploy; cold/asleep Neon fails to 503+`Retry-After` (not a hang).

---

## 3. Execution order + dependency gates between branches

```
feature/api-scaffold                     [must merge first — settings/db/errors/health/seed are the base]
        │
        ▼
feature/api-recalls                      [needs pagination.py + Page[T] + Source enum + seed cassette]
        │
        ├──────────────┐                 ┌── these two share no code; build in parallel after recalls
        ▼              ▼
feature/api-products   feature/api-firms  [each: own queries/ + models/ module; both reuse Page[T]/enums/seed]
        └──────┬───────┘
               ▼
feature/api-openapi-contract             [needs ALL routes + response models final → spec is complete]
               │
               ▼
feature/api-deploy                        [last — packages the finished, contract-locked app]
```

| Gate | Why it is ordered this way |
|---|---|
| scaffold **before everything** | `pagination.py`, `Page[T]`, `Source` enum, `errors.py`, `db.py`, and the `seed_gold.sql` cassette are dependencies of every endpoint branch. |
| recalls **before** products/firms | recalls introduces the keyset codec + `Page[T]` + `FirmRef` reused by products/firms; landing it first avoids three branches inventing the cursor in parallel. |
| products ∥ firms | Independent modules (`queries/products.py`+`models/products.py` vs `queries/firms.py`+`models/firms.py`), no shared new code beyond the already-merged commons → **safe to parallelize**. They will both touch `openapi.json`; resolve that on the openapi-contract branch, not by merging spec edits from two branches. |
| openapi-contract **after all routes** | The committed snapshot must reflect the **complete** route+model set; enriching it earlier guarantees a re-diff churn. |
| deploy **last** | Dockerfile/CI/cache/rate-limit wrap the finished app; nothing else depends on them. |

---

## 4. Open questions ledger

### 4.1 RESOLVED (do NOT re-litigate — locked in docs `01`/`02`)

| Topic | Resolution | Source |
|---|---|---|
| Detail-endpoint key | Compute `recall_event_id = md5(f"{SOURCE_UPPER}\|{recall_id}")` in-API; hit existing `UNIQUE(recall_event_id)`. | `02` Decisions-locked; `01` Mart 1 |
| Composite index `(source, source_recall_id)` | **Dropped — not needed.** Do not request a pipeline index change. | `02` (C0c-dbt) |
| Firm sidecar field names | `firm_usda_attributes` (USDA) / `firm_uscg_attributes` (USCG) / `firm_fda_attributes` (FDA) — **R5 rename applied** at the mart output; 3 per-source sub-models, each array default `[]`. | `02` (superseded by R5); `01` Mart 3 |
| `classification` / `risk_level` / `type` | **NOT global enums** — source-native / disjoint domains → free-string equality filters/fields. Only `source` is a closed UPPERCASE `StrEnum`. | `01`; `02` |
| `is_active` | **Tri-state** `bool \| None` (NULL for CPSC/NHTSA); an `?is_active=true` filter excludes NULL rows. | `01`; `02` |
| `distribution_states` | **Scalar `str \| None`**, distinct from `distribution_state_codes: list[str] \| None`. | `02` |
| Pagination | Keyset/seek; `limit+1`; opaque base64url cursor; no COUNT by default; `?with_total=true` opt-in. | `02` Decisions-locked |
| Search paths | FTS via `websearch_to_tsquery` over stored `search_vector`; exact via hin/model btree; UPC via `recall_product_upcs` jsonb containment; **no fuzzy** (pg_trgm off, ADR 0037); require ≥1 of `q\|hin\|model\|upc` else 422. | `01` Mart 2; `02` |
| CI test DB | **Seeded Postgres service container** (`seed_gold.sql` cassette) — NOT a Neon branch, NOT prod. 85% coverage floor. | `02`; plan §7 |
| Deploy target | **Fly.io**; Render fallback; **Cloudflare Workers rejected** (Pyodide/WASM can't load asyncpg). | `02`; ADR 0025 |
| `/stats/*` | **Out of v1** — deferred. v1 = 4 endpoints + `/openapi.json` + `/health` + `/health/db`. | `02`; ADR 0024 |
| Observability v1 | structlog JSON + `request_id`; operator reads platform logs; **no Sentry/Datadog/OTel** in v1. | `02`; ADR 0029 |

### 4.2 REMAINING (each with HOW to resolve)

| # | Open item | How to resolve / who to ask |
|---|---|---|
| R1 | **Read-only role specifics** — exact role name (`recalls_readonly`?), `GRANT SELECT` target set (all tables vs only `mart_*`), pooled (PgBouncer) vs direct Neon endpoint, whether `default_transaction_read_only=on` is set, and the env-var name (`NEON_DATABASE_URL_RO`?). **(This is P1 — the live-deploy blocker.)** | **Ask the operator.** The role is provisioned in the pipeline repo as a migration mirroring `migrations/versions/0033_recalls_app_role_posture.py` (doc `07` #2). The API only consumes the resulting DSN; confirm name+endpoint+grants before wiring `db.py` against prod and before deploy. Not in any read ADR. |
| R2 | **`hazards` jsonb element shape** (mart_recall_summary) | If the API must type it: inspect a live row, or read the CPSC `hazards` source in `dbt/models/silver/recall_event.sql` @ `39dcbda`. Otherwise model **opaque** (`list \| None` / `Any`) — the locked default. No blocker. |
| R3 | **`model_year` physical type** (mart_product_search — int vs text) | Model permissively as `str \| int \| None` (locked default, Pydantic coerces). To pin it: inspect a live mart row, or check `dbt/models/gold/mart_product_search.sql` casts. No blocker. |
| R4 | **Per-mart row counts** (for real perf sizing) | Not in any read doc; the "130k" figure is **not** to be hard-coded. Get exact counts via `SELECT count(*)` against the read-only role once P1 lands, or ask the operator. Keyset/no-count-by-default design is correct regardless — not a blocker. |
| R5 | **slowapi rate-limit policy** (limits, per-IP window) | **API-repo decision, NOT ADR-ratified** (ADR 0024 only says "abuse control is platform/rate-limit level"). Pick limits tuned to the free-tier DB; document as "chosen here, not from ADR" in `06` and the C15 commit. Confirm tolerances with the operator if traffic shape is known. |
| R6 | **Postgres / Neon version** (FTS + jsonb-containment behavior parity between the CI container and prod Neon) | Match the CI `services: postgres` image tag to Neon's major version. Ask the operator for the Neon Postgres major, or read it from a `SELECT version()` once P1 lands; pin the container image accordingly in `ci.yml`. Low risk for `websearch_to_tsquery` + `@>` containment, but pin to avoid surprises. |
| R7 | **Gold rebuild-timestamp surface** (for cache validators — P3) | Doc `07` #6: ask the pipeline repo to expose a queryable "last transform completed at". Until then, ship the coarse `Cache-Control: max-age` fallback (C15). Soft; upgrade cache headers when it lands. |

---

## 5. Build-session kickoff checklist (the first 10 things)

1. **Read the build docs in order:** `00` (if present) → `01` (the schema contract — trust over the
   plan) → `02` (drift + locked decisions) → `03` API contract → `04` implementation → `05` testing/CI
   → `06` deploy/ops → `07` gold-layer recs → **this `08`**. Treat `01` as authoritative for any
   column/type/null/enum fact.
2. **Confirm the read-only role with the operator (open item R1 / prerequisite P1):** role name, env
   var (`NEON_DATABASE_URL_RO`?), pooled endpoint, and grants. This is the one hard blocker for live
   deploy — surface it on day one so the pipeline-repo migration can land in parallel. Do **not** wait
   on it to start coding (CI uses the throwaway container).
3. **Init the repo with `uv`** (Conventional-Commit `chore: init` = commit C1): `pyproject.toml` with
   the pinned deps + ruff/pyright/pytest/coverage config, `uv.lock`, `.envrc`, `.env.example`
   documenting `NEON_DATABASE_URL_RO`, `.pre-commit-config.yaml`, README pointing at docs `01`/`03` and
   the pipeline gold docs. Verify the empty-package gate is green (`ruff`/`pyright`/`pytest` pass with
   no tests yet).
4. **Scaffold settings + db + errors + health first** (commits C2–C5, the `feature/api-scaffold`
   branch): `settings.py` (fail-loud `ValidationError` on missing DSN, mirror the pipeline's
   `SecretStr` + call-time-construction pattern), `db.py` (async pool with `pool_pre_ping`/`pool_recycle`
   + cold-Neon→503 healthcheck), `errors.py` (the envelope taxonomy), `logging.py` (structlog +
   `request_id`), `main.py` app factory, `/health` + `/health/db`.
5. **Write the `seed_gold.sql` cassette + conftest** (commit C6) early — every endpoint branch's
   integration tests depend on it. Seed the cross-cutting shapes (active/retracted recall, multi-firm
   rollup, USCG HIN, NHTSA model, two-source firm, FTS hit/miss, populated `search_vector`).
6. **Stand up the Postgres service container locally** to match CI (`docker run` a Postgres pinned to
   Neon's major version per R6) and load `seed_gold.sql`; confirm the first `/health/db` integration
   test passes via `httpx.AsyncClient + ASGITransport`. **No test ever points at prod Neon.**
7. **Verify the full local gate is green on the scaffold branch** before moving on: the §2.1 command
   block, including `--cov-fail-under=85` and the OpenAPI regen+diff no-op.
8. **Build endpoints in dependency order** (§3): `feature/api-recalls` (pagination → list → detail with
   the md5 key) → then `feature/api-products` and `feature/api-firms` in parallel. Bake each honest
   caveat into the route's OpenAPI description as the route is written, not after.
9. **Harden the contract** (`feature/api-openapi-contract`): enrich the spec, write `export_openapi.py`,
   commit `openapi.json`, add the snapshot-diff + response-schema-conformance contract tests. From here
   on, any route/model change regenerates and commits the snapshot in the same branch.
10. **Package + ship** (`feature/api-deploy`): Dockerfile (non-root, slim 3.12) + `fly.toml` +
    `render.yaml` stub (no `wrangler.toml`), cache headers + `Retry-After` + slowapi, CI/deploy
    workflows. Hand off the live steps (Fly app create, secrets, first deploy, and confirmation that the
    P1 read-only role is active) to the operator.

> **Judgment calls flagged in this doc:** (a) env var named **`NEON_DATABASE_URL_RO`** with the `_RO`
> suffix to encode the read-only posture — confirm with the operator (R1); (b) **`recalls_readonly`** as
> the suggested role name (operator owns the final name); (c) slowapi limits are an API-repo choice, not
> ADR-ratified (R5). All three are coordination items, not code blockers.
