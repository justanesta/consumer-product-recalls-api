# Data-side → API handover: Silver/Gold provenance audit (2026-W25)

**From:** `consumer-product-recalls` (data repo), branch `chore/data-provenance` · **2026-06-19**
**To:** `consumer-product-recalls-api`, branch `feature/api-audit`
**Contract:** ADR 0042 — the API reads the gold serving marts (`mart_recall_summary`, `mart_product_search`,
`mart_firm_profile`, `gold_meta`); their column names/types/enum domains/key recipes are the wire contract.
**Data-side source of truth:** `documentation/audit/silver_gold_provenance_audit_2026_w25.md` + the runnable
catalog `scripts/sql/cross_source/provenance_audit/` (run against **prod**, 2026-06-19).

## What this is

The data side ran an **independent, second** provenance audit over the same gold marts your
`project_scope/provenance-analysis-2026-06-17.md` + current API code already audited. **This is the cross-repo
reconciliation: the two audits agree on every point.** This doc reports it so `feature/api-audit` can (a) take
the independent confirmation, (b) close the two items your own analysis flagged `UNVERIFIED`, and (c) clean up
the one set of stale planning docs.

> **Bottom line: this branch requires NO change to your API code, your OpenAPI, or
> `provenance-analysis-2026-06-17.md` — they are already correct.** It made **no gold data/schema change** (no
> dbt model `.sql` touched → tables byte-identical → `gold_meta.schema_version` stays `'1'` → no contract
> break). The only stale spots are the earlier `build/01–05` planning docs (which `build/00` already says are
> superseded by the code/OpenAPI).

---

## §0. TL;DR

| Area | Your current state | Our independent audit | Action for you |
|---|---|---|---|
| **FDA `classification` = `1/2/3/NC`** | ✅ correct in code (`models/recalls.py:51`) + `provenance-analysis:241` | **CONFIRMED** + full corpus distribution | reconcile the **stale `build/01–05`** docs/fixtures (§4) |
| **distribution arrays = `list \| None`, NULL vs `{}` vs values** | ✅ correct (`models/recalls.py:202-217`) | **CONFIRMED** + live counts (§2) | none |
| **`risk_level` 4-value USDA-only (no `Medium - Class I`)** | flagged `UNVERIFIED` (§3.11) | **CONFIRMED** — only the 4 CASE values emit | close the UNVERIFIED note |
| classification corpus-scale null/value distribution | flagged `UNVERIFIED` (§3.10) | **MEASURED** (§3) | close the UNVERIFIED note |
| `is_currently_active` / `was_ever_retracted` | **pruned** from the response (`queries/recalls.py:53`) | now NHTSA-populated (FYI only) | none (§5) |
| `event_type` discriminator | absent | **CONFIRMED absent** (ADR 0003 deferred) | none — don't add (§6) |

---

## §1. Cross-repo confirmation — your contract is validated against live prod

Each item below your code/`provenance-analysis-2026-06-17` already states; our 2026-06-19 prod run confirms it.

| Contract item | Independent live confirmation (prod 2026-06-19) |
|---|---|
| `classification` source-native (FDA `1/2/3/NC`, USDA `Class I/II/III/Public Health Alert`, USCG `H/L/M/S`, CPSC/NHTSA NULL) | exact match; full per-value counts in §3 |
| `recall_event_id = md5(source \|\| '\|' \|\| source_recall_id)` (UPPERCASE source) | **byte-exact: 0 mismatches** over 93,444 rows — your path-param key recipe is correct |
| `source` closed + UPPERCASE `{CPSC,FDA,USDA,NHTSA,USCG}` | exactly those 5 in all marts; no NULL, no `'ALL'` in the serving marts |
| `is_active` tri-state, NULL for CPSC+NHTSA | CPSC 9,853 / NHTSA 30,090 all NULL; FDA/USDA/USCG `t`/`f` |
| `risk_level` USDA-only | non-null only USDA (1,218); §3 confirms the 4-value domain |
| `distribution_scope` closed 4-value NOT-NULL | `{Nationwide 42,207, Regional 32,283, Unspecified 11,973, International 6,981}`, 0 NULL |
| O1 jsonb arrays always non-null (`product_names`/`models`/`hins`/`firms`) | 0 NULL each — model `list[...]`, never `\| None` (contrast §2) |
| `recall_product_id` unique (keyset cursor) | 470,973 rows, all distinct, 0 NULL |
| `mart_product_search.upc` 100% NULL | 0 of 470,973 non-null (recall-level UPCs ride in `recall_product_upcs`) |
| `announced_at` nullable ~20 FDA / `published_at` always present | `announced_at` NULL = **20** (all FDA); `published_at` 0 NULL, sane range |
| served free-text empty-string clean | **0 `''`** across every served text column — no API-side `''→None` needed |
| nested-jsonb `''` by design | `hazards.HazardType`/`HazardTypeID` empty at CPSC source (your `models/recalls.py` note is correct) — not a defect |

---

## §2. Distribution arrays — the 3-state contract (NULL / `{}` / populated)

Your `models/recalls.py:202-217` already models this correctly (`list[str] | None`; "Null when no geography
parsed; an empty array indicates a foreign-country-only / domestic-only recall"). Confirming with **live
counts** (the corpus-scale measure your §3.10 flagged as not directly re-measured). The mart `LEFT JOIN`s
`recall_distribution_area`, which only FDA+USDA populate:

| State | Meaning | Pydantic | live `distribution_state_codes` | live `distribution_country_codes` |
|---|---|---|---|---|
| **`NULL`** | no `recall_distribution_area` row (CPSC/NHTSA/USCG, or FDA/USDA with no parsed geography) | the `None` case | **53,345** (57%) | **53,345** |
| **`'{}'`** | sidecar row exists, lists zero states / zero foreign countries | empty `list` | 2,931 | 32,852 |
| **populated** | actual USPS / ISO-3166-1 alpha-2 codes | non-empty `list` | 37,168 | 7,247 |

(mart total = 93,444.) **`NULL` ≠ `{}` is preserved on purpose** (data-side decision 2026-W25: *document as
nullable, do not coalesce*) — `NULL` = "no distribution data / unmatched"; `{}` = "matched, zero codes." Your
field descriptions already capture both; this just supplies the magnitudes. `distribution_country_codes` is
**FDA-only in practice** (USDA path dormant, ~0 today) — your `models/recalls.py:215` note holds.

---

## §3. Closing your two `UNVERIFIED` items (now measured)

**§3.10 — classification corpus-scale null/value distribution** (you flagged "not directly re-measured beyond
per-value counts"). Full live per-source breakdown (prod 2026-06-19):

| Source | values | counts |
|---|---|---|
| FDA | `1` / `2` / `3` / `NC` | 7,523 / 34,165 / 8,902 / 12 |
| USDA | `Class I` / `Class II` / `Class III` / `Public Health Alert` | 824 / 188 / 43 / 163 |
| USCG | `H` / `L` / `M` / `S` / `NULL` | 641 / 636 / 25 / 2 / 377 |
| CPSC / NHTSA | `NULL` | 9,853 / 30,090 |

(Counts drift slightly from your 2026-06-17 numbers — ~2 days of extracts — but the domain is identical.) This
is now `warn`-guarded on our nightly build via a new `accepted_values` test (§5), so a future out-of-domain
value alerts us before it reaches you.

**§3.11 — `risk_level` `Medium - Class I`** (you flagged the 5-label USDA PDF taxonomy includes it, CASE
doesn't emit it). **Confirmed:** only the **4** CASE values are present live — `High - Class I` (824) /
`Low - Class II` (188) / `Marginal - Class III` (43) / `Public Health Alert` (163). No `Medium - Class I`. Also
now `warn`-guarded.

---

## §4. Stale documentation to reconcile (the only doc action)

The earlier **`build/01–05`** planning docs (+ a couple of test fixtures) still carry the **pre-correction
"FDA `Class I/II/III`"** — i.e. they contradict your *own* current code (`models/recalls.py:51`) and
`provenance-analysis-2026-06-17.md:241,248`. `build/00-README:9-10` already says "trust the code/OpenAPI where
these disagree," so they're technically superseded — but `build/01` is labeled "the schema contract," so a
future reader could trust the wrong value. Reconcile when convenient:

| File | Stale text | Correct to |
|---|---|---|
| `build/01-ground-truth-gold-marts.md:68` | FDA `Class I / Class II / Class III` | FDA `1 / 2 / 3 / NC` |
| `build/02-plan-reconciliation.md:28` | "FDA/USDA `Class I/II/III`" | FDA `1/2/3/NC`; USDA `Class I/II/III` + `Public Health Alert` |
| `build/03-api-contract-and-models.md:162, 436, 535` | "FDA/USDA use `Class I/II/III`"; example `["Class II"]` | FDA `1/2/3/NC`; an FDA example should be `2` |
| `build/05-testing-and-ci-plan.md:203, 221, 228, 434, 588` | FDA fixture `F-1001` with `classification='Class I'` | use `'2'` for the FDA fixture (FDA never emits `Class I`); a test asserting `?classification=Class I` returns an **FDA** row tests an impossible value |

> `tests/test_queries_recalls.py:61` (`["Class I","Class II"]`) tests the IN-list filter mechanism with
> arbitrary strings — fine as-is (USDA *does* emit `Class I`); only the **FDA**-labeled fixtures above are wrong.

---

## §5. What changed on the DATA side this branch (`chore/data-provenance`)

So you know our side now matches yours:

- **ADR 0042 + `_gold.yml`** — we corrected the *same* `Class I/II/III` error in our own docs → FDA `{1,2,3,NC}`. (The data was always `1/2/3/NC`; only our docs were wrong.)
- **ADR 0003** — recorded `event_type` as **deferred / not-implemented** (the two ship-triggers: PHA-semantics clarification, or a recall-adjacent feed like FAA ADs).
- **`_silver.yml`** — added `accepted_values(warn)` tests on `classification`, `lifecycle_status`, `risk_level`, `initiated_by`, `firm_uscg_attributes.status` (domains in §3 + below). **These now run on every nightly `dbt build`** — if a source drifts out of an enum domain your filters depend on, our build **warns** (early-warning channel). Green against prod today.
- **No dbt model/snapshot `.sql` changed** → gold tables byte-identical → **no `schema_version` bump, no API-visible change.**

**Enum domains now `warn`-guarded on our side** (authoritative live reference for your OpenAPI enums):
`lifecycle_status` = FDA `{Ongoing,Terminated,Completed}` · USDA `{Active Recall,Closed Recall,Public Health Alert}` · USCG `{Open,Closed}` · CPSC/NHTSA NULL ·
`initiated_by` = `{firm,agency}` (FDA+NHTSA only) ·
`firm_uscg_attributes.status` (in `mart_firm_profile.firm_uscg_attributes` jsonb) = `{In Business,Inactive,Federal or State Agency}` ·
`role` (in `firms` jsonb) = `{manufacturer,importer,distributor,establishment,filer}` (no `retailer`) ·
`match_confidence` (in `firms` jsonb) live 13-value set incl. `rapidfuzz_rollup` (not `rapidfuzz_high`).

---

## §6. FYIs / non-issues

- **`is_currently_active` / `was_ever_retracted`:** you deliberately **pruned** these from the response
  (`queries/recalls.py:53-54` — "implied authoritative agency semantics they lack and were source-partial").
  FYI only: NHTSA presence is now **live** (30,075 rows, the C16 deep-rescan manifest banked) — so *if* you ever
  re-surface them, they're now USDA+NHTSA-populated (still NULL for CPSC/FDA/USCG). **No action.**
- **`event_type`:** confirmed absent from gold (ADR 0003 deferred). Every served row is a recall. Don't add a
  filter/column; the data side will re-handover if it ever ships.

---

## §7. Provenance — where to verify

- Data-side audit report: `consumer-product-recalls/documentation/audit/silver_gold_provenance_audit_2026_w25.md` (§1b "Live results" is authoritative).
- Runnable catalog (read-only, prod): `consumer-product-recalls/scripts/sql/cross_source/provenance_audit/` — `40_gold_marts_audit.sql` (serving contract), `90_coverage_gap_queries.sql` (key recipe / event_type / distribution conflation).
- Branch `chore/data-provenance` (pending patch-bump + merge to `main`); all counts from the 2026-06-19 prod run.
