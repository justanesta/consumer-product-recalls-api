# 07 — Gold-Layer / Mart Change Recommendations (cross-repo)

> **Audience:** the operator of the **pipeline repo** `justanesta/consumer-product-recalls`
> (`@feature/pre-go-live-validation`, commit `39dcbda`). **Not** the API repo.
> **The `recalls-api` repo owns no schema, no migrations, no dbt** — it reads the gold marts and
> cannot apply any of these. Every change below is a pipeline-repo change (dbt
> `config(indexes=[…])` co-located in the mart model, or an Alembic migration in
> `migrations/versions/`), following the same convention as ADR 0038 / index_audit.md / migration
> 0033.
>
> **Grounding:** facts traced to `01-ground-truth-gold-marts.md` (the schema contract; cited as
> "01 — Mart N"), `02-plan-reconciliation.md`, the mart SQL at commit `39dcbda`
> (`dbt/models/gold/mart_*.sql`, `fct_units_recalled.sql`, `_gold.yml`), `migrations/versions/0033_recalls_app_role_posture.py`,
> ADR 0038, `documentation/index_audit.md`, `documentation/gold_design_notes.md`.
>
> **Blocker status:** **NONE of these block v1 EXCEPT #2 (the read-only role)**, which is a hard
> deploy prerequisite — the API must not reuse the read+write `recalls_app` role (migration 0033).
> Everything else is performance/clarity/hygiene the operator can apply on the normal nightly cadence.

Sibling docs: **03** API contract · **04** implementation · **05** testing/CI · **06** deploy/ops ·
**08** commit plan. This doc is consumed by 06 (the read-only role is a deploy gate) and 04 (the
ETag anchor in #6 informs the cache-header code).

---

## How the operator applies these (two mechanisms, per ADR 0038 §6)

| Object class | Mechanism | Re-applied when | Convention source |
|---|---|---|---|
| **Index on a `mart_*` table** | add to that model's `{{ config(indexes=[…]) }}` block | every `dbt build` (gold tables are dropped + recreated each run) | ADR 0038 §6; index_audit.md "Gold" |
| **GIN/expression index dbt can't express as a column list** | dbt `post_hook` on the model (the `firm_fda_attributes((firm_fei_num::text))` precedent) | every `dbt build` | index_audit.md "Why the functional index" |
| **Role / grant / DB-level posture** | Alembic migration in `migrations/versions/` (operator-run, never in CI) | once, on `alembic upgrade head` | migration 0033 |
| **A new column / `gold_meta` table** | dbt model change (`+` a `select` expression or a new `mart_`/meta model) | every `dbt build` | ADR 0038 §2 |

dbt index blocks use Postgres index DDL implicitly: `{'columns': [...], 'unique': bool}` →
btree; `{'columns': [...], 'type': 'gin'}` → GIN (see `mart_product_search.sql` lines 3–10 for the
live pattern). dbt cannot express `DESC` ordering, partial predicates, or expression keys in the
column-list form — those go through a `post_hook` (shown per-rec below).

---

## Priority summary

| # | Recommendation | Priority | Blocks v1? | Mechanism |
|---|---|---|---|---|
| **2** | New **read-only role** for the API (mirror 0033, `GRANT SELECT` only + `default_transaction_read_only`) | **Required (deploy)** | **YES** | Alembic migration `0034` |
| **1** | `(published_at DESC, recall_event_id)` index on `mart_recall_summary` (back the headline keyset sort) | **Recommended** | No | dbt `post_hook` |
| **3** | GIN index on `mart_recall_summary.product_upcs` (back recall-level UPC containment) | **Recommended** | No | dbt `post_hook` |
| **6** | `gold_meta.rebuilt_at` (deterministic ETag / Last-Modified anchor) | **Recommended** | No | new dbt model |
| **4** | Coalesce `product_names`/`models`/`hins` to `'[]'::jsonb` (uniform non-null contract) | **Optional (consistency)** | No | mart SQL edit |
| **5** | Rename sidecar OUTPUT columns → `firm_usda_attributes`/`firm_uscg_attributes`/`firm_fda_attributes` | **Recommended (pre-go-live, before the API's first openapi.json freeze)** | No | **dbt model edit** (`mart_firm_profile.sql`), NOT Alembic — **API-breaking if applied after freeze** |
| **7** | Trigram/expression index for `?firm=` ILIKE substring | **Conditional** (only if hot; pg_trgm disabled today) | No | extension + dbt `post_hook` |
| **8** | Plan-C0c-dbt `(source, source_recall_id)` composite index | **DECLINE** | n/a | — |
| **9** | FTS rank-keyset stability (rank is query-time, not stored) | **API-side note** — no mart change | No | — |
| **10** | Doc-hygiene: stale `fct_units_recalled` + `dim_date` descriptions; missing `fct_recalls_by_country` | **Recommended (hygiene)** | No | `_gold.yml` / doc edits |

---

## #2 — NEW read-only role for the API  · **REQUIRED (the only deploy blocker)**

**Problem (API pain).** The existing `recalls_app` role (migration `0033_recalls_app_role_posture.py`)
is the **pipeline's READ+WRITE runtime role**: it carries `GRANT SELECT, INSERT, UPDATE ON ALL TABLES`
(0033 step 2, line 82), `TRUNCATE` on the two crosswalk tables (step 4), and `ALTER DEFAULT
PRIVILEGES … GRANT SELECT, INSERT, UPDATE` so **future** tables inherit write (step 3). An open,
no-auth, public-internet API that connects as `recalls_app` would expose `INSERT`/`UPDATE` to anyone
who reached a (future) write path or a SQL flaw. The API is contractually read-only (ADR 0024 §1,
ADR 0025); it **must not** reuse `recalls_app`.

**Exact change.** Provision a dedicated `recalls_readonly` role as a **new Alembic migration**
(`migrations/versions/0034_recalls_readonly_role.py`), mirroring 0033's NOLOGIN-shell + SQL-create
pattern (so Neon does **not** add it to `neon_superuser`, whose `pg_write_all_data` would silently
re-grant write — see 0033 lines 16–22), but `GRANT SELECT` only and `default_transaction_read_only=on`
as a defense-in-depth belt. The operator sets the password + `LOGIN` out-of-band exactly as for 0033.

```python
r"""recalls_readonly — dedicated read-only role for the public serving API (recalls-api).

Separate from recalls_app (0033, the pipeline READ+WRITE runtime role). The open, no-auth API
connects as this role: SELECT only, plus a session-level default_transaction_read_only belt so even
a SELECT-able function or a planner surprise cannot mutate. Created as a NOLOGIN SQL shell for the
SAME reason as 0033: a SQL-created role is NOT added to neon_superuser (whose pg_write_all_data would
re-grant write), and no password literal is committed. Operator activates once, out-of-band:
    ALTER ROLE recalls_readonly LOGIN PASSWORD '<strong pw>';
Then expose its connection string to the API as NEON_DATABASE_URL_RO (SecretStr; see API doc 06).

Runs as the OWNER (operator-run, never in CI). Idempotent on the clean path.

Revision ID: 0034
Revises: 0033
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create as a NOLOGIN shell if absent; fail loudly on a pre-existing *dirty* role (any admin
    #    attribute or neon_superuser membership) — a non-superuser owner cannot restrict it, so the
    #    fix is delete-in-Neon-console + re-run, landing on the clean CREATE path (mirrors 0033 §1).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'recalls_readonly') THEN
                IF EXISTS (
                    SELECT 1 FROM pg_roles
                    WHERE rolname = 'recalls_readonly'
                      AND (rolsuper OR rolcreatedb OR rolcreaterole
                           OR rolreplication OR rolbypassrls)
                ) OR EXISTS (
                    SELECT 1 FROM pg_auth_members am
                    JOIN pg_roles g ON g.oid = am.roleid
                    JOIN pg_roles m ON m.oid = am.member
                    WHERE m.rolname = 'recalls_readonly' AND g.rolname = 'neon_superuser'
                ) THEN
                    RAISE EXCEPTION USING MESSAGE =
                        'recalls_readonly exists with elevated privileges; a non-superuser owner '
                        || 'cannot fully restrict it. Delete the role in the Neon console and '
                        || 're-run alembic upgrade head to recreate it clean via SQL.';
                END IF;
            ELSE
                CREATE ROLE recalls_readonly NOLOGIN;
            END IF;
        END $$;
        """
    )

    # 2. Read-only grants: SELECT on all CURRENT tables. USAGE on schema (needed to resolve objects).
    #    NO INSERT/UPDATE/DELETE/TRUNCATE, NO sequence privileges (read-only never advances a seq).
    op.execute("GRANT USAGE ON SCHEMA public TO recalls_readonly;")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO recalls_readonly;")

    # 3. FUTURE owner-created tables inherit SELECT (a new mart is readable without re-granting).
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO recalls_readonly;"
    )

    # 4. Belt-and-braces: force every session opened by this role to read-only. Blocks any write at
    #    the transaction level even if a grant leaks. The role can still SET it back, but the API
    #    never does; combined with SELECT-only grants this is a hard read-only posture.
    op.execute("ALTER ROLE recalls_readonly SET default_transaction_read_only = on;")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'recalls_readonly') THEN
                ALTER ROLE recalls_readonly RESET default_transaction_read_only;
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    REVOKE SELECT ON TABLES FROM recalls_readonly;
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM recalls_readonly;
                REVOKE ALL ON SCHEMA public FROM recalls_readonly;
                DROP ROLE recalls_readonly;
            END IF;
        END $$;
        """
    )
```

Operator activation (mirrors operations.md "Restricted app role"; Neon needs a plaintext password):

```bash
alembic upgrade head
# then, out-of-band (do NOT commit the password):
psql "$NEON_OWNER_URL" -c "ALTER ROLE recalls_readonly LOGIN PASSWORD '<strong pw>';"
# hand the API the resulting connection string as NEON_DATABASE_URL_RO (see #2 open items below)
```

**API benefit.** A genuine least-privilege posture: the open API cannot mutate gold even under a SQL
flaw or a malicious input that reaches a write path. Satisfies ADR 0024 §1 / ADR 0025 read-only intent
without the API repo owning any schema.

**Cost / risk.** One small migration; zero impact on the pipeline runtime (which keeps using
`recalls_app`). Risk: if the operator points the API at `recalls_app` "to save a step", the read-only
contract is silently void — call this out in 06's deploy checklist. `GRANT SELECT ON ALL TABLES`
grants read on **all** public tables including bronze/silver/audit; if the operator wants to restrict
the API to gold marts only, narrow step 2 to an explicit table list (the four serving objects:
`mart_recall_summary`, `mart_product_search`, `mart_firm_profile`, plus any `fct_*`/`gold_meta` the
API later reads) and add a matching `ALTER DEFAULT PRIVILEGES`. Default-broad SELECT is fine for a
read-only role; gold-only is stricter. **Operator's call.**

**Priority: Required for deploy.** This is the single hard prerequisite; #1–#10 are not.

**Open items to confirm with the operator (mirrors 02 "MUST re-verify"):**
- Exact role name (`recalls_readonly` proposed) and whether to scope grants to gold-only vs all tables.
- **Pooled (PgBouncer `-pooler`) vs direct Neon endpoint** for the connection string. A small async
  pool that holds connections (04/06: `pool_size~5`) generally wants the **direct** endpoint; the
  pooled endpoint is for many short-lived connections. Confirm which the operator exposes.
- Env-var name the API should read: **`NEON_DATABASE_URL_RO`** proposed, to parallel the pipeline's
  `NEON_DATABASE_URL` (`SecretStr`, fail-loud at boot). Decide and document in API settings (04/06).

---

## #1 — `(published_at DESC, recall_event_id)` index on `mart_recall_summary`  · **Recommended**

**Problem (API pain).** The headline `GET /recalls` list orders `(published_at DESC, recall_event_id)`
(01 — Mart 1 "Keyset sort keys"). The **only** `published_at`-bearing index is the composite
`(source, published_at)` (mart SQL line 6). Per the leftmost-prefix rule (index-optimization.md
"Composite Index Column Ordering"), the planner can use that composite for ordering **only when a
leading `source` equality is present**. An **unfiltered** `/recalls` (no `?source=`) therefore falls
to a **full Sort node over the whole mart** (sargable-queries / explain-plan-reading.md: a `Sort` with
no supporting index). This is doc 02's single **blocker-severity** caveat. Keyset pagination is
correct, but the *first page sort itself* is not index-backed when unfiltered.

**Exact change.** Add a dedicated descending composite that exactly matches the sort tuple. dbt's
column-list config **cannot express `DESC`**, so use a `post_hook` (the index_audit.md precedent for
the one index the column-list form can't express). Edit `dbt/models/gold/mart_recall_summary.sql`:

```python
{{ config(
    materialized='table',
    indexes=[
      {'columns': ['recall_event_id'], 'unique': True},
      {'columns': ['source', 'published_at']},
      {'columns': ['is_active']},
      {'columns': ['classification']},
    ],
    post_hook="create index if not exists {{ this.name }}_published_at_desc_evt
               on {{ this }} (published_at desc, recall_event_id)"
) }}
```

> `recall_event_id` is the keyset tiebreaker and is UNIQUE, so `(published_at DESC, recall_event_id)`
> is a total order — the seek predicate `(published_at, recall_event_id) < (:last_pub, :last_id)`
> becomes a pure index range scan, no Sort node. dbt re-creates the post_hook index on every rebuild,
> so it stays in lockstep with the table (no `CONCURRENTLY` needed — the table is freshly built each
> run, not live-mutated). `if not exists` keeps the hook idempotent within a run.

**API benefit.** Turns the unfiltered headline `/recalls` first page + every keyset page into an
**Index Scan** (no full sort), and makes deep pagination O(log n) seek instead of re-sorting the
corpus per page. Removes the need to *force* a `?source=` filter to get acceptable latency.

**Cost / risk.** One extra btree (~one key + tid per recall row; tens of thousands of rows per
02 — sizing is unverified, but small). Marginal `dbt build` time + storage. The existing
`(source, published_at)` index stays (it still backs `?source=`-filtered ordering and `?source=`
equality). No correctness risk. Per ADR 0038 §6 / index_audit.md Phase-7, if traffic shows the
unfiltered path is rarely hit (most clients pass `?source=`), this index can be dropped later — but
add it now because the unfiltered list **is** the documented default landing query.

---

## #3 — GIN index on `mart_recall_summary.product_upcs`  · **Recommended**

**Problem (API pain).** UPC search routes to **recall-level jsonb containment**, not the per-product
`upc` column (which is `NULL` for **every** row today — 01 — Mart 2, ADR-confirmed in 02). The real
path is `recall_product_upcs @> :upc` (a jsonb array containment); that column on `mart_product_search`
is `rc.product_upcs` pulled verbatim from `mart_recall_summary.product_upcs` (mart_product_search.sql
lines 35, 58). **Neither `mart_recall_summary.product_upcs` nor the re-surfaced
`mart_product_search.recall_product_upcs` has any index** (index_audit.md "Gold" lists neither). A
jsonb `@>` containment with no GIN index is a **Seq Scan with a per-row containment recheck**
(index-optimization.md "GIN index … array/JSONB containment"). The all-null `upc` btree (mart line 8)
does nothing for the real search path.

**Exact change.** The standard jsonb-containment GIN. Containment (`@>`) works with the default
`jsonb_ops` opclass. Add to the model the API actually queries for UPC search — **`mart_product_search`**
is the `GET /products/search` table, so index `recall_product_upcs` there (and optionally the source
column on `mart_recall_summary` if any path queries it directly). Edit `mart_product_search.sql`:

```python
{{ config(
    materialized='table',
    indexes=[
      {'columns': ['recall_product_id'], 'unique': True},
      {'columns': ['recall_event_id']},
      {'columns': ['hin']},
      {'columns': ['model']},
      {'columns': ['upc']},
      {'columns': ['search_vector'], 'type': 'gin'},
      {'columns': ['recall_product_upcs'], 'type': 'gin'},   -- NEW: recall-level UPC containment
    ]
) }}
```

> dbt **can** express this one as a column-list `{'type': 'gin'}` (same form as the `search_vector`
> GIN), so no post_hook needed. For a tighter index, a `post_hook` with the path-ops opclass
> (`USING gin (recall_product_upcs jsonb_path_ops)`) is smaller and faster for pure `@>` but supports
> only containment — fine here since `@>` is the only operator used. Default `jsonb_ops` is the
> safe choice; switch to `jsonb_path_ops` if the index gets large.

**API benefit.** `?upc=` becomes a **Bitmap Index Scan** on the GIN instead of a full-table jsonb
recheck. This is the honest, supported UPC path the OpenAPI copy points at (01 quick-ref:
"Product UPC search → `recall_product_upcs` jsonb containment, NOT the all-null `upc` column").

**Cost / risk.** GIN is larger and slower to build than btree, and rebuilt each `dbt build` — but
the mart is small and built once nightly, so build cost is amortized. Many recalls have empty/NULL
`product_upcs` (UPCs are CPSC-heavy), so the GIN is sparse and cheap. No correctness risk. **Decline
the all-null `upc` btree** as a separate cleanup (it indexes a 100%-NULL column — index_audit.md
lists it but it serves nothing today); that is an Optional prune, not part of this rec.

---

## #6 — `gold_meta.rebuilt_at` for deterministic ETag / Last-Modified  · **Recommended**

**Problem (API pain).** 06's HTTP caching keys `Cache-Control` / `ETag` / `Last-Modified` off the
nightly ~03:00 UTC transform rebuild (locked decision 14). But the API has **no clean, queryable
"when was gold last rebuilt" signal** — `recall_lifecycle.last_seen_at` is per-recall pipeline-
observation time (01 — Mart 1: "NOT recall age"), not a layer-wide rebuild timestamp, and reading
`MAX(published_at)` is a data-content date, not a build time. Without a stable anchor the API would
have to fabricate an ETag (e.g. hash a page), defeating the cheap "did gold change since 03:00?"
conditional-GET / `304 Not Modified` story.

**Exact change.** Emit a one-row meta table at the end of the gold build. A tiny dbt model
`dbt/models/gold/gold_meta.sql`:

```python
{{ config(materialized='table') }}

-- gold_meta — one row, the gold-layer rebuild stamp. Set to the dbt run start time so every mart
-- built in the same `dbt build` shares one deterministic rebuilt_at. Read by the serving API
-- (recalls-api) to compute a layer-wide ETag / Last-Modified for conditional GET / 304.

select
    '{{ run_started_at.astimezone(modules.pytz.UTC).isoformat() }}'::timestamptz as rebuilt_at,
    '{{ var("gold_schema_version", "1") }}'::text                               as schema_version
```

> `run_started_at` is the dbt run timestamp (identical across all models in one `dbt build`), so
> every mart in a run shares one `rebuilt_at` — exactly the deterministic, monotonic anchor the API
> needs. The API reads `SELECT rebuilt_at, schema_version FROM gold_meta` once (cache it for the
> process / TTL), sets `Last-Modified: <rebuilt_at>` and `ETag: "<schema_version>-<rebuilt_at epoch>"`,
> and answers `If-None-Match` / `If-Modified-Since` with `304`. **Add `gold_meta` to the read-only
> role's SELECT set** (it's covered by the broad `GRANT SELECT ON ALL TABLES` in #2; if the operator
> scopes to gold-only, include it).

**API benefit.** Deterministic, layer-wide cache validators that flip exactly once per nightly
rebuild → cheap `304`s, lower DB load, the caching story in 06 becomes real instead of best-effort.

**Cost / risk.** Trivial — a one-row table, negligible build cost, no schema coupling to the marts.
Alternative considered & **rejected**: a `rebuilt_at` column on every mart row (wasteful duplication
across all rows; harder for the API to read one value). A single `gold_meta` table is the clean shape.
Small open item: confirm dbt's `run_started_at`/`modules.pytz` are available in the project's dbt
version (they are in dbt-core ≥1.x); if not, use `'{{ run_started_at }}'::timestamptz` with the
project timezone, or a `post_hook` `update`/`insert` of `now()`.

---

## #4 — Coalesce `product_names` / `models` / `hins` to `'[]'::jsonb`  · **Optional (consistency)**

**Problem (API pain).** In `mart_recall_summary`, `firms` is coalesced to `'[]'::jsonb` (mart line 97)
but `product_names` / `models` / `hins` are **NOT** coalesced (lines 100–102) — they are `NULL` when a
recall has no products (01 — Mart 1; confirmed 02). The API works around this with
`Field(default_factory=list)` on those three (locked decision 8), so the wire contract is already
uniform. This rec only removes the asymmetry **at the source** so the jsonb-array contract is uniform
*in the database* (every jsonb-array column non-null), matching the `firms`/`firm_count` coalesce
pattern already in the same model.

**Exact change.** Wrap the three rollup selects in `coalesce(..., '[]'::jsonb)` in the final select of
`mart_recall_summary.sql` (lines 100–102):

```sql
    coalesce(pr.product_names, '[]'::jsonb) as product_names,
    coalesce(pr.models,        '[]'::jsonb) as models,
    coalesce(pr.hins,          '[]'::jsonb) as hins,
```

**API benefit.** Marginal — the API already defaults these to `[]`. The benefit is a self-consistent
mart (no "some jsonb arrays are null, some aren't" footgun for any *future* direct-gold consumer or
the website), and one fewer place the API's `default_factory` is load-bearing.

**Cost / risk.** Zero behavioral change for the API (it already coerces NULL→`[]`). Tiny SQL diff.
**Do NOT do this if the operator wants to preserve the NULL-vs-`[]` distinction** as a "had no
products at all" vs "had products, none named" signal — but `product_count` already carries that
distinction (it's a separate coalesced column, line 99), so the NULL is pure noise here. Safe to apply.
**Priority: Optional** — the API does not need it; it is hygiene.

---

## #5 — Rename sidecar OUTPUT columns to `firm_{usda,uscg,fda}_attributes`  · ✅ **APPLIED upstream (pre-freeze)** — was: Recommended pre-go-live, API-BREAKING after freeze

**Problem (API pain).** `mart_firm_profile`'s sidecar output columns are
`establishment_attributes` (= **USDA** FSIS), `manufacturer_attributes` (= **USCG** boat MIC),
`fda_attributes` (= **FDA** FEI) — mart SQL lines 49–51, 125–127. The `establishment`/`manufacturer`
naming is **semantically confusing**: "manufacturer" reads like a generic role but means USCG-only,
and "establishment" means USDA-only. The plan (C19) **expected** these to already be renamed
`firm_{usda,uscg,fda}_attributes`; doc 02 flagged that as a **blocker-severity correction** — the
rename hit the **silver source tables only**, **not** the mart output. So the API must use the
confusing names verbatim (locked decision 6).

**Status: ✅ APPLIED upstream (R5).** The mart output columns are now
`firm_usda_attributes` / `firm_uscg_attributes` / `firm_fda_attributes`; locked decision 6 is
superseded and the shipped API (C7 — `queries/firms.py` / `models/firms.py`) uses the new names.

**It is a dbt model edit, NOT an Alembic migration.** The gold marts are dbt `materialized='table'`
models (dropped + recreated each `dbt build`); the `migrations/versions/*.py` Alembic migrations are
**bronze-layer** role/DDL posture. This rename touches **only** `dbt/models/gold/mart_firm_profile.sql`
(plus its `_gold.yml`) — no migration, no Alembic revision.

**VERIFIED zero downstream dbt breakage.** The **only** consumer of `mart_firm_profile` in the dbt DAG
is `fct_recalls_by_firm.sql`, and it selects only
`firm_id, canonical_name, total_recalls, active_recalls, distinct_products, first_recall_at,
last_recall_at` — it does **NOT** reference any of the three sidecar columns. So renaming the sidecar
outputs cannot break any downstream dbt model.

**Exact change — exactly 2 spots in `dbt/models/gold/mart_firm_profile.sql`.** (1) the three
`as <name>` aliases in the `firm_attrs` CTE, and (2) the three `fa.<name>` columns in the final
`select`. Then `dbt build --select mart_firm_profile+`:

```sql
-- (1) in the firm_attrs CTE:
        jsonb_agg(est_json order by establishment_id) filter (...) as firm_usda_attributes,
        jsonb_agg(mfr_json order by mic)              filter (...) as firm_uscg_attributes,
        jsonb_agg(fda_json order by firm_fei_num)     filter (...) as firm_fda_attributes,
-- (2) in the final select:
    fa.firm_usda_attributes,
    fa.firm_uscg_attributes,
    fa.firm_fda_attributes
```

(also update `_gold.yml` column names + any `accepted_values`/`not_null` tests referencing the old
names.) The target names **match the already-renamed silver source tables** (`ref('firm_usda_attributes')`,
`ref('firm_uscg_attributes')`, `ref('firm_fda_attributes')`) and exactly what the plan (C19) anticipated.

**API benefit.** Self-documenting source-tagged names; the API's three per-source Pydantic sub-models
(`UsdaEstablishment` / `UscgManufacturer` / `FdaAttributes`) map 1:1 to obvious column names instead
of a comment-justified mapping. Reduces the "which sidecar is which?" cognitive load in 03/04.

**Cost / risk.** ⚠️ **This is an API-facing breaking change** if applied *after* the API ships against
the current names. **Do it BEFORE the API's first `openapi.json` snapshot is frozen** (05 contract test)
so the API is built against the clean names from day one; the two repos coordinate the rename in
lockstep. If the API has already shipped, **decline** — the rename is not worth a contract break for
cosmetics. Because the API repo is being built fresh now, this is the **one window** where it's cheap;
flag it to the operator early. **Priority: Recommended (do pre-go-live, before the API's first
openapi.json freeze).**

---

## #7 — Trigram / expression index for `?firm=` ILIKE substring  · **Conditional**

**Problem (API pain).** A `GET /recalls?firm=<substring>` filter would be an `ILIKE '%substring%'`
against `primary_firm_name` (or a firm-name join). A **leading-wildcard `%…%` is non-sargable**
(sargable-queries.md "LIKE Patterns": a leading wildcard forces a scan of every value); no index on
`mart_recall_summary` helps it. The natural fix — a `pg_trgm` GIN/GiST trigram index — is **not
available**: `pg_trgm` is **disabled on Neon (ADR 0037)**, which is also why firm fuzzy-resolution
runs as an upstream Python stage (gold_design_notes.md, ADR 0038 §5). So substring `?firm=` is a
seq-ish scan today, with no near-term index path.

**Exact change (only if it becomes hot).** Two routes, in preference order:
1. **Prefer steering the API** to the **`GET /firms/{id}`** path (exact canonical firm) or
   `normalized_name` btree (already indexed, mart_firm_profile line 6) for *prefix* lookups
   (`normalized_name LIKE 'acme%'` **is** sargable — prefix, not leading-wildcard). Document
   `?firm=` as best-effort substring, not index-backed; no mart change.
2. **If `pg_stat_statements` shows `?firm=` is a real hot path** (ADR 0038 §6 Phase-7 re-profile),
   the operator enables the extension and adds a trigram index — an Alembic migration to enable the
   extension (owner-only) plus a dbt `post_hook` trigram GIN:

```sql
-- migration (operator): enable the extension (reverses ADR 0037's "disabled" posture — a real decision)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```
```python
-- mart_recall_summary.sql post_hook (only after the extension exists):
post_hook="create index if not exists {{ this.name }}_primary_firm_trgm
           on {{ this }} using gin (primary_firm_name gin_trgm_ops)"
```

**API benefit.** Turns substring `?firm=` ILIKE into a trigram **Bitmap Index Scan** — but only worth
it if the endpoint sees real substring traffic.

**Cost / risk.** Enabling `pg_trgm` **reverses a standing ADR 0037 decision** — not a quiet index add;
it needs an ADR amendment and the operator's sign-off, and re-opens the "do we now also offer fuzzy
product search?" question the project deliberately closed. Trigram GINs are large and slower to build.
**Therefore Conditional, default OFF.** v1 ships substring `?firm=` as documented best-effort (no
fuzzy, no trigram — honest OpenAPI copy per locked decision 5); only revisit under measured load.

---

## #8 — Plan-C0c-dbt `(source, source_recall_id)` composite index  · **DECLINE**

**Problem it claimed to solve.** The original plan proposed an optional `(source, source_recall_id)`
composite index on `mart_recall_summary` as an alternative detail-lookup path for
`GET /recalls/{source}/{recall_id}`.

**Why decline.** The detail endpoint computes `recall_event_id = md5(f"{SOURCE_UPPER}|{recall_id}")`
in the API and hits the **existing `UNIQUE(recall_event_id)`** btree (mart line 4) — an O(1) point
lookup, confirmed for all five sources (01 — "recall_event_id md5 surrogate"; 02 marks C0c-dbt
**minor: drop entirely**). The composite would index a path the API **never takes**: it would only
help a `WHERE source=? AND source_recall_id=?` query, which the API does not issue. It is a pure
write-cost / storage liability (index-optimization.md "Common Index Mistakes #4: never removing
unused indexes" — here, never *adding* one). **Do not request this index. If it already exists on
silver `recall_event` for the pipeline's own joins, leave it; do not add it to the gold mart.**

**Priority: Decline.** No change; recorded so the build session and operator don't re-litigate it.

---

## #9 — FTS rank-keyset stability  · **API-side note (no mart change)**

**Observation (not a mart change).** The FTS path orders by `ts_rank_cd(search_vector, query) DESC`
(01 — Mart 2). **`ts_rank_cd` is computed at query time, not stored**, and the GIN serves the `@@`
*match*, not the *ordering* (01: "rank is NOT an ordered btree path"; 02 marks this minor). So:
- A keyset cursor that encodes `(rank, recall_product_id)` is **application-level over the matched
  set**, not an index seek — fine, because the matched set for a real query is small.
- Rank is **deterministic for a fixed `(query, search_vector)`**, and `search_vector` is stored +
  stable across a nightly rebuild, so rank is stable **within** a gold version; but a rebuild that
  changes a product's text changes its rank. The keyset tiebreaker `recall_product_id` is the stable
  anchor (01 — Mart 2: migrated to a stable `(event, ordinal)` key at this commit), so cursors stay
  monotonic even if a rank value shifts slightly between rebuilds.

**Recommendation: NO mart change.** Do **not** try to materialize a per-document rank column (rank is
query-dependent — meaningless to store). The API handles this entirely (04/03): compute rank at query
time, page the matched set with `(rank DESC, recall_product_id)` keyset, and treat the cursor as valid
within a gold version (combine with the `gold_meta.rebuilt_at` from #6 to invalidate cursors across a
rebuild if strict stability is ever required). **Priority: API-side note only.**

---

## #10 — Pipeline doc-hygiene fixes  · **Recommended (hygiene)**

These are **pipeline-repo documentation** corrections (no code/index change); they matter because the
API's OpenAPI caveat copy and any future `/stats/*` work read these docs as truth, and they are
currently **stale vs the SQL**.

| Item | Stale text (location) | Authoritative reality (SQL / facts) | Fix |
|---|---|---|---|
| **a. `fct_units_recalled` description** | `_gold.yml` lines 133–135: "FDA/USDA … basis-aware: per_product rows are **summed**, total_all_products … is **max'd**" | `fct_units_recalled.sql` line 45 uses **`max(rp.quantity_value)`** (basis-agnostic — SQL comment line 19: "`units = max(quantity_value)`, basis-agnostic", dated 2026-06-09). The description still narrates the older basis-aware sum/max logic. (01 — fct table flags this; confirmed in SQL.) | Update the `_gold.yml` description to match the SQL: units = `max(quantity_value)` per recall, basis-agnostic. |
| **b. `dim_date` spine year** | `_gold.yml` line 7: "1960-01-01..(current year + 2)" | SQL spine is **1940-01-01**..current_year+2 (01 — fct table; gold_design_notes.md "the 1940 floor matches `assert_recall_event_date_sanity`'s ERROR floor"). The `_gold.yml` says 1960 — **stale**. | Change `_gold.yml` `dim_date` description `1960` → `1940`. |
| **c. `fct_recalls_by_country` missing from plan deferred list** | The plan enumerates ~7 `fct_*`; `fct_recalls_by_country` (built C12, 2026-06-09) is absent (02 area "Deferred stats": "10 fct_* + dim_date … plan omits `fct_recalls_by_country`"). | The model exists (`dbt/models/gold/fct_recalls_by_country.sql`); its `'US'` cell is **derived** (heuristic), FDA+USDA only, per-country inflation (01 — fct table). | Add `fct_recalls_by_country` to the plan's deferred `/stats/*` inventory with its caveats; use 01's fct table as the authoritative list. |

**API benefit.** The deferred `/stats/*` scoping (post-v1) reads correct mart semantics; the v1 OpenAPI
caveat copy doesn't propagate a stale units/date claim. None of these touch v1's 4 endpoints.

**Cost / risk.** Doc-only edits in the pipeline repo. No risk. **Priority: Recommended hygiene.**

---

## Cross-references & judgment calls

- **The only deploy blocker is #2** (read-only role). #1, #3, #6, #10 are Recommended-but-not-blocking;
  **#5 is Recommended (do pre-go-live, before the API's first openapi.json freeze)**; #4 Optional;
  #7 Conditional; #8 Decline; #9 API-side-only. Consumed by **06** (deploy gate + cache anchor) and
  **04** (UPC GIN + ETag code).
- **Judgment call (#1 / #3 / #7 mechanism):** I specified `post_hook` for the `DESC` and trigram
  indexes because dbt's `config(indexes=[…])` column-list form **cannot** express `DESC` ordering or
  expression/opclass keys — this mirrors the index_audit.md precedent (the `firm_fda_attributes((firm_fei_num::text))`
  functional index is added via `post_hook` for exactly this reason). The UPC GIN (#3) **can** use the
  column-list `{'type':'gin'}` form (same as the live `search_vector` GIN), so it does.
- **Judgment call (#5 timing):** I made the sidecar rename **time-boxed to before the API's first
  openapi.json freeze** rather than a flat "do it" or "decline" — it's cheap now (fresh API repo) and a
  contract break later. The operator + API build session must coordinate; if they can't, decline.
- **Judgment call (#2 grant scope):** I default to `GRANT SELECT ON ALL TABLES` (mirrors 0033's blanket
  grant shape) but flag gold-only scoping as the stricter operator option. Either satisfies read-only.
- **Open items carried from 02 (operator must confirm before 06 wires `db.py`):** exact read-only role
  name, gold-only-vs-all grant scope, pooled-vs-direct Neon endpoint, and the API env-var name
  (`NEON_DATABASE_URL_RO` proposed). Also: dbt `run_started_at`/`modules.pytz` availability for #6
  (fallback noted inline).
- **Not re-litigated (locked):** md5 detail path (#8 decline), keyset pagination, FTS-without-trigram,
  sidecar names used verbatim by the API unless #5 is taken in the freeze window.
