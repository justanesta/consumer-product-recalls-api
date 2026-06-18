# Provenance Apply — Execution Plan (finalized 2026-06-18)

**Status:** Plan for approval. This is the **only write-to-code phase** of the audit sequence
(Provenance analysis → Surface review → **Apply**). Gated on (a) your approval and (b) the pipeline
empty-string normalization being **rebuilt into the gold serving marts** (the silver SQL is already
written — see §1).

## Inputs (SSOTs — transcribe, never re-derive)
- `project_scope/provenance-analysis-2026-06-17.md` — per-field proposed descriptions + matrix + §6 gap closure.
- `project_scope/surface-review-2026-06-17.md` — the `[FOLD INTO PROVENANCE APPLY]` items + dispositions.
- `TODO.md` → `## Performance` — the Q2 prune.
- The empty-string lineage trace (§1 below), verified against the pipeline dbt SQL on 2026-06-18.

---

## 1. Empty-string normalization — VERIFIED integration

The pipeline NULLs every free-text `''` (the source's "absent" marker). Confirmed by reading the dbt
SQL: the normalization is **already written in both silver models** (pending a gold `dbt build`/deploy
to reach the serving marts the API reads):
- `recall_product.sql:253–273` — source-uniform `nullif(trim(...), '')` at the union output.
- `recall_event.sql` — per-source: CPSC (`recall_reason` :46) + NHTSA (`recall_reason` :294,
  `corrective_action` :333, `consequence_of_defect` :334, `notes` :335, `mfgcampno` :336, `fmvss` :337).

### 1a. Verified lineage (raw → silver → gold **serving mart** → API)
Exposure is true only if the field is in the serving-mart SELECT **and** an API response model.

**Product grain** (`recall_product` → `mart_product_search`):

| Field | Gold serving mart | API-exposed | Empty-string impact |
|---|---|---|---|
| `product_name` | passthrough (`mart_product_search.sql:51`) | Yes (`ProductSearchHit` + `RecallDetail.product_names[]`) | CPSC ~3.2% blank→NULL — **no flip** |
| `product_description` | passthrough (`:52`) | Yes (`ProductSearchHit`) | CPSC 100% blank→NULL — **FLIP** |
| `model` | passthrough (`:53`) | Yes (`ProductSearchHit` + `RecallDetail.models[]`) | CPSC 100% blank→NULL — **FLIP** (→ NHTSA-only) |
| `type` | passthrough (`:54`) | Yes (`ProductSearchHit`) | CPSC ~40% blank→NULL — **no flip** (~60% real) |
| `category_id`, `number_of_units`/`unit_count` | **dropped** (not selected) | No | n/a — not in serving mart |

**Event grain** (`recall_event` → `mart_recall_summary`):

| Field | Gold serving mart | API-exposed | Empty-string impact |
|---|---|---|---|
| `recall_reason` | passthrough (`mart_recall_summary.sql:93`) | Yes (`RecallDetail`) | NHTSA ~8% + 1 CPSC blank→NULL — **no flip** (cross-source) |
| `corrective_action` | passthrough (`:108`) | Yes (`RecallDetail`) | NHTSA ~8% blank→NULL — **no flip** (NHTSA-only) |
| `consequence_of_defect` | passthrough (`:109`) | Yes (`RecallDetail`) | NHTSA ~16% blank→NULL — **no flip** (NHTSA-only) |
| `fmvss`, `mfgcampno`, `notes` | **dropped** (not in mart) | No | n/a — silver-only |

### 1b. Net for the apply
- **Exposed-affected (the apply re-tags): 7** — `product_name`, `product_description`, `model`, `type`,
  `recall_reason`, `corrective_action`, `consequence_of_defect`.
- **Silver-only / dropped at serving mart (no API impact): 5** — `category_id`, `number_of_units`
  (product), `fmvss`, `mfgcampno`, `notes` (event).
- **Binary `populated_by` flips: exactly 2** — `product_description` (CPSC `Y→–`) and `model`
  (CPSC `Y→–`, → NHTSA-only for real values; matches provenance finding #5). The other five exposed
  fields are blanks-within-a-populated-source → **no matrix flip**.

### 1c. Description adjustment during transcription
The deliverable's proposed descriptions for these 7 fields were written to the *pre-normalization*
reality ("CPSC empty-string"). The apply **adjusts** them to the end state — drop the "empty-string"
caveat; flip the `model`/`product_description` provenance tags to exclude CPSC; and apply the general
invariant *"free-text fields are NULL (not `\"\"`) when the source provides no value."*

### 1d. Residual gate (shrunk, because the SQL is verified)
Only one thing to confirm before merge: **the gold serving marts are rebuilt** with the new silver
(they're `materialized='table'`, so the live tables still serve `''` until `dbt build` runs). No
matrix re-derivation needed — the SQL already proves the two flips and the five drops.

### 1e. Pipeline-side note (yours; no apply impact)
`recall_event` normalizes **per-source** (CPSC + NHTSA branches only), whereas `recall_product` is
**source-uniform** at the union. So FDA/USDA/USCG event narrative (`recall_reason` via
`product_short_reason_txt` / `summary` / `coalesce(problem_1,problem_2)`) is **not** `nullif`-wrapped.
Fine if those are clean (your audit found only CPSC/NHTSA dirty); flagged in case you want
`recall_event` as defensively uniform as `recall_product`. Cross-source either way → no flip.

---

## 2. Q2 prune (the apply's anchor)
Remove from the API response (**keep in gold** — API-only; the pipeline keeps them for observability):
`is_currently_active`, `was_ever_retracted`, `first_seen_at`, `last_seen_at`, `edit_count`,
`edit_event_count`. **Keep `has_been_edited`.**
- `models/recalls.py` — drop from `RecallSummary` (`edit_event_count`) + `RecallDetail` (all six).
- `queries/recalls.py` — drop the columns from `_LIST_COLS` and the `sa.table()` literal (so
  `detail_stmt`'s `select(recall_summary)` stops projecting them).
- Tests — `test_models_recalls.py` and the integration assertions reading pruned fields (e.g.
  `test_detail_multi_firm_rollup` asserts `was_ever_retracted`).
- Docs — remove from the `data_contract.md` detail/list projection lists and the `api-reference.md`
  RecallDetail field table.
- Breaking to the OpenAPI contract — pre-go-live, cheap now.

---

## 3. Descriptions + matrix (the core write)
- `Field(description=…)` on **every exposed field** of `RecallSummary` / `RecallDetail` /
  `RecallSearchHit` / `ProductSearchHit` / `FirmProfile` (+ `FirmRef`), transcribed from the
  deliverable §3.x `proposed_description`, with the §1c empty-string adjustments and the §2 removals.
  Provenance tag is an **isolated trailing clause** (`… Sources: FDA, USDA (null for CPSC/NHTSA).`)
  so a later tag change is a one-line edit.
- **Subsumes these Surface-review description fixes** (all "make a description accurate" = this pass):
  A6 (`upc`/`recall_product_upcs` "flattened" → attribute flattening to the API), A10 (`firm_count`
  vs `firms[]`), A11 (`reason_category` USDA-only scope), A2 (`firm=` query-param: primary firm only).
- `data_contract.md` — new **"Per-source field provenance"** matrix section (deliverable §2 + the §1b
  flips); update the detail/list projection lists for the prune.
- `api-reference.md` — add a **"Sources"** column linking the matrix (don't restate); remove pruned
  fields from the RecallDetail table.
- **Honesty guard:** do not over-claim the deliverable §5 structural-only `populated_by` fields, the
  presence-flag true/false distributions, or other "unverified/structural-only" items — describe them
  as the deliverable qualified them.

---

## 4. Regenerate + gate
`uv run python -m recalls_api.export_openapi` → then `ruff check` + `ruff format --check` + `pyright` +
full `pytest` (via `sg docker -c 'uv run pytest'`) + `export_openapi --check`.

## 5. Verification pass (optional workflow — your opt-in)
A transcription of ~60 descriptions warrants an independent check. If you want it, a small workflow of
parallel verifiers can confirm: each written `Field` description matches its SSOT
`proposed_description` (± the §1c adjustment); the matrix matches the deliverable + §1b flips; the
prune removed **exactly** the six fields and kept `has_been_edited`; and no description over-claims an
unverified item. (Ultracode is off, so this is opt-in, not automatic; otherwise the §4 gate +
`export_openapi --check` are the baseline guard.)

---

## Out of scope (standalone — NOT the apply)
- **A1 cursor — DONE** (committed). A5 dead-config, the test-hygiene gaps, and the system/e2e tier —
  separate PRs.
- **A9 (drop `ProductSearchHit.upc`) — DECISION NEEDED.** Distinct from the empty-string audit: `upc`
  is `cast(null as text)` (a forward-compat placeholder; `mart_product_search.sql:17` keeps it as a
  "forward-looking placeholder for structured per-product UPCs"), not a blank-string. Drop it in the
  apply (tagged FOLD) **iff** you confirm gold keeps it 100% NULL; else keep with the existing
  "currently null for all rows" note.
- **H2 (product FTS rank weight vector)** — needs upstream mart confirmation; a *ranking* behavior,
  not a description, so out of apply scope (at most a one-line doc note).

---

## Execution order
0. **(you)** Confirm the gold serving marts are rebuilt with the silver normalization (§1d), and the
   A9 `upc` decision.
1. **(me)** Descriptions + §1c empty-string adjustments + §2 prune (`models/`, `queries/`).
2. **(me)** `data_contract.md` matrix + `api-reference.md` Sources column + the subsumed A2/A6/A10/A11 fixes.
3. **(me)** openapi regen + §4 gate.
4. **(me, optional)** §5 verification pass.

Steps 1–3 can run **before** step 0's rebuild confirmation (the seed has no CPSC/NHTSA empty-strings,
so the test suite is unaffected and the contract is written forward-correct) — but **hold merge** until
the gold marts are rebuilt, so the deployed API's data and its OpenAPI contract agree on day one.
