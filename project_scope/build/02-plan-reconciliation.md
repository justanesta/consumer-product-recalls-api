# Plan Reconciliation — Drift Report (recalls-api)

> Compares `project_scope/fastapi-serving-layer-plan.md` (the design being hardened) against the
> orchestrator-verified mart facts and the directly-read mart SQL / silver SQL / ADRs at the pinned
> commit. **Severity:** `blocker` (will break or mislead the build), `important` (must change a
> decision/field), `minor` (small correction), `confirmed` (plan is right — locked).

## Provenance

Same as `01-ground-truth-gold-marts.md`: repo `justanesta/consumer-product-recalls` @
`feature/pre-go-live-validation`, commit `39dcbda3da7c1915b3c660327ebdd8b8dab09bb5`
(2026-06-13T17:11:23Z). `main` (`dc2a155`, 2026-06-11) is 1 commit behind. ADRs 0024/0025/0035/0036/0037/0038
read directly. The plan's references to branch `feature/phase-7-production-plus-todos` are **stale** —
that branch no longer exists; the authoritative branch is `feature/pre-go-live-validation`.

---

## Area: Recalls list / detail (`mart_recall_summary`)

| Plan claim | Current reality | Severity | Resolution |
|---|---|---|---|
| Detail key: compute `recall_event_id = md5(source\|\|'\|'\|\|source_recall_id)`, hit existing unique index, no upstream change (§3 detail) | **Confirmed** in `recall_event.sql` for all 5 sources; `source_recall_id` holds the exact md5 business key (incl. FDA where staging col is RECALLEVENTID but `source_recall_id = recall_event_id::text`). | confirmed | Lock the md5 path. `source` MUST be uppercased before hashing. |
| Optional `(source, source_recall_id)` composite index `C0c-dbt` as alternative | The md5 path makes this **unnecessary**; UNIQUE(recall_event_id) already serves it. | minor | **Drop C0c-dbt entirely.** Don't request a pipeline index change. |
| `RecallSummary` list projection includes `reason_category, primary_firm_name, firm_count, product_count, edit_event_count, has_been_edited` etc. | All present and correctly typed. `firm_count`/`product_count`/`edit_event_count` are bigint; `has_been_edited` bool NOT NULL. | confirmed | Lock list projection. |
| Detail projects the full wide row incl. `distribution_states, hazards, product_upcs` as "jsonb arrays → typed lists" | `distribution_states` is a **scalar text** column (`re.distribution_states`), NOT an array — distinct from the `distribution_state_codes` **text[]** array. `hazards` is jsonb of unconfirmed element shape. `product_upcs` is recall-level jsonb. | important | Model `distribution_states: str \| None` (scalar). Model `distribution_state_codes`/`distribution_country_codes` as `list[str] \| None` (text[], NULL when no rda row). Treat `hazards` as opaque jsonb (`list \| None` or `Any`). |
| `product_names`/`models`/`hins` "are NULL when empty; default to `[]`" (§4) | **Confirmed** — `jsonb_agg ... filter` un-coalesced; NULL when no products. | confirmed | `Field(default_factory=list)` on these three. |
| `announced_at` nullable; `is_active` filter | **Confirmed nullable by design** (~20 FDA). `is_active` is **tri-state** (NULL for CPSC/NHTSA), not just bool. | important | `announced_at: datetime \| None`, `is_active: bool \| None`. A `?is_active=true` filter excludes NULL rows — document that CPSC/NHTSA never match an is_active filter. |
| Filter `classification` as a shared `StrEnum(Source, Classification)` (§1, §4) | `classification` is **source-native, not a unified enum** (ADR 0036 D2): FDA `1/2/3/NC`, USDA `Class I/II/III` + `Public Health Alert`, USCG `H/L/M/S`, CPSC/NHTSA NULL. `risk_level` is **USDA-only**. | important | Keep `Source` as StrEnum; do **NOT** make `Classification` a global StrEnum the client filters by value. `?classification=` is a free-string equality on the indexed column; document source-scoped meaning. |
| Index reliance: `(source, published_at)`, `(is_active)`, `(classification)` btree back every filter; keyset uses `(published_at, recall_event_id)` (§3, §5) | Indexes confirmed. **But there is NO standalone `published_at` index and NO `(published_at, recall_event_id)` index.** Unfiltered `ORDER BY published_at DESC` is a full sort; index-backed only when `?source=` leads. | **blocker** | Correct §3/§5: unfiltered keyset on `published_at` is NOT index-backed. Either (a) document the full-sort cost (acceptable at corpus scale), or (b) steer deep pagination behind a `source` filter. Do NOT claim the composite backs an unfiltered sort. |

## Area: Product search (`mart_product_search`)

| Plan claim | Current reality | Severity | Resolution |
|---|---|---|---|
| Two paths: identifier btree (hin/model/upc) + FTS over `search_vector` GIN; `websearch_to_tsquery`; `ts_rank_cd` (§3, §5) | Confirmed: UNIQUE(recall_product_id), btree(recall_event_id/hin/model/upc), GIN(search_vector). search_vector = product_name+description+recall_title+firm_name coalesced. | confirmed | Lock FTS design + `websearch_to_tsquery`. |
| Product-grain `upc` is NULL for every source; recall-level UPCs ride `recall_product_upcs` jsonb; surface a note (§3) | **Confirmed** — `upc` btree exists but all-null. | confirmed | Do NOT advertise `?upc=` product search returning hits; route UPC to `recall_product_upcs` jsonb containment. Surface `upc_is_recall_level` note. |
| No fuzzy/typo search (pg_trgm not enabled, ADR 0037) | Confirmed (ADR 0037; firm fuzziness resolved upstream by Python clusterer). | confirmed | Document honestly in OpenAPI. |
| `ProductSearchHit` fields incl. `model_year`, `type` | `model_year` type undeclared (int vs text — FLAGGED). `type` is five disjoint per-source domains, not a global enum. | minor | Model `model_year: str \| int \| None` (or `str \| None`); `type: str \| None` free string. |
| Keyset on FTS path `(rank DESC, recall_product_id)` (§3) | Correct that rank ordering is the design; note **rank is not an ordered index path** (GIN serves the `@@` match, not the sort) — fine on the matched set. | minor | Keep; note the keyset cursor on rank is application-level over the matched set, not an index seek. |
| `recall_product_id` opaque, stable across rebuilds | **Confirmed** — migrated to stable `(event, ordinal)` key at this very commit (`39dcbda`, CPSC). Good for cursor stability. | confirmed | Treat as opaque keyset key. |

## Area: Firm profile (`mart_firm_profile`)

| Plan claim | Current reality | Severity | Resolution |
|---|---|---|---|
| Sidecar mart columns "are being renamed to `firm_{usda,uscg,fda}_attributes` (C19) — confirm at build time" (§3, C7) | **WRONG / stale.** The rename hit the upstream **silver source tables only**. The MART OUTPUT columns are still `establishment_attributes` (USDA), `manufacturer_attributes` (USCG), `fda_attributes` (FDA) — verified in `mart_firm_profile.sql`. | **blocker** | Use `establishment_attributes`/`manufacturer_attributes`/`fda_attributes` verbatim as API field names. Remove the "confirm renamed names" note — there is no mart rename. **(Superseded post-build: R5 was later applied upstream; the mart columns and the shipped API now use `firm_usda_attributes`/`firm_uscg_attributes`/`firm_fda_attributes`.)** |
| Sidecars "typed loosely as shapes differ by source"; `list[SidecarAttributes]` | Correct that shapes differ; per-source full-row shapes are now known (see doc 01 mapping table). A single shared model is wrong. | important | Use 3 per-source sub-models (UsdaEstablishment / UscgManufacturer / FdaAttributes) with the documented keys, all fields optional except join key. Default each array to `[]`. |
| `recalls_by_source` jsonb dict → `dict[str,int]` (§3) | Confirmed (`jsonb_object_agg`). NULLABLE (not coalesced). | confirmed | `dict[str,int]` default `{}`. |
| `firm_id` path param = md5 cluster id, unique index | Confirmed `firm_id = md5(upper(trim(name)))`, UNIQUE. | confirmed | Lock. Opaque path param. |
| `first_recall_at`/`last_recall_at`/`roles` present | All **NOT coalesced** → NULLABLE (NULL for firm with zero matched recalls). | minor | `first_recall_at`/`last_recall_at`: `datetime \| None`; `roles`: default `[]`. |
| `distinct_products` int | It's `sum()` over bigint → **numeric** (integer-valued), coalesced 0. | minor | Model `int` (safe; value is integral). |

## Area: Pagination / indexes

| Plan claim | Current reality | Severity | Resolution |
|---|---|---|---|
| Keyset (seek) pagination, not OFFSET; cursor encodes last sort tuple; `limit+1`; opaque base64 cursor (§5) | Endorsed by ADR 0024 §3 (keyset, index-friendly, stable under nightly rewrite). | confirmed | Lock keyset design and pure `pagination.py` codec. |
| `/recalls` keyset `(published_at, recall_event_id)` is index-backed | **Not index-backed when unfiltered** (see Recalls area blocker). | **blocker** | See above — the single most important index caveat. |
| `firm` substring `ILIKE` has no index ("future trigram candidate") | Correct — no expression index; pg_trgm disabled (ADR 0037) so trigram is not a near option. | confirmed | Accept seq-ish ILIKE at corpus scale; do not promise trigram. |
| "130k-row recall mart" sizing figure (§5, §9) | **Unverified** — no per-mart row count in any read doc. Bronze corpus hints: ~9.8k CPSC, ~25k FDA events, ~24,204 firms. Recall total likely tens of thousands (50,854 figure is geography recall-cells, not mart rows). | minor | Treat row counts as unknown; keyset/no-count-by-default design is correct regardless. Don't hard-code 130k. |
| No total count by default; `?with_total=true` opt-in (§5) | Sound; not contradicted by sources. | confirmed | Lock. |

## Area: Deferred stats (`fct_*`)

| Plan claim | Current reality | Severity | Resolution |
|---|---|---|---|
| `fct_*` back optional `/stats/*`, deferred from v1; 4-endpoint v1 contract (§3 deferred) | Confirmed by ADR 0024 §5 (`/stats/*` deferred, gated on website chart inventory; v1 = 4 endpoints). | confirmed | Keep `/stats/*` out of v1. |
| Geography lens trap: two bases `distribution` vs `firm_location`; expose `geography_basis` + caveat (§3 deferred) | The basis value was **renamed `firm_location` → `firm_registration`** (C17). Both `distribution`-only-FDA/USDA and the multi-count-footprint trap confirmed. | minor | If/when building `/stats/.../geography`, use `firm_registration` (not firm_location); carry "never read as consumer impact" + footprint-inflation caveat. |
| Plan lists 7 fct marts for dashboards | There are **10 fct_* + dim_date** (adds `fct_recalls_by_country`, and the plan omits it; counts also vary in pipeline prose). units/trend/by_firm have NO 'ALL' rollup; geography is the only indexed fct table. | minor | Use doc 01's fct table as the authoritative list when scoping `/stats/*`. Note `fct_units_recalled` `_gold.yml` description is stale (SQL = `max(quantity_value)`). |

## Area: Deploy / infra

| Plan claim | Current reality | Severity | Resolution |
|---|---|---|---|
| Fly.io target, Render fallback, Cloudflare Workers rejected (Pyodide/WASM can't run asyncpg) (§0, §12) | **Confirmed verbatim** by ADR 0025 (Accepted 2026-06-09). | confirmed | Lock. Ship Dockerfile + fly.toml + render.yaml stub; no wrangler.toml. |
| Stack: FastAPI + Pydantic v2 + SQLAlchemy Core async over asyncpg, read-only to Neon main (§1) | **Confirmed** by ADR 0024 §1 (Core, not ORM; read-only Neon main). | confirmed | Lock. |
| Settings env var `DATABASE_URL` (§1 settings, §2) | The pipeline's canonical DB env var is **`NEON_DATABASE_URL`** (pydantic field `neon_database_url: SecretStr`), targeting branch `main` in CI (ADR 0005/0016). ADR 0024/0025 don't name the API's var. | important | The API is a separate repo and MAY pick its own var, but **mirror `NEON_DATABASE_URL`** (or a read-only variant like `NEON_DATABASE_URL_RO`) for consistency, as `SecretStr`, fail-loud at boot. Don't silently introduce `DATABASE_URL`; decide and document in the API's settings. |
| Read-only Postgres role + `GRANT SELECT` + `default_transaction_read_only=on`, provisioned by pipeline repo (§9, C0c-ops) | ADR 0025 confirms a **dedicated restricted read-only Neon role** (ADR 0013 amendment + mutation-guard). Exact role name/grants/pooled-vs-direct endpoint **NOT specified** in read ADRs. | important | Keep the read-only posture; the role provisioning is a pipeline-repo/operator task. The exact role name, grants, pooled (PgBouncer) endpoint, and `default_transaction_read_only` are an open item to confirm with the operator. |
| `pool_pre_ping`, `pool_recycle`, cold-start → 503 + Retry-After; HTTP cache headers keyed off nightly rebuild (§9) | Cold starts confirmed acceptable (ADR 0005, ADR 0025). Transform rebuilds nightly ~03:00 UTC (architecture.md) — good ETag/Last-Modified anchor; both silver+gold fully rebuilt each run. | confirmed | Lock cold-start + caching strategy. |
| slowapi IP rate limit at app layer (§0, §6, §9) | **Unverified by source.** ADR 0024 §6 says only "abuse control is platform/rate-limit level, not application auth" — does NOT name slowapi or any limit. | important | slowapi is a reasonable choice but is an **API-repo decision, not ratified by an ADR**. Ship it as the plan intends, but mark it "chosen here, not from ADR"; tune limits to free-tier DB. |

## Area: Testing / CI

| Plan claim | Current reality | Severity | Resolution |
|---|---|---|---|
| pytest pyramid; `--cov-fail-under=85`; offline/deterministic; no test hits prod Neon (§7) | Confirmed mirror of ADR 0015 (85% floor, ephemeral test DB, cassette discipline). | confirmed | Lock. |
| CI gate: `uv sync` → ruff check + ruff format --check → pyright → pytest(+postgres service) → openapi drift → `pre-commit run --all-files` (§11) | ADR 0018 gate is ruff check + ruff format --check + pyright + pytest unit + pytest integration + dbt parse + e2e smoke + `pre-commit run --all-files`. `uv sync` is implied (uv per ADR 0017) but not literally an ADR gate step; `dbt parse`/e2e/Neon-branch steps are pipeline-specific (API repo has no dbt). | minor | Keep the API gate (no dbt parse). `uv sync` as setup is fine. Postgres **service container** seeded by `seed_gold.sql` recommended over Neon branch for the API repo (faster, fewer secrets) — matches ADR 0015's swappable-provider seam. |
| CI test DB = seeded gold via `services: postgres` (recommended) vs ephemeral Neon branch (§7, §14 Q2) | ADR 0015's `test_db_url` provider abstraction supports both; gold marts have no pipeline deps to reproduce, so a plain seeded Postgres is sufficient. | confirmed | Recommend service-container; keep Neon-branch as optional smoke. |
| OpenAPI: FastAPI generator is source of truth; committed `openapi.json` snapshot = contract-test fixture; drift = fail (§5, §8) | **Confirmed verbatim** by ADR 0024 §4. | confirmed | Lock the export-openapi + snapshot-diff contract test. |
| Dependabot | Not mentioned in any ADR. | minor | Optional; add if desired, not required. |
| structlog JSON, `request_id` correlation, v1 = "operator reads platform logs", defer Sentry/OTel (§10) | Confirmed mirror of ADR 0021 (structlog JSON, run_id/correlation) + ADR 0029 (operator-reads-logs, Sentry/OTel deferred; Phase 8 FastAPI is the natural home for `/health` + Sentry). | confirmed | Lock. `/health` + `/health/db` is the right place; Sentry deferred. |

---

## Decisions locked (do NOT re-litigate at build time)

- **4-endpoint v1 contract** (ADR 0024 §2): `GET /recalls`, `GET /recalls/{source}/{recall_id}`,
  `GET /products/search`, `GET /firms/{id}` + auto `GET /openapi.json`; plus operational `/health`,
  `/health/db`. No `/stats/*` in v1.
- **Stack:** FastAPI + Pydantic v2 + SQLAlchemy **Core** async over asyncpg, read-only to Neon `main`. Python 3.12, uv.
- **Detail lookup:** compute `recall_event_id = md5(f"{SOURCE_UPPER}|{recall_id}")`, hit
  `UNIQUE(recall_event_id)`. No new upstream index. **C0c-dbt composite index is dropped.**
- **Pagination:** keyset (seek), `limit+1`, opaque base64 cursor, no count by default, `?with_total=true` opt-in.
- **Search:** Postgres FTS via `websearch_to_tsquery` over stored `search_vector`; exact id via
  hin/model btree; UPC via `recall_product_upcs` jsonb containment (NOT the all-null `upc` column).
  No fuzzy/typo search.
- **Firm sidecar field names** (post-R5, source-aligned): `firm_usda_attributes` (USDA),
  `firm_uscg_attributes` (USCG), `firm_fda_attributes` (FDA). Per-source sub-models. *(02 originally
  recorded these as un-renamed; R5 was applied upstream after reconciliation.)*
- **Defaults:** `[]` for `product_names`/`models`/`hins`/`roles`/the 3 sidecar arrays; `{}` for
  `recalls_by_source`; `| None` for `announced_at`/`is_active`(tri-state)/`is_currently_active`/
  `was_ever_retracted`/`first_recall_at`/`last_recall_at`/geo arrays/firm-name fields.
- **`source` is a closed uppercase StrEnum** (CPSC/FDA/USDA/NHTSA/USCG). `classification`/`risk_level`/
  `type` are NOT global enums (source-native / disjoint) — free-string filters.
- **Deploy:** Fly.io (Render fallback, Workers rejected); Dockerfile + fly.toml + render.yaml stub;
  `flyctl deploy` on push to main. Read-only Neon role, cold-start → 503+Retry-After, HTTP cache headers.
- **Testing/CI:** 85% coverage floor; seeded-Postgres service container; OpenAPI snapshot contract test;
  structlog JSON; v1 operator-reads-logs (no Sentry/OTel).
- **`distribution_states` is a scalar text column**, distinct from the `distribution_state_codes` text[] array.

## MUST re-verify at build time (or with the operator)

- **Read-only Neon role specifics:** exact role name, `GRANT SELECT` target set, pooled (PgBouncer)
  vs direct endpoint, whether `default_transaction_read_only=on` is set, and the connection-string env
  var name the API should use (`NEON_DATABASE_URL` vs a `_RO` variant). Not in the read ADRs — confirm
  with the operator / pipeline repo before wiring `db.py`.
- **`hazards` jsonb element shape** (mart_recall_summary): selected as jsonb passthrough; element shape
  not declared. If the API needs to type it, inspect a live row or `recall_event.sql` CPSC `hazards`
  source; otherwise model as opaque `list \| None`.
- **`model_year` physical type** (mart_product_search): int vs text undeclared. Model permissively.
- **Per-mart row counts** for any real perf sizing (none in the read docs); don't hard-code 130k.
- **slowapi**: not ADR-ratified; confirm the rate-limit policy/limits as an API-repo decision.
- **`fct_*` exact `source` accepted_values per mart** if/when `/stats/*` is built (units ≠ country ≠ trend).
