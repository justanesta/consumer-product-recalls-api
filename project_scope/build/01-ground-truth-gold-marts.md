# Ground Truth — Gold Marts Schema Reference (recalls-api)

> **This is the authoritative schema contract the build session trusts INSTEAD of "re-read at
> build time".** Every fact below was read directly from the mart SQL / `_silver.yml` / `_gold.yml`
> / silver model SQL at the pinned commit. Where a fact could not be confirmed from source it is
> marked `[FLAGGED]` or moved to "Remaining unknowns".

## Provenance

| Field | Value |
|---|---|
| Repo | `justanesta/consumer-product-recalls` (the pipeline repo; **not** this API repo) |
| Branch | `feature/pre-go-live-validation` |
| Commit | `39dcbda3da7c1915b3c660327ebdd8b8dab09bb5` |
| Commit time | `2026-06-13T17:11:23Z` |
| `main` status | `dc2a155` (2026-06-11) is **1 commit behind** — LACKS the CPSC `recall_product_id` stable-(event,ordinal) migration and ADR 0041. Use the feature branch as ground truth. |
| Doc date | 2026-06-13 |

**To re-verify:** fetch `dbt/models/gold/mart_*.sql` (and `dbt/models/silver/recall_event.sql`,
`firm_*_attributes.sql`, `_silver.yml`, `_gold.yml`) at ref
`39dcbda3da7c1915b3c660327ebdd8b8dab09bb5`. The mart SQL is the type-bearing source; `_gold.yml`
carries `not_null`/`accepted_values` dbt tests (runtime expectations, **not** DB-level constraints);
`data_schemas.md` is a glossary that does **not** declare Postgres types.

**Type provenance rule:** marts are `materialized='table'` (real Postgres tables). No file declares
explicit DDL column types. Types tagged **(SQL)** are definitive — read off a SQL expression in the
mart (`jsonb_agg`/`jsonb_build_object`/`jsonb_object_agg`/`to_jsonb` → `jsonb`; `count()` → `bigint`;
`sum()` over bigint → `numeric`; `to_tsvector` → `tsvector`; `coalesce(x, 0)`/`coalesce(x,'[]'::jsonb)`
→ NOT NULL). Types tagged **(inf)** are inferred from documented semantics (silver passthrough scalars
are `text`/`timestamptz`/`boolean`); the silver DDL is not in the open snapshot, so confirm only if a
type choice is load-bearing (it generally is not — Pydantic coerces).

**Nullability rule:** every rollup CTE in every mart is reached via `LEFT JOIN`, so any **un-coalesced**
rollup column is NULLABLE in the mart even when the source column is `not_null`. `dbt not_null` ≠ a
Postgres `NOT NULL` constraint; treat it as "expected present". The API must model the explicitly-NULL
columns as `| None` (or default to `[]`) — see the per-mart "NULL-vs-coalesce" notes.

---

## Source / role / classification / lifecycle enums (cross-cutting)

### `source` — closed 5-value StrEnum, uppercase
`CPSC | FDA | USDA | NHTSA | USCG`. Confirmed `accepted_values` on `mart_recall_summary.source`,
`mart_product_search.source`, and the silver `recall_event`/`recall_product`. **Always uppercase in
storage.** The `fct_*` marts add a synthetic `'ALL'` rollup value (see fct section) — the three
serving marts do **NOT**. The detail-endpoint path param `{source}` must be one of these five.

### `recall_event_firm.role` — closed 5-value enum
`manufacturer | importer | distributor | establishment | filer`. (`retailer` was removed — CPSC retail
narrative moved to `recall_event.sales_channel_narrative`; `filer` is NHTSA-specific.) Per-source role
assignment: CPSC → manufacturer/importer/distributor; FDA → establishment; USDA → establishment;
NHTSA → filer (`mfgname`, filed it) + manufacturer (`mfgtxt`, made it); USCG → manufacturer.
This is the domain of `firms[].role` and `mart_firm_profile.roles[]`.

### `firms[].match_confidence` — closed enum (severity=error)
`exact_name, geo_suffix_strip_exact, dba_extract_exact, usda_unambiguous, usda_product_items_extract,
usda_state_match, usda_processing_match, usda_multi_signal, usda_ambiguous_null, uscg_mic_unambiguous,
uscg_mic_time_sensitive_unresolved, uscg_mic_build_date_resolved, fei_exact, name_variant_exact,
name_typo_high, rapidfuzz_rollup, singleton`. Default `exact_name`. Surface as opaque string; do not
type as a global enum the client filters on.

### `classification` — source-native, NOT a unified cross-source enum  ⚠️
One column, **source-dependent encoding** (ADR 0036 D2). Confirmed from `recall_event.sql`:

| Source | classification values | risk_level | lifecycle_status source field & values |
|---|---|---|---|
| CPSC | `NULL` (no field in API) | `NULL` | `NULL` |
| FDA | `center_classification_type_txt` → `Class I` / `Class II` / `Class III` (and source NC variants) | `NULL` | `phase_txt` → `Ongoing` / `Completed` / `Terminated` |
| USDA | `Class I` / `Class II` / `Class III` / `Public Health Alert` | derived 1:1 from classification: `High - Class I` / `Low - Class II` / `Marginal - Class III` / `Public Health Alert` | `recall_type` → `Active Recall` / `Public Health Alert` / `Closed Recall` |
| NHTSA | `NULL` | `NULL` | `NULL` |
| USCG | `severity` → `H` / `L` / `M` / `S` | `NULL` | `initcap(disposition)` → `Open` / `Closed` |

**API consequence:** `classification` cannot be a single global `StrEnum` the client filters by value
across sources — `Class I` (FDA/USDA) and `H` (USCG) coexist in the same column. Treat the `?classification=`
filter as a free string equality against the indexed column; document that its meaning is source-scoped.
`risk_level` is **USDA-only** (NULL everywhere else). `lifecycle_status` is NULL for CPSC and NHTSA.

### `is_active` — cross-source boolean, NULL for CPSC + NHTSA  ⚠️
Derived from FDA `phase_txt` (Ongoing→true, Completed/Terminated→false), USDA `recall_type`
(Active/PHA→true, Closed→false), USCG `disposition` (open→true, closed→false). CPSC and NHTSA carry no
native status → `is_active = NULL`. So `is_active` is **tri-state** (true/false/NULL); a `?is_active=`
filter must not silently exclude NULL rows unless that is intended. `fct_recall_status` maps NULL → `'unknown'`.

### `distribution_scope` — closed NOT-NULL enum
`Nationwide | International | Regional | Unspecified`. `not_null` (silver). CPSC + USCG → `Unspecified`;
NHTSA defaults `Nationwide`; FDA/USDA derived from distribution text/states.

---

## `recall_event_id` md5 surrogate (the detail-endpoint key)  ✅ CONFIRMED

```
recall_event_id = md5(source || '|' || source_recall_id)
```

Confirmed verbatim in `_silver.yml:14` ("Surrogate key md5(source || '|' || source_recall_id).") and
in each per-source CTE of `recall_event.sql`:

| Source | md5 input (line in recall_event.sql) | `source_recall_id` is |
|---|---|---|
| CPSC | `md5('CPSC' \|\| '\|' \|\| source_recall_id)` (L35) | RecallNumber |
| FDA  | `md5('FDA' \|\| '\|' \|\| recall_event_id::text)` (L96) | `recall_event_id::text` (RECALLEVENTID) — **written to `source_recall_id`** (L98) |
| USDA | `md5('USDA' \|\| '\|' \|\| source_recall_id)` (L196) | field_recall_number |
| NHTSA| `md5('NHTSA' \|\| '\|' \|\| campno)` (L278) | campno |
| USCG | `md5('USCG' \|\| '\|' \|\| source_recall_id)` (L356) | USCG Number |

**Load-bearing for the detail endpoint:** for every source, `source_recall_id` holds exactly the
business key fed into the md5. So the API can compute
`recall_event_id = md5(f"{source}|{recall_id}")` from `{source}/{recall_id}` path params and hit the
existing `UNIQUE(recall_event_id)` index on `mart_recall_summary` — **O(1), no new index, no upstream
change.** `source` MUST be uppercase before hashing (storage is uppercase). The C0c-dbt
`(source, source_recall_id)` composite index in the plan is therefore **unnecessary** — drop it.

---

## Mart 1 — `mart_recall_summary`  → `GET /recalls` (list + detail)

- **Grain:** one row per `recall_event`. Left joins are to **pre-grouped** rollups (firm_rollup,
  product_rollup, recall_lifecycle 1:1, history_rollup, recall_distribution_area) → **never fan out**.
- **Indexes:** `UNIQUE(recall_event_id)`; `btree(source, published_at)`; `btree(is_active)`;
  `btree(classification)`. **No standalone `published_at` index. No `(published_at, recall_event_id)` index.**

| Column | Postgres type | Nullable? | jsonb element shape | Notes |
|---|---|---|---|---|
| `recall_event_id` | text (inf, md5) | **NOT NULL** | — | UNIQUE; detail lookup key |
| `source` | text (inf) | **NOT NULL** | — | enum (5 values, uppercase) |
| `source_recall_id` | text (inf) | **NOT NULL** | — | native id; second half of md5 |
| `title` | text (inf) | NULLABLE | — | untested; editable field |
| `recall_reason` | text (inf) | NULLABLE | — | defect narrative |
| `url` | text (inf) | NULLABLE | — | CPSC/NHTSA may be NULL |
| `announced_at` | timestamptz (inf) | **NULLABLE by design** | — | ~20 FDA rows NULL; not_null test is severity=warn. Use for recall AGE. Model `| None`. |
| `published_at` | timestamptz (inf) | **NOT NULL** | — | hard contract date; sort/filter key |
| `classification` | text (inf) | NULLABLE | — | source-native (see enum table); btree-indexed |
| `risk_level` | text (inf) | NULLABLE | — | USDA-only |
| `lifecycle_status` | text (inf) | NULLABLE | — | NULL for CPSC/NHTSA |
| `is_active` | boolean (inf) | **NULLABLE (tri-state)** | — | NULL for CPSC/NHTSA; btree-indexed |
| `reason_category` | text (inf) | NULLABLE | — | USDA-only raw comma-joined FSIS reason |
| `distribution_scope` | text (inf) | **NOT NULL** | — | enum (4 values) |
| `distribution_states` | text (inf, scalar) | NULLABLE | — | `re.distribution_states` scalar string — **distinct from** `distribution_state_codes` below; do NOT conflate |
| `distribution_state_codes` | text[] | NULLABLE | — | from `recall_distribution_area` (LEFT JOIN); USPS 2-letter. **NULL** = no rda row (no parseable geo); **`{}`** = parsed, no states. FDA/USDA only. |
| `distribution_country_codes` | text[] | NULLABLE | — | ISO-3166-1 alpha-2, **foreign-only** ('US' excluded by design); NULL when no rda row |
| `hazards` | jsonb `[FLAGGED type]` | NULLABLE | (unknown) | `re.hazards` passthrough; selected as `jsonb` (CPSC populates it; FDA/USDA/NHTSA cast NULL jsonb). Treat as opaque jsonb array. |
| `product_upcs` | jsonb (inf) | NULLABLE | array of text (UPC) | **recall-level** UPCs (not per-product). Re-surfaced as `recall_product_upcs` in mart_product_search. |
| `corrective_action` | text (inf) | NULLABLE | — | — |
| `consequence_of_defect` | text (inf) | NULLABLE | — | (silver fixed the `conequence_defect` typo) |
| `primary_firm_name` | text (SQL: `(array_agg(...))[1]`) | NULLABLE | — | role-priority manufacturer>establishment>filer>importer>distributor>other; NULL for firmless recalls |
| `firm_count` | bigint (SQL: `count(distinct)`) | **NOT NULL** (coalesce 0) | — | — |
| `firms` | jsonb (SQL: `jsonb_agg(jsonb_build_object(...))`) | **NOT NULL** (coalesce `'[]'`) | array of `{firm_id: text, name: text, role: text, match_confidence: text}` ordered by role then canonical_name | maps to `list[FirmRef]` |
| `product_count` | bigint (SQL: `count(*)`) | **NOT NULL** (coalesce 0) | — | — |
| `product_names` | jsonb (SQL: `jsonb_agg distinct ... filter`) | **NULLABLE — NOT coalesced** | array of text | NULL when recall has no products / all null. **Default to `[]` in API model.** |
| `models` | jsonb (SQL: same) | **NULLABLE — NOT coalesced** | array of text | **Default to `[]`.** |
| `hins` | jsonb (SQL: same) | **NULLABLE — NOT coalesced** | array of text (Hull IDs, USCG) | **Default to `[]`.** |
| `first_seen_at` | timestamptz (inf) | NULLABLE (LEFT JOIN; 1:1 in practice) | — | pipeline-observation time, **NOT recall age** |
| `last_seen_at` | timestamptz (inf) | NULLABLE (LEFT JOIN) | — | — |
| `edit_count` | integer (inf) | NULLABLE (LEFT JOIN) | — | distinct content versions (1=never changed) |
| `is_currently_active` | boolean (inf) | **NULLABLE** | — | USDA+NHTSA only (NULL for CPSC/FDA/USCG; NHTSA NULL until deep-rescan). Model `| None`. |
| `was_ever_retracted` | boolean (inf) | **NULLABLE** | — | USDA+NHTSA only. Model `| None`. |
| `edit_event_count` | bigint (SQL: `count(*)`) | **NOT NULL** (coalesce 0) | — | raw history change-row count (USDA counts EN+ES); activity proxy |
| `has_been_edited` | boolean (SQL: `hr.source_recall_id is not null`) | **NOT NULL** | — | always true/false |

**NULL-vs-coalesce summary:** coalesced→NOT NULL: `firm_count`, `firms`, `product_count`,
`edit_event_count`, `has_been_edited`. Explicitly NULLABLE jsonb the API must default to `[]`:
`product_names`, `models`, `hins`. NULL-by-design scalars the API must model `| None`: `announced_at`,
`is_active`, `is_currently_active`, `was_ever_retracted` (and the array geo columns).

**Keyset sort keys:**
- `(published_at DESC, recall_event_id)` — the natural list order. **⚠️ NOT index-backed when
  unfiltered:** the only `published_at`-bearing index is the composite `(source, published_at)`, which
  the planner can only use for ordering when a leading `source` equality/range is present. An
  **unfiltered** `ORDER BY published_at DESC` falls to a full sort. **Index-backed only when
  `?source=` is also supplied.** Document this; accept the sort cost at corpus scale, or always
  require/encourage a `source` filter for deep pagination.
- Point lookup `recall_event_id` (UNIQUE) — for detail.
- Equality filters `is_active`, `classification` are each single-column btree-backed.

---

## Mart 2 — `mart_product_search`  → `GET /products/search`

- **Grain:** one row per `recall_product`. Built `recall_product rp` **INNER JOIN** a `recall_ctx` CTE
  selected from `mart_recall_summary` (so this mart depends on mart_recall_summary — a column rename
  there propagates here).
- **Indexes:** `UNIQUE(recall_product_id)`; `btree(recall_event_id)`; `btree(hin)`; `btree(model)`;
  `btree(upc)`; `GIN(search_vector)`.
- **`recall_product_id`** was migrated at this commit (`39dcbda`) to a **stable `(event, ordinal)`**
  key (CPSC) — good for keyset cursor stability across nightly rebuilds. **Treat as opaque** in the API.
  (NHTSA = 7-tuple md5; FDA = PRODUCTID; USDA/USCG = `recall_event_id`.)

| Column | Postgres type | Nullable? | jsonb element shape | Notes |
|---|---|---|---|---|
| `recall_product_id` | text (inf, surrogate) | **NOT NULL** | — | UNIQUE; opaque; keyset key |
| `recall_event_id` | text (inf, md5 FK) | **NOT NULL** | — | btree-indexed |
| `source` | text (inf) | **NOT NULL** | — | enum (5) |
| `source_recall_id` | text (inf) | **NOT NULL** | — | — |
| `product_name` | text (inf) | NULLABLE | — | coalesced to '' in tsvector |
| `product_description` | text (inf) | NULLABLE | — | coalesced to '' in tsvector |
| `model` | text (inf) | NULLABLE | — | btree-indexed; NHTSA/CPSC exact lookup |
| `type` | text (inf) | NULLABLE | — | five disjoint per-source domains (ADR 0036 D3); not a global enum. USDA = comma-joined processing text |
| `model_year` | `[FLAGGED int vs text]` | NULLABLE | — | undeclared; treat as string-or-int. USCG MIC build-year logic uses it. |
| `hin` | text (inf) | NULLABLE | — | btree-indexed; USCG Hull ID |
| `upc` | text (inf) | **NULLABLE — NULL for EVERY row today** ⚠️ | — | btree-indexed but **all-null**. Product-grain UPC unimplemented. Do NOT advertise `?upc=` product search; use `recall_product_upcs` containment instead. |
| `recall_title` | text (= `rc.title`) | NULLABLE | — | = mart_recall_summary.title |
| `classification` | text | NULLABLE | — | from recall_ctx |
| `risk_level` | text | NULLABLE | — | from recall_ctx (USDA-only) |
| `published_at` | timestamptz | **NOT NULL** | — | from recall_ctx |
| `url` | text | NULLABLE | — | from recall_ctx |
| `is_active` | boolean | **NULLABLE (tri-state)** | — | from recall_ctx |
| `firm_name` | text (= `rc.primary_firm_name`) | NULLABLE | — | NULL for firmless recalls |
| `recall_product_upcs` | jsonb (= `rc.product_upcs`) | NULLABLE | array of text (UPC) | **recall-level** UPC array — the real UPC search path (containment), since the per-product `upc` column is all-null |
| `search_vector` | tsvector (SQL: `to_tsvector('english', ...)`) | **NOT NULL** | — | GIN-indexed; built from product_name + product_description + recall_title + firm_name (each coalesced to ''). **No pg_trgm (ADR 0037) → token/prefix FTS only, NO fuzzy/typo search.** |

**Keyset sort keys:**
- FTS path: `(ts_rank_cd(search_vector, query) DESC, recall_product_id)` — **rank is NOT an ordered
  btree path** (GIN serves the `@@` match, not the sort), so relevance-ordered keyset is **not
  index-backed**; the sort is on the (small) matched set. Use `websearch_to_tsquery('english', :q)`
  (injection-safe, never raises).
- Identifier path: exact `hin` / `model` btree equality (each indexed); `upc` btree exists but column
  is all-null. Order `(published_at DESC, recall_product_id)` for the identifier path.
- Point lookup `recall_product_id` (UNIQUE) is the clean keyset key.

---

## Mart 3 — `mart_firm_profile`  → `GET /firms/{id}`

- **Grain:** one row per canonical `firm_id` (the 6b cross-source cluster id) — this IS the cross-source
  rollup (a Honda/Tyson under several sources collapses to one row).
- **Indexes:** `UNIQUE(firm_id)`; `btree(normalized_name)` (non-unique).
- `firm_id = md5(upper(trim(name)))` (additive crosswalk canonical id). Treat as opaque path param.

| Column | Postgres type | Nullable? | jsonb element shape | Notes |
|---|---|---|---|---|
| `firm_id` | text (inf, md5) | **NOT NULL** | — | UNIQUE; path-param key |
| `canonical_name` | text (inf) | **NOT NULL** | — | — |
| `normalized_name` | text (inf) | **NOT NULL** | — | display representative, **not unique** (two spellings can clean to one); btree-indexed |
| `observed_names` | jsonb (inf) | NULLABLE | array of text (every raw spelling) | — |
| `observed_company_ids` | jsonb (SQL: unnested as text) | NULLABLE | array of text (FDA FEI numeric / USDA `M1234`/`M1+P1` / USCG 3-char MIC; disjoint namespaces) | sidecar join key |
| `alternate_names` | jsonb (inf) | NULLABLE | array of text (DBA/brand aliases) | nullable, untested |
| `total_recalls` | bigint (SQL: `count(distinct)`) | **NOT NULL** (coalesce 0) | — | — |
| `active_recalls` | bigint (SQL: `count(distinct) filter(is_active)`) | **NOT NULL** (coalesce 0) | — | — |
| `first_recall_at` | timestamptz (SQL: `min(published_at)`) | **NULLABLE — NOT coalesced** | — | NULL for firm with zero matched recalls (LEFT JOIN) |
| `last_recall_at` | timestamptz (SQL: `max(published_at)`) | **NULLABLE — NOT coalesced** | — | — |
| `roles` | jsonb (SQL: `jsonb_agg(distinct role)`) | **NULLABLE — NOT coalesced** | array of text (role enum) | default to `[]` in API |
| `recalls_by_source` | jsonb (SQL: `jsonb_object_agg(source, cnt)`) | **NULLABLE — NOT coalesced** | object `{source: int}` (keys ⊂ 5-source set) | maps to `dict[str, int]`; default `{}` |
| `distinct_products` | numeric (SQL: `sum()` over bigint) | **NOT NULL** (coalesce 0) | — | integer-valued; API may model as `int` |
| `firm_usda_attributes` | jsonb (SQL: `jsonb_agg(to_jsonb(ea)) filter`) | **NULLABLE — NOT coalesced** | array of full USDA establishment rows | **USDA** (renamed from `establishment_attributes`, R5) |
| `firm_uscg_attributes` | jsonb (SQL: `jsonb_agg(to_jsonb(ma)) filter`) | **NULLABLE — NOT coalesced** | array of full USCG manufacturer/MIC rows | **USCG** (renamed from `manufacturer_attributes`, R5) |
| `firm_fda_attributes` | jsonb (SQL: `jsonb_agg(to_jsonb(fa)) filter`) | **NULLABLE — NOT coalesced** | array of full FDA FEI rows | **FDA** (renamed from `fda_attributes`, R5) |

**⚠️ The three sidecar OUTPUT columns are now source-aligned: `firm_usda_attributes` (USDA) /
`firm_uscg_attributes` (USCG) / `firm_fda_attributes` (FDA)** — gold-readiness R5 (07 #5) was applied
upstream pre-go-live, so the mart columns and the API fields share these names 1:1. The pre-rename
names (`establishment_attributes`=USDA, `manufacturer_attributes`=USCG, `fda_attributes`=FDA) are
historical only. The sidecar arrays are NOT coalesced → default each to `[]` and use per-source
sub-models (the shapes differ; a single shared SidecarAttributes model is wrong).

> **NOTE — rename APPLIED (gold-readiness R5).** recommendation 07 #5 (rename the mart sidecar output
> columns to `firm_usda_attributes` / `firm_uscg_attributes` / `firm_fda_attributes`) was applied
> upstream pre-go-live and is live on the read-only role. C7's `queries/firms.py` / `models/firms.py`
> use these names, verified live against the mart; the pre-rename names above are historical only.

**Keyset sort keys:** only `firm_id` (UNIQUE, point lookup/keyset) and `normalized_name` (btree) are
indexed. There is no `published_at` or recall-count index — keyset by anything else is not index-backed.
`GET /firms/{id}` is a single point read by `firm_id`; no pagination needed.

---

## Firm sidecar mapping (the jsonb element shapes for `mart_firm_profile`)

Each sidecar is a `materialized='table'` CURRENT view (`dbt_valid_to is null`) over an SCD-2 snapshot.
`to_jsonb(row)` emits **all** columns below. Shapes **differ by source** → per-source Pydantic sub-models.

| Mart output column | Source table | Source | Join key (→ `observed_company_ids` element) | Element object keys (full row, in select order) |
|---|---|---|---|---|
| `firm_usda_attributes` | `firm_usda_attributes` | USDA (FSIS establishment) | `establishment_id` (= FSIS establishment_number) | `establishment_id, establishment_name, address, city, state, zip, county, fips_code, geolocation, latest_mpi_active_date, grant_date, status_regulated_est, size, district, circuit, activities, dbas` |
| `firm_uscg_attributes` | `firm_uscg_attributes` | USCG (boat MIC) | `mic` (3-char) | `mic, company_name, dba, parent_company, parent_mic, past_company_1, past_company_2, past_company_3, address, city, state, zip, country, status, in_business, out_of_business, date_modified, uscg_directory_id, detail_url, mic_has_prior_holder (bool), mic_oob_recycled (bool), mic_renamed_not_recycled (bool), prior_holders (jsonb array of text)` |
| `firm_fda_attributes` | `firm_fda_attributes` | FDA (FEI) | `firm_fei_num::text` (cast; FEI is bigint, an expression index `((firm_fei_num::text))` backs the join) | `firm_fei_num, firm_legal_nam, firm_city_nam, firm_state_cd, firm_state_prvnc_nam, firm_country_nam, firm_postal_cd, firm_line1_adr, firm_line2_adr, firm_surviving_nam, firm_surviving_fei` |

Notes: USDA `status_regulated_est` ∈ {`''`, `Inactive`}. USCG `mic_oob_recycled` ⊂ `mic_has_prior_holder`.
FDA `firm_state_cd`/`firm_postal_cd`/`firm_surviving_*` are legitimately nullable (state ~86.8% pop).
CPSC and NHTSA have **NO sidecar** (name-keyed, no structural anchor) — never expect a CPSC/NHTSA block.
Model all sidecar fields as optional except the join key; treat the embedded jsonb objects loosely
(the API does not need to validate every government attribute).

---

## Deferred `/stats/*` family — fct_* + dim_date (compact reference)

All `fct_*` are `materialized='view'` (recomputed, unindexed) **except** `fct_recalls_by_geography`
(table, indexed) and `dim_date` (table). The serving API v1 does **not** ship these; this is for the
deferred dashboard endpoints gated on the website chart inventory.

| Mart | Materialized | Grain | Key columns | `'ALL'` rollup? | Trap |
|---|---|---|---|---|---|
| `fct_recalls_by_month` | view | (month_start, source) | `period, source, event_count` | **Yes** (GROUPING SETS) | filter `source` deliberately or double-count ALL+per-source |
| `fct_recalls_by_week` | view | (iso_week_start Mon, source) | `period, source, event_count` | **Yes** | same |
| `fct_recalls_by_year` | view | (year_start, source) | `period, source, event_count` | **Yes** | same |
| `fct_recalls_monthly_trend` | view | (source, month) dense 0-filled spine | `month, source, event_count, rolling_3mo_avg, rolling_12mo_avg, event_count_year_ago, yoy_pct_change` | **No** (per-source only; no ALL) | `event_count_year_ago`/`yoy_pct_change` NULL for first 12 months / zero-prior |
| `fct_recalls_by_classification` | view | (source, classification, risk_level) | `source, classification, risk_level, event_count` | **Yes** | classification/risk_level NULLABLE (unclassified bucket); enums NOT conformed — `'ALL'` mixes incomparable domains, descriptive only |
| `fct_recall_status` | view | (source, status) | `source, status, event_count` | **Yes** | `status` ∈ {active, inactive, unknown}; CPSC/NHTSA → unknown |
| `fct_recalls_by_geography` | **table** (indexed) | (geography_basis, source, state_code) | `geography_basis, source, state_code, recall_count` | **Yes** | `geography_basis` ∈ {`distribution`, `firm_registration`} (renamed from firm_location C17). **Per-state counts SUM TO MORE than distinct recalls** (multi-state firm footprint). NEVER read as consumer impact. distribution = FDA/USDA only; firm_registration = USDA/USCG/FDA + name-merged. Indexes: `(geography_basis, source, state_code)`, `(state_code)`. |
| `fct_recalls_by_country` | view | (source, country_code) | `source, country_code, recall_count` | **Yes** (`source` ∈ {FDA, USDA, ALL}) | FDA+USDA only. `'US'` cell is **derived** (heuristic regex on 'nationwide' + scope + state codes), not stored. Per-country inflation (multi-valued reach). |
| `fct_units_recalled` | view | (source, unit_category, month) | `source, unit_category, period, recalls_with_units, total_units, avg_units_per_recall, max_units` | **No** (measure source-incommensurable) | `source` ∈ {NHTSA, USCG, FDA, USDA} (no CPSC, no ALL). MUST filter by source; NEVER sum across `unit_category` (count/weight/volume/grouping). `total_units` is a magnitude sum, NOT unique items. **⚠️ `_gold.yml` description is STALE** (says basis-aware sum/max); SQL is authoritative: `units = max(quantity_value)`, basis-agnostic (2026-06-09). |
| `fct_recalls_by_firm` | view | one row per canonical firm | `firm_id, canonical_name, event_count(=total_recalls), active_recalls, product_count(=distinct_products), first_recall_at, last_recall_at, event_count_rank` | **No** (no source dimension) | reads mart_firm_profile (gold-on-gold); ready-made leaderboard |
| `dim_date` | **table** | one row per calendar day | `date_day (UNIQUE), year, quarter, month, month_name, iso_week, iso_day_of_week, day_name, day_of_year, iso_week_start, month_start, quarter_start, year_start, is_weekend, us_fiscal_year` | n/a | spine **1940-01-01 .. current_year+2** (SQL; `_gold.yml` says 1960 — STALE). The API never needs dim_date. |

`fct_*` source `accepted_values` differ per mart — validate endpoint `source` params against the
specific mart's domain (e.g. units = {NHTSA,USCG,FDA,USDA}; country = {FDA,USDA,ALL}; trend has no ALL).

---

## Quick-reference: what the API must do

- Compute `recall_event_id = md5(f"{SOURCE_UPPER}|{recall_id}")` for the detail lookup; hit `UNIQUE(recall_event_id)`. No new index.
- Default to `[]`: `product_names`, `models`, `hins` (mart_recall_summary); `roles`,
  `firm_usda_attributes`, `firm_uscg_attributes`, `firm_fda_attributes` (mart_firm_profile); default `{}`: `recalls_by_source`.
- Model `| None`: `announced_at`, `is_active`, `is_currently_active`, `was_ever_retracted`,
  `first_recall_at`, `last_recall_at`, geo arrays, `primary_firm_name`, `firm_name`.
- `firms` and `firm_count`, `product_count`, `edit_event_count`, `has_been_edited`, `total_recalls`,
  `active_recalls`, `distinct_products` are non-null (coalesced).
- Product UPC search → `recall_product_upcs` jsonb containment, NOT the all-null `upc` column.
- No fuzzy/typo search anywhere (no pg_trgm). FTS via `websearch_to_tsquery`.
- Unfiltered `/recalls?order=published_at` is a full sort (no standalone index) — index-backed only with `?source=`.
- Sidecar mart columns are source-aligned (R5 applied): `firm_usda_attributes`(USDA)/`firm_uscg_attributes`(USCG)/`firm_fda_attributes`(FDA).
