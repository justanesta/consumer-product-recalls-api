# Gold-Field Provenance Analysis — Consumer Product Recalls API

**Date:** 2026-06-17
**Status:** READ-ONLY analysis. This document feeds a later **GATED apply** step. **Apply nothing here** — no Pydantic `Field(description=...)` strings, no `_gold.yml` column docs, no model changes are made by authoring this file. Every proposed description below is a *proposal* staged for review.

## 1. Purpose & Methodology

### Purpose
Establish the empirically-verified provenance of every gold-served API field exposed by the consumer-product-recalls API, so that (a) the API model `Field(description=...)` strings (point 3a/3c), and (b) the `data_contract.md` per-source population matrix (point 3b) can be authored from ground truth rather than assumption. Each field record carries the proposed description text, ready to paste in the later apply step, provenance-tagged.

### Methodology
The audit traces each field through the full pipeline:

```
raw source (incl. agency PDFs: CPSC Programmers Guide, FDA enforcement_report_api_definitions,
            NHTSA RCL.txt, USDA/USCG dictionaries & scrape observations)
   -> staging (stg_*)
   -> silver  (recall_event, recall_product, recall_event_firm, firm, recall_distribution_area,
               recall_lifecycle, recall_event_history, *_attributes snapshots/views)
   -> gold    (mart_recall_summary, mart_product_search, mart_firm_profile + sidecars)
   -> API     (Pydantic models: recalls.py, products.py, firms.py, common.py)
```

Every claim is **empirically verified** against the dbt SQL and against `data/exploratory/gold/audit_coverage.txt` / `audit_schema.txt` (real row counts, real per-source population). Where the first pass made a claim that ground-truth contradicted (e.g. the FDA classification vocabulary; empty-string-vs-NULL for CPSC `model`/`type`/`product_description`; NHTSA/USDA presence-flag population), the correction is recorded in the per-field record and folded into the discrepancy/confidence sections. **Nothing is assumed** — every `populated_by` value is either backed by a coverage number or explicitly flagged as structural-only.

### Source-of-truth caveat carried throughout
**ADR documents do not exist on disk.** No ADR directory was found in either repo; ADR numbers (0002, 0026, 0027, 0031, 0033, 0034, 0035, 0036, 0038, 0042, etc.) appear only as inline references inside dbt model headers and `*.yml`. ADR attributions below are sound but rest on model-header comments, **not** on reading the ADR text. This is the single most pervasive UNVERIFIED aspect.

> **🔧 Correction (2026-06-17, post-run sanity check) — the caveat above is WRONG.** The ADRs **do** exist on disk; the lineage agents searched for an `adr/` directory and missed the real one, `documentation/decisions/`. The pipeline repo holds **43** ADR files (including `0035-cross-source-scd2-silver-dimensions.md`, `0036-cross-source-canonical-silver-naming.md`, `0042-gold-serving-marts-published-read-contract.md`) and the API repo holds **15**. The ADR attributions in this document are therefore **verifiable**, not unverified — the apply step (or a short follow-up pass) should read the cited ADRs to confirm the semantic-decision wording. Treat "ADR text unread" as an open verification *task*, not a structural impossibility.

---

## 2. Per-Source Field Provenance Matrix

Legend: **Y** = source populates this field with meaningful data · **–** = explicitly NULL for this source (by construction) · **n/a** = field is source-independent (synthesized constant / query-time / pipeline-observability — not attributable to any one agency).

### `mart_recall_summary` — backs RecallSummary (list) & RecallDetail (detail)

| Field | CPSC | FDA | USDA | NHTSA | USCG | Notes |
|---|---|---|---|---|---|---|
| recall_event_id | Y | Y | Y | Y | Y | synthesized md5 PK, never null |
| source | Y | Y | Y | Y | Y | hard-coded discriminator literal |
| source_recall_id | Y | Y | Y | Y | Y | agency-native; FDA = RECALLEVENTID |
| title | Y | Y | Y | Y | Y | native CPSC/USDA; synthesized FDA/NHTSA/USCG |
| url | Y | – | Y | – | Y | FDA/NHTSA carry no per-recall URL |
| announced_at | Y | Y | Y | Y | Y | ~20 FDA events null (≥1940 guard) |
| published_at | Y | Y | Y | Y | Y | coalesced, hard NOT-NULL, sort key |
| classification | – | Y | Y | – | Y | native vocabularies, NOT normalized |
| risk_level | – | – | Y | – | – | USDA-only, derived 1:1 from classification |
| lifecycle_status | – | Y | Y | – | Y | native vocabularies, NOT normalized |
| is_active | – | Y | Y | – | Y | tri-state; null = CPSC+NHTSA exactly |
| reason_category | – | – | Y | – | – | USDA FSIS taxonomy CSV |
| recall_reason | Y | Y | Y | Y | Y | free-text narrative, all 5 |
| corrective_action | – | – | – | Y | – | NHTSA-only |
| consequence_of_defect | – | – | – | Y | – | NHTSA-only |
| distribution_scope | Y | Y | Y | Y | Y | conformed enum; CPSC/USCG/NHTSA are DEFAULTS |
| distribution_states | – | – | Y | – | – | USDA raw CSV scalar |
| distribution_state_codes | – | Y | Y | – | – | parsed USPS codes (FDA free-text + USDA list) |
| distribution_country_codes | – | Y | – | – | – | FDA-only in practice (USDA path dormant) |
| hazards | Y | – | – | – | – | CPSC jsonb array |
| product_upcs | Y | – | – | – | – | CPSC-only, sparse (~4.6%) |
| primary_firm_name | Y | Y | Y | Y | Y | role-priority pick from firm rollup |
| firm_count | Y | Y | Y | Y | Y | count(distinct firm_id) |
| firms | Y | Y | Y | Y | Y | jsonb array, one element per (firm,role) |
| product_count | Y | Y | Y | Y | Y | USDA/USCG structurally always 1 |
| product_names | Y | Y | Y | Y | Y | cross-source alias (desc/title/component) |
| models | – (`""`) | – | – | Y | – | NHTSA MODELTXT; CPSC empty-string only |
| hins | – | – | – | – | Y | USCG Hull IDs |
| edit_event_count | n/a | n/a | n/a | n/a | n/a | synthesized; structurally non-null all rows |
| has_been_edited | n/a | n/a | n/a | n/a | n/a | synthesized; 45 trues corpus-wide, source split unknown |
| edit_count | Y | Y | Y | Y | Y | distinct content-hash versions (pipeline) |
| first_seen_at | Y | Y | Y | Y | Y | pipeline-observability (bronze) |
| last_seen_at | Y | Y | Y | Y | Y | pipeline-observability (bronze) |
| is_currently_active | – | – | Y | Y | – | presence manifest; {USDA,NHTSA} only |
| was_ever_retracted | – | – | Y | Y | – | presence manifest; {USDA,NHTSA} only |

### `mart_product_search` — backs ProductSearchHit

| Field | CPSC | FDA | USDA | NHTSA | USCG | Notes |
|---|---|---|---|---|---|---|
| recall_product_id | Y | Y | Y | Y | Y | per-source md5 surrogate |
| recall_event_id | Y | Y | Y | Y | Y | parent-event md5 |
| source | Y | Y | Y | Y | Y | literal discriminator |
| source_recall_id | Y | Y | Y | Y | Y | FDA = productid (product-grain) |
| product_name | Y | Y | Y | Y | Y | cross-source alias |
| product_description | Y (`""`) | Y | Y | Y | Y | CPSC empty-string (100% non-null but blank) |
| model | Y (`""`) | – | – | Y | – | NHTSA real; CPSC empty-string |
| model_year | – | – | – | Y | Y | NHTSA + USCG (vehicle/vessel) |
| type | Y | Y | Y | Y | Y | source-specific vocabularies, NOT harmonized |
| hin | – | – | – | – | Y | USCG Hull IDs |
| upc | – | – | – | – | – | placeholder; NULL for every source |
| rank | n/a | n/a | n/a | n/a | n/a | query-time ts_rank_cd, not stored |
| upc_is_recall_level | n/a | n/a | n/a | n/a | n/a | constant `True` honesty flag |
| recall_title | Y | Y | Y | Y | Y | from mart_recall_summary.title |
| classification | – | Y | Y | – | Y | from mart_recall_summary |
| risk_level | – | – | Y | – | – | from mart_recall_summary |
| published_at | Y | Y | Y | Y | Y | from mart_recall_summary |
| url | Y | – | Y | – | Y | from mart_recall_summary |
| is_active | – | Y | Y | – | Y | from mart_recall_summary |
| firm_name | Y | Y | Y | Y | Y | = primary_firm_name |
| recall_product_upcs | Y | – | – | – | – | CPSC-only, recall-level; real UPC-search path |

### `mart_firm_profile` (+ sidecars) — backs FirmProfile

| Field | CPSC | FDA | USDA | NHTSA | USCG | Notes |
|---|---|---|---|---|---|---|
| firm_id | Y | Y | Y | Y | Y | derived cross-source cluster key |
| canonical_name | Y | Y | Y | Y | Y | representative display name |
| normalized_name | Y | Y | Y | Y | Y | upper(trim()) of representative, NOT unique |
| observed_names | Y | Y | Y | Y | Y | jsonb of raw spellings |
| observed_company_ids | – | Y | Y | – | Y | FDA FEI / USDA establishment_number / USCG MIC |
| alternate_names | n/a | n/a | n/a | n/a | n/a | derived enrichment (firm_crosswalk) |
| total_recalls | Y | Y | Y | Y | Y | count(distinct recall_event_id) cross-source |
| active_recalls | – | Y | Y | – | Y | FILTER(is_active); CPSC/NHTSA can never count |
| first_recall_at | Y | Y | Y | Y | Y | min(published_at) |
| last_recall_at | Y | Y | Y | Y | Y | max(published_at) |
| roles | Y | Y | Y | Y | Y | distinct roles jsonb |
| recalls_by_source | Y | Y | Y | Y | Y | sparse jsonb object |
| distinct_products | Y | Y | Y | Y | Y | per-firm footprint (NOT global-distinct) |
| firm_fda_attributes | – | Y | – | – | – | FDA FEI sidecar |
| firm_usda_attributes | – | – | Y | – | – | USDA FSIS establishment sidecar |
| firm_uscg_attributes | – | – | – | – | Y | USCG MIC directory sidecar |

---

## 3. Per-Field Records

For each field: gold `mart.column`; raw→gold lineage; true meaning + caveats; verified `populated_by`; the **PROPOSED** `Field(description=...)` string (provenance-tagged, ready to paste); the current description; the discrepancy (severity) + verification confidence; and explicitly-called-out UNVERIFIED aspects.

---

### 3.1 `RecallSummary.recall_event_id` / `RecallDetail.recall_event_id` → `mart_recall_summary.recall_event_id`

- **Lineage:** silver `recall_event` synthesizes a source-namespaced surrogate: `md5('<SOURCE>' || '|' || <natural key>)` per branch — CPSC RecallNumber (`recall_event.sql:35`), FDA RECALLEVENTID via the staging-aliased `recall_event_id` (`:96`/`:98`), USDA field_recall_number (`:196`), NHTSA CAMPNO (`:278`), USCG recall Number (`:356`); unique test `:4`. Reused **verbatim** into gold `mart_recall_summary.sql:89` (unique PK `:4`; header `:26-31` "reused from silver verbatim (ADR 0038) — never re-keyed"). Both Pydantic models bind the same column (`models/recalls.py:22`, `:56`).
- **True meaning:** an opaque, API-synthesized, source-namespaced surrogate PK for a recall **EVENT** (not a product line). 32-char md5 hex, stable across re-extractions as long as the upstream natural key is stable, unique one-per-recall_event, never null (mart PK, 93,378 rows). Not a raw agency identifier.
- **Caveats:** event grain (FDA hashes RECALLEVENTID, so all product lines of one recall share this id — product-level uniqueness is `recall_product_id`); opaque, carries no parseable semantics; stability inherited from the upstream natural key.
- **populated_by:** CPSC ✓ FDA ✓ USDA ✓ NHTSA ✓ USCG ✓ (NOT-NULL unique PK; `audit_coverage.txt:10-14`, `audit_schema.txt:186`).
- **PROPOSED:** *"Opaque surrogate identifier for one recall event, stable across re-extractions. Synthesized as md5('<SOURCE>' || '|' || <source recall key>) (CPSC RecallNumber / FDA RECALLEVENTID / USDA recall number / NHTSA CAMPNO / USCG recall number) in silver and reused verbatim in gold (ADR 0038). Unique, one row per recall event, never null. Not a raw agency identifier; use {source, source_recall_id} for the human-facing key. Sources: all (CPSC, FDA, USDA, NHTSA, USCG)."*
- **Current:** `null` (both models).
- **Discrepancy (LOW):** no Pydantic description on a non-obvious opaque hashed event-grain surrogate. Confidence **HIGH**.
- **UNVERIFIED:** ADR 0038 text not read (file absent); attribution from model header + `_gold.yml:161-162`.

---

### 3.2 `ProductSearchHit.rank` → (no gold column — query-time)

- **Lineage:** gold ships only the precomputed `search_vector` tsvector (`mart_product_search.sql:66-72`, GIN-indexed `:8`); **no `rank` column exists** (`audit_schema.txt:166-185`). `rank` is computed **per request** in the API as `ts_rank_cd(search_vector, websearch_to_tsquery('english', :q))` in `fts_stmt` (`queries/products.py:102`), selected only on the FTS path (`:103`), ordered `rank.desc()` (`:109`). The UPC path (`_upc_where`/`upc_stmt`, `:146-157`) and exact-identifier path (`identifier_stmt`, `:125-133`) use bare `*_HIT_COLS` (`:45-65`, no `rank`), so rank is **absent** there. Pydantic `rank: float | None = None` (`models/products.py:45-47`).
- **True meaning:** API-synthesized cover-density relevance score, present **only** on the keyword (q) path; null/absent for UPC and exact-identifier lookups. Higher = better match for *this* query; **not comparable across queries** and not the same scale as `RecallSearchHit.rank` (which uses a 4-bucket weighted A/B/C/D vector — product_search uses an *unweighted* vector).
- **populated_by:** n/a for every source — population depends on the query path, not the matched record's agency.
- **PROPOSED:** *"Cover-density full-text relevance (ts_rank_cd over the product search_vector). Present only on the keyword (q) search path; null for UPC and exact-identifier lookups. Higher is more relevant, but scores are not comparable across queries. Computed per request in the API, not stored in gold. Source-independent (not an agency field)."*
- **Current:** `"Relevance; present only for keyword (q) search."`
- **Discrepancy (LOW):** current is correct on the populated-only-on-q point but omits (1) non-comparability across queries and (2) that it is query-time, ts_rank_cd over an unweighted vector. Confidence **HIGH** (first-pass `_search_stmt`/`upc_stmt` line citations were misnamed; corrected to `fts_stmt:100-109`, substantive claim unaffected).
- **UNVERIFIED:** whether a combined q+upc path ever attaches a non-null rank on a non-q path (only separate stmts observed); exact `ts_rank_cd` normalization flag (called without explicit arg).

---

### 3.3 `ProductSearchHit.upc_is_recall_level` → (no gold column — constant)

- **Lineage:** no column backs this. Hardcoded Pydantic `Literal[True]`, default `True` (`models/products.py:48-51`). Rationale grounded in gold: the per-product `upc` column is NULL for every row of every source (`mart_product_search.sql:14-17,26-30`; `upc_pop = 0` all five sources, `audit_coverage.txt:117-121`). UPC search is served by recall-level containment `cast(recall_product_upcs, jsonb) @> [{"upc": :upc}]` (`queries/products.py:146-152`), never the `upc` column ("ALL-NULL today — never filtered", `:33`). The all-NULL `upc` btree was DROPPED 2026-06-15.
- **True meaning:** a constant honesty flag (always `True`) documenting that UPC search is recall-grain, not product-grain. CPSC UPCs are recall-level; FDA bulk returns none; USDA/NHTSA/USCG have no UPC concept. Recall-level matches are **CPSC-only** today (466 product rows / 453 recalls; all other sources 0, `audit_coverage.txt:117-121`).
- **populated_by:** n/a for every source — fixed constant on every hit.
- **PROPOSED:** *"Constant True honesty flag: UPC search is recall-level (containment over the recall_product_upcs array, currently CPSC-sourced and sparse), not product-grain. The per-product upc column is NULL for every source today (CPSC UPCs are recall-level; FDA bulk returns none; USDA/NHTSA/USCG have no UPC). Set in the API model, not a stored field; always True. Source-independent."*
- **Current:** `"UPC matches are recall-level (recall_product_upcs), not product-grain."`
- **Discrepancy (LOW):** current omits that the field is a fixed constant (always True) and that recall-level UPC matches are CPSC-only today. Confidence **HIGH** (corrected the CPSC populated rate from the raw-dict ~2.7% estimate to the empirical gold count: 466 product rows / 453 recalls ≈ 4.6%).
- **UNVERIFIED:** live populated rate of `recall_product_upcs` not separately queried beyond the coverage count; whether a future source could ever populate the per-product `upc` column.

---

### 3.4 `source` (RecallSummary / RecallDetail) → `mart_recall_summary.source`

- **Lineage:** hard-coded discriminator literal per silver branch — `'CPSC'` (`recall_event.sql:36`), `'FDA'` (`:97`), `'USDA'` (`:197`), `'NHTSA'` (`:279`), `'USCG'` (`:357`); unioned in `all_events`. Passed through `mart_recall_summary.sql:90`. `accepted_values ['CPSC','FDA','USDA','NHTSA','USCG']` + not_null at both `_silver.yml:21-23` and `_gold.yml:170-175`. Pydantic types it via a `Source` StrEnum matching the gold accepted_values.
- **True meaning:** the originating agency feed — a closed 5-value discriminator literal (not a raw field), forming the first half of `(source, source_recall_id)`.
- **populated_by:** all five ✓ (`audit_coverage.txt:11-15`).
- **PROPOSED:** *"Originating agency feed for the recall (closed enum). One of: CPSC, FDA, USDA, NHTSA, USCG. Always populated for every source."*
- **Current:** `null` (typed via StrEnum).
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.5 `source_recall_id` (RecallSummary / RecallDetail) → `mart_recall_summary.source_recall_id`

- **Raw sources:** CPSC RecallNumber, FDA recalleventid (event grain, cast text), USDA field_recall_number (DDD-YYYY, English-only), NHTSA CAMPNO, USCG 'Number'.
- **Lineage:** per-source identity column. FDA collapses product-grain bronze via `DISTINCT ON (recall_event_id)` and casts text (`recall_event.sql:95,98`); NHTSA collapses vehicle×component rows via `DISTINCT ON (campno)` (`:277,280`). Pass-through `mart_recall_summary.sql:91`.
- **True meaning:** agency-native primary recall identifier; meaning differs per source. FDA value is the **RECALLEVENTID event grain** (one event spans many product lines); NHTSA campno is the campaign; USDA is the English-language record only.
- **populated_by:** all five ✓ (`source_recall_id_pop = n_rows`, 9853/50552/30075/1681/1217, `audit_coverage.txt:11-15`).
- **PROPOSED:** *"Agency-native recall identifier (string); meaning varies by source — CPSC RecallNumber, FDA RECALLEVENTID, USDA field_recall_number (DDD-YYYY), NHTSA CAMPNO campaign number, USCG recall Number. Pair with `source` for global identity. Always populated."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.6 `title` (RecallSummary / RecallDetail) → `mart_recall_summary.title`

- **Raw sources:** CPSC Title (native, `recall_event.sql:41`); USDA field_title (native, `:202`); FDA synthesized `coalesce(recall_num, center_cd||'-'||event_id) || ' — ' || firm_legal_nam` (`:123-124`); NHTSA synthesized `campno || ' — ' || mfgname` (`:284`); USCG synthesized `coalesce(company_name,mic,source_recall_id) || ' — ' || coalesce(model_name,'(no model)')` (`:362-363`). Pass-through `mart_recall_summary.sql:92`.
- **True meaning:** human-readable headline. Native for CPSC/USDA; **synthesized composites** for FDA/NHTSA/USCG (em-dash join of recall-id and firm/model). Effectively always populated.
- **Caveats:** FDA/NHTSA/USCG titles are pipeline-synthesized, NOT agency-authored. FDA firm = firmlegalnam; NHTSA firm = MFGNAME (Part 573 filer).
- **populated_by:** all five ✓ (non-null-producing SQL for all branches).
- **PROPOSED:** *"Human-readable recall headline. CPSC/USDA use the agency's native title; FDA/NHTSA/USCG have no title field so it is synthesized as '<recall-id> — <firm/model name>'. Effectively always populated."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH** (first-pass cited USDA title at `:200`; actual `:202`, immaterial drift).

---

### 3.7 `url` (RecallSummary / RecallDetail) → `mart_recall_summary.url`

- **Raw sources:** CPSC URL (`recall_event.sql:43`), USDA field_recall_url (`:204`), USCG details_url constructed `recalls-details.php?id=<number>` (`:365`). FDA `cast(null as text)` (`:128`), NHTSA `cast(null as text)` (`:286`). Pass-through `mart_recall_summary.sql:94`.
- **True meaning:** public detail-page URL. Populated for CPSC/USDA/USCG; **NULL for FDA and NHTSA** (no per-recall detail URL; FDA's press-release URL is a separate Tier-3 field not mapped here). USCG url is pipeline-constructed.
- **populated_by:** CPSC ✓ FDA – USDA ✓ NHTSA – USCG ✓.
- **PROPOSED:** *"Public detail-page URL for the recall. Sources: CPSC, USDA, USCG (null for FDA/NHTSA, which provide no per-recall detail URL)."*
- **Current:** `null` (typed `str | None`, correctly nullable).
- **Discrepancy: NONE.** Confidence **HIGH** (no direct url coverage column; FDA/NHTSA false forced by explicit null casts; CPSC/USDA/USCG rest on SQL construction).

---

### 3.8 `announced_at` (RecallSummary / RecallDetail) → `mart_recall_summary.announced_at`

- **Raw sources:** CPSC RecallDate (`recall_event.sql:38`), FDA recallinitiationdt with `>= '1940-01-01'` guard (`:112-113`), USDA field_recall_date (`:199`), NHTSA RCDATE Part-573 received date (`:281`), USCG case_open_date with epoch→null + `WHERE announced_at is not null` (`:359,431`). Pass-through `mart_recall_summary.sql:95`.
- **True meaning:** date the recall was first announced/initiated. **Nullable by design** — exactly ~20 FDA events null (archive + dropped-century typos nulled by the ≥1940 guard); USCG epoch-sentinel rows are dropped from the table entirely. `not_null` is severity=warn at silver.
- **populated_by:** all five ✓ — `announced_at_pop` CPSC 9853/9853, FDA **50532/50552 (exactly 20 null)**, NHTSA 30075/30075, USCG 1681/1681, USDA 1217/1217 (`audit_coverage.txt:11-15`).
- **PROPOSED:** *"Date the recall was first announced/initiated (timestamptz). Conformed across all five sources (CPSC RecallDate, FDA recall-initiation date, USDA recall date, NHTSA RCDATE, USCG case-open date). Nullable: ~20 FDA events lack a trustworthy initiation date (archive + dropped-century typos). Sort/filter on published_at when a guaranteed date is required."*
- **Current:** `null`.
- **Discrepancy:** this is one of the **5 known carry-forward findings** (see §4). The substance (nullable, ~20 FDA null, semantics vary) is correct and confirmed; the gap is the missing Pydantic description. Confidence **HIGH**.

---

### 3.9 `published_at` (RecallSummary / RecallDetail) → `mart_recall_summary.published_at`

- **Raw sources:** CPSC LastPublishDate (`recall_event.sql:39`); FDA `coalesce(event_lmd, recall_initiation_dt)` (`:119`); USDA `coalesce(last_modified, recall_date)` (`:200`); NHTSA `coalesce(datea, rcdate)` (`:282`); USCG `coalesce(last_date, announced_at)` (`:360`). Hard not_null at `_silver.yml:44-45` and `_gold.yml:176-178`; the canonical keyset-sort column (`mart_recall_summary.sql:12-16` post_hook, `:96`).
- **True meaning:** last-published/modified date, coalesced per source so it is **guaranteed non-null** — the sort/pagination key (contrast nullable `announced_at`). Semantics differ slightly by source (last-published vs last-modified vs record-creation).
- **populated_by:** all five ✓ — 100% population (`audit_coverage.txt:11-15`, all = n_rows).
- **PROPOSED:** *"Last-published/modified date of the recall (timestamptz), coalesced per source to always be present — the guaranteed sort/pagination key (contrast nullable announced_at). Sources: all five."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.10 `classification` (RecallSummary / RecallDetail / ProductSearchHit) → `mart_recall_summary.classification` (and `mart_product_search.classification`)

- **Raw sources:** FDA centerclassificationtypetxt (`recall_event.sql:129`), USDA field_recall_classification (`:205`), USCG severity (`:366`). CPSC `cast(null)` (`:44`), NHTSA `cast(null)` (`:287`). Pass-through `mart_recall_summary.sql:97` → `mart_product_search.sql:36,59`.
- **True meaning:** source-native severity/hazard classification, **NOT cross-normalized**:
  - **FDA: numeric short codes `'1'`, `'2'`, `'3'`, `'NC'` (Not Yet Classified)** — *not* Roman "Class I/II/III". (Gold holds raw centerclassificationtypetxt verbatim.)
  - USDA: `Class I/II/III` + `Public Health Alert`.
  - USCG: single-letter `H/L/M/S` (value meanings undocumented, USCG OII ask pending).
  - NULL for CPSC and NHTSA (no hazard-class field).
- **populated_by:** CPSC – FDA ✓ USDA ✓ NHTSA – USCG ✓ — confirmed: CPSC blank 9853, NHTSA blank 30075, FDA `'2'`=34128/`'3'`=8896/`'1'`=7516/`'NC'`=12, USDA full, USCG H/L/M/S populated + 377 blank (`audit_coverage.txt:27-42`; product mart `classification_pop` USCG 1304, USDA 1217, FDA 134602, `:120`).
- **PROPOSED:** *"Recall severity/hazard classification in the source's native vocabulary (FDA: numeric 1/2/3 and NC for Not Yet Classified; USDA: Class I/II/III, Public Health Alert; USCG: H/L/M/S). NOT normalized across sources. Sources: FDA, USDA, USCG (null for CPSC/NHTSA)."*
- **Current:** `null`.
- **Discrepancy: NONE on provenance/population.** Confidence **HIGH**, but the first pass's `confirmed` flag was set false because it **mis-stated the FDA vocabulary** (claimed Roman "Class I/II/III"; FDA actually emits `1/2/3/NC` — `stg_fda_recalls.sql:36`, `fda/field_audit_2026_w22.md:285,287,333`). The proposed string above is corrected. This is a content correction, not a discrepancy against existing docs.
- **UNVERIFIED → ✅ RESOLVED 2026-06-19 (data-side handover):** ~~corpus-scale null/value distribution of the merged column not directly re-measured beyond the per-value counts above~~ — independently measured against live prod: FDA `1/2/3/NC` = 7,523/34,165/8,902/12, USDA `Class I/II/III`/PHA = 824/188/43/163, USCG `H/L/M/S`/NULL = 641/636/25/2/377, CPSC/NHTSA NULL = 9,853/30,090; domain identical (counts drift ~2 days from the figures above), now warn-guarded by a dbt `accepted_values` test (see [data-side handover](data-side-provenance-handover-2026-06-19.md) §3).

---

### 3.11 `risk_level` (RecallSummary / RecallDetail / ProductSearchHit) → `mart_recall_summary.risk_level` (and `mart_product_search.risk_level`)

- **Lineage:** **USDA-only**, a CASE on `classification` (`recall_event.sql:216-222`): Class I→`High - Class I`, Class II→`Low - Class II`, Class III→`Marginal - Class III`, Public Health Alert→passthrough. **Derived 1:1 from classification, NOT lifted from the raw USDA risk_level field** (W1 Q2 decision; raw kept only in `source_payload_raw`). Other sources `cast(null)`: CPSC `:51`, FDA `:144`, NHTSA `:299`, USCG `:376`. Pass-through `mart_recall_summary.sql:98` → `mart_product_search.sql:37,60`.
- **True meaning:** USDA-only health-risk label, redundant with USDA classification; carries no signal beyond it.
- **populated_by:** CPSC – FDA – USDA ✓ NHTSA – USCG – — `risk_level_pop` USDA 1217 only; derived counts exactly match USDA classification counts (High-Class I 824, Low-Class II 187, PHA 163, Marginal-Class III 43), proving the deterministic mapping (`audit_coverage.txt:67-71` vs `:38-41`). Product mart `risk_level_pop` USDA 1217, others 0 (`:117-121`); only the 4 CASE values emitted — no `Medium - Class I` (`:151-156`).
- **PROPOSED:** *"USDA health-risk label derived 1:1 from the USDA classification (e.g. 'High - Class I', 'Low - Class II', 'Marginal - Class III', 'Public Health Alert'). Sources: USDA only (null for CPSC/FDA/NHTSA/USCG)."*
- **Current:** `null` (Pydantic example `'Low - Class II'` matches a derived value; `str | None`).
- **Discrepancy:** this is one of the **5 known carry-forward findings** (see §4 — the "risk_level" finding: USDA-only, derived not lifted). The provenance is now fully confirmed; the gap is documentation. Confidence **HIGH**.
- **UNVERIFIED → ✅ RESOLVED 2026-06-19 (data-side handover):** ~~the 5-label USDA PDF taxonomy includes `Medium - Class I`, which the CASE does not emit — not re-verified against future corpus~~ — independently confirmed live: only the **4** CASE values are present (`High - Class I` 824 / `Low - Class II` 188 / `Marginal - Class III` 43 / `Public Health Alert` 163), no `Medium - Class I`; now warn-guarded by a dbt `accepted_values` test (see [data-side handover](data-side-provenance-handover-2026-06-19.md) §3).

---

### 3.12 `lifecycle_status` (RecallSummary / RecallDetail) → `mart_recall_summary.lifecycle_status`

- **Raw sources:** FDA phase_txt (`recall_event.sql:130`), USDA recall_type (`:206`), USCG `initcap(disposition)` (`:367`). CPSC `cast(null)` (`:45`), NHTSA `cast(null)` (`:290`). Pass-through `:99`.
- **True meaning:** lifecycle/status in each source's native vocabulary (FDA Ongoing/Completed/Terminated; USDA Active Recall/Closed Recall/Public Health Alert; USCG Open/Closed, casing-normalized). **NOT conformed** to a single enum. NULL for CPSC and NHTSA.
- **populated_by:** CPSC – FDA ✓ USDA ✓ NHTSA – USCG ✓ — `lifecycle_status_pop` CPSC 0, FDA 50552, NHTSA 0, USCG 1681, USDA 1217 (`audit_coverage.txt:11-15,46-55`).
- **PROPOSED:** *"Recall lifecycle/status in the source's native vocabulary (FDA: Ongoing/Completed/Terminated; USDA: Active Recall/Closed Recall/Public Health Alert; USCG: Open/Closed). NOT normalized across sources; see is_active for a conformed boolean. Sources: FDA, USDA, USCG (null for CPSC/NHTSA)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.13 `is_active` (RecallSummary / RecallDetail / ProductSearchHit) → `mart_recall_summary.is_active` (and `mart_product_search.is_active`)

- **Lineage:** conformed cross-source **tri-state** boolean DERIVED via CASE from each source's lifecycle field: FDA phase_txt Ongoing→true, Terminated/Completed→false (`recall_event.sql:134-138`); USDA Active Recall & **Public Health Alert→true**, Closed Recall→false (`:209-213`); USCG open→true, closed→false (`:370-373`). CPSC `cast(null as boolean)` (`:48`), NHTSA (`:293`). Pass-through `:100` → `mart_product_search.sql:40,63`.
- **True meaning:** whether the recall is still active. NULL for CPSC/NHTSA (no lifecycle concept). USDA PHA counts as active.
- **populated_by:** CPSC – FDA ✓ USDA ✓ NHTSA – USCG ✓ — tri-state counts f=46265, **null=39928 (== CPSC 9853 + NHTSA 30075 exactly)**, t=7185 (`audit_coverage.txt:60-62`). Product mart `is_active_pop` FDA 134602, USCG 1681, USDA 1217; CPSC/NHTSA 0 (`:117-121`).
- **PROPOSED:** *"Conformed tri-state flag for whether the recall is still active/ongoing, derived from each source's lifecycle field (FDA/USDA/USCG). null when the source has no lifecycle concept. Sources: FDA, USDA, USCG (null for CPSC/NHTSA)."*
- **Current (RecallSummary):** `"Tri-state; null for CPSC/NHTSA."` · **Current (RecallDetail):** `null` · **Current (ProductSearchHit):** `null`.
- **Discrepancy (LOW):** (a) RecallSummary description is accurate but terse — omits "derived (not raw)" and "USDA PHA = active"; (b) **RecallDetail.is_active has NO description while RecallSummary.is_active does** — inconsistent documentation of the same column across the two models. Confidence **HIGH**.
- *Note:* must **not** be conflated with `mart_recall_summary.is_currently_active` (presence-manifest flag, §3.36).

---

### 3.14 `reason_category` (RecallSummary / RecallDetail) → `mart_recall_summary.reason_category`

- **Lineage:** **USDA-only.** The staging-collapsed `recall_reason` CSV (from the post-2026-06 `field_recall_reason` jsonb array, via `jsonb_array_to_csv` then nullif) is renamed `reason_category` (`recall_event.sql:224`). Others `cast(null)`: CPSC `:53`, FDA `:146`, NHTSA `:301`, USCG `:378`. A `reason_category_tokens` jsonb array is derived once by comma-split (`:453-462`) but is **not** selected into this mart. Pass-through `:101`.
- **True meaning:** a comma-joined string of FSIS reason tokens. The base taxonomy is 9 nominal tokens, but the column is multi-valued — **~26 distinct observed combined values** (e.g. `'Misbranding, Unreported Allergens'` is one real value). NULL for the other four sources (their reason is free text in `recall_reason`). ~1.2% null even within USDA.
- **populated_by:** CPSC – FDA – USDA ✓ NHTSA – USCG – — `reason_category_pop` USDA 1202/1217 (~1.2% null), all others 0 (`audit_coverage.txt:11-15`).
- **PROPOSED:** *"Categorical recall-reason tokens from USDA's FSIS taxonomy (comma-joined, e.g. 'Unreported Allergens, Misbranding'). Sources: USDA only (null for CPSC/FDA/NHTSA/USCG, which carry only free-text reasons in recall_reason)."*
- **Current:** `null`.
- **Discrepancy:** this is one of the **5 known carry-forward findings** (see §4). Provenance confirmed; the only first-pass imprecision was framing it as a "closed 9-value" set — it is multi-valued with ~26 distinct combined values (`usda/field_audit_2026_w22.md:149,263`). Confidence **HIGH**.

---

### 3.15 `recall_reason` (RecallDetail) → `mart_recall_summary.recall_reason`

- **Raw sources:** CPSC Description (`recall_event.sql:42`), FDA productshortreasontxt (Bug-1-corrected full reason text, `:126-127`), USDA field_summary (HTML-encoded, `:203`), NHTSA DESC_DEFECT (`:285`), USCG `coalesce(problem_1, problem_2)` (≤25 chars, `:364`). Pass-through `mart_recall_summary.sql:93`; also fed into FTS `search_vector` weight C (`:139`).
- **True meaning:** free-text reason/defect narrative across all five sources. Semantics vary: CPSC/USDA are broad narratives; FDA/NHTSA are specifically the defect reason; USCG is a short capped problem note. USDA value is HTML-encoded.
- **populated_by:** all five ✓ (all map a non-null-source narrative; no per-source pop column).
- **PROPOSED:** *"Free-text recall/defect narrative, conformed across sources (CPSC Description, FDA reason-for-recall full text, USDA HTML summary, NHTSA defect summary, USCG problem note). Sources: all five. Content type and length vary by source; USDA is HTML-encoded and USCG is truncated to ~25 chars."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.16 `corrective_action` (RecallDetail) → `mart_recall_summary.corrective_action`

- **Lineage:** **NHTSA-only** — `corrective_action` lifted from RCL.txt field 22 Corrective Summary (`recall_event.sql:324`). Others `cast(null)`: CPSC `:76`, FDA `:169`, USDA `:250`, USCG `:401`. Pass-through `mart_recall_summary.sql:108`.
- **True meaning:** NHTSA-only remedy narrative (what the manufacturer/consumer should do). NULL for the other four. ~2.5% empty within NHTSA. Note: CPSC and USDA carry remedy data at the raw level (CPSC `remedies`/`remedy_options` exist in silver `recall_event.sql:64-65`) but are **not selected into this mart**.
- **populated_by:** CPSC – FDA – USDA – NHTSA ✓ USCG –.
- **PROPOSED:** *"Free-text corrective-action / remedy narrative (what the manufacturer and consumer should do). Sources: NHTSA only (null for CPSC/FDA/USDA/USCG in this model)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.
- **UNVERIFIED:** whether CPSC remedies are intentionally excluded vs not-yet-surfaced.

---

### 3.17 `consequence_of_defect` (RecallDetail) → `mart_recall_summary.consequence_of_defect`

- **Lineage:** **NHTSA-only** — source's misspelled `conequence_defect` (RCL.txt field 21 Consequence Summary) renamed to corrected `consequence_of_defect` (`recall_event.sql:325`). Others `cast(null)`: CPSC `:77`, FDA `:170`, USDA `:251`, USCG `:402`. Pass-through `mart_recall_summary.sql:109`; fed FTS weight D (`:140`).
- **True meaning:** NHTSA-only harm/consequence narrative. ~5.5% empty within NHTSA. Column name fixes the upstream typo.
- **populated_by:** CPSC – FDA – USDA – NHTSA ✓ USCG –.
- **PROPOSED:** *"Free-text description of what can happen if the defect is not remedied (harm/consequence). Sources: NHTSA only (null for CPSC/FDA/USDA/USCG)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.18 `distribution_scope` (RecallSummary / RecallDetail) → `mart_recall_summary.distribution_scope`

- **Lineage:** conformed 4-value enum `{Nationwide, International, Regional, Unspecified}`. FDA (`recall_event.sql:147` on distribution_area_summary_txt) and USDA (`:225` on states) pass through `classify_distribution_scope` macro (International checked before Nationwide; null/blank→Unspecified; `classify_distribution_scope.sql:16-21`). CPSC literal `'Unspecified'` (`:54`), USCG `'Unspecified'` (`:379`), NHTSA literal `'Nationwide'` (`:302`). NOT-NULL + accepted_values at `_silver.yml:53-57` and `_gold.yml:185-189`. Pass-through `:102`.
- **True meaning:** always-populated breadth enum. Only FDA/USDA reflect actual distribution text; **CPSC/USCG 'Unspecified' and NHTSA 'Nationwide' are policy DEFAULTS**, not agency-stated breadth (NHTSA: federal vehicle recalls are national by regulation).
- **populated_by:** all five ✓ — 100% not_null; counts Nationwide 42183 / Regional 32255 / Unspecified 11973 / International 6967, matching `_gold.yml:181-184` exactly (`audit_coverage.txt:18-22`).
- **PROPOSED:** *"Conformed distribution-breadth enum, always populated: Nationwide, International, Regional, or Unspecified. Classified from real distribution text for FDA/USDA; CPSC/USCG default to Unspecified (no distribution field) and NHTSA to Nationwide (federal vehicle recalls). Sources: all five."*
- **Current:** `null` (Pydantic has an example but no description; `_gold.yml:180-184` has a rich description worth surfacing).
- **Discrepancy (LOW):** gold yml description not mirrored into the Pydantic Field. Confidence **HIGH**.

---

### 3.19 `distribution_states` (RecallDetail) → `mart_recall_summary.distribution_states`

- **Lineage:** **USDA-only.** Staging-collapsed `states` CSV renamed `distribution_states` (`recall_event.sql:226`). Others `cast(null)`: CPSC `:55`, FDA `:148`, NHTSA `:303`, USCG `:380`. **FDA's distribution text lives in a separate column** `distribution_area_summary` (`:133`), not here. Pass-through `mart_recall_summary.sql:103`; **distinct from** the parsed `distribution_state_codes` array (`rda.* :104`).
- **True meaning:** a raw comma-joined string of USDA distribution states (e.g. `'Nationwide'`, `'Arizona, California'`) — a prose-ish scalar, NOT the parsed/validated USPS code array. May contain non-state tokens (`'Nationwide'`/`'Midwest'`).
- **populated_by:** CPSC – FDA – USDA ✓ NHTSA – USCG – — `distribution_states_pop` USDA 872/1217 (~28.4% null), all others 0 (`audit_coverage.txt:11-15`).
- **PROPOSED:** *"USDA distribution-states as a raw comma-joined string (e.g. 'Nationwide', 'Arizona, California'). Sources: USDA only (null for CPSC/FDA/NHTSA/USCG). For machine-readable geography use distribution_state_codes (parsed USPS) / distribution_country_codes; do not parse this scalar."*
- **Current:** `"Agency prose (scalar string)."`
- **Discrepancy (LOW):** current is correct but does not say USDA-only / null-for-four, nor that it is distinct from the parsed codes. Confidence **HIGH**.

---

### 3.20 `hazards` (RecallDetail) → `mart_recall_summary.hazards`

- **Lineage:** **CPSC-only** jsonb array passed through (`recall_event.sql:46`). Others `cast(null as jsonb)`: FDA `:131`, USDA `:207`, NHTSA `:291`, USCG `:368`. Pass-through `mart_recall_summary.sql:107`.
- **True meaning:** CPSC jsonb array of hazard objects `[{Name, HazardType, HazardTypeID}]`. Only `Name` (free-text narrative) is populated; `HazardType`/`HazardTypeID` are empirically always empty at source. No other source has a structured hazard array (NHTSA's harm narrative is `consequence_of_defect`).
- **populated_by:** CPSC ✓ FDA – USDA – NHTSA – USCG – (only non-null branch is CPSC; other four explicit null casts).
- **PROPOSED:** *"CPSC structured hazard array (jsonb objects with a free-text 'Name' narrative; categorical HazardType/HazardTypeID are empty at source). Sources: CPSC only (null for FDA/USDA/NHTSA/USCG). NHTSA's harm narrative lives in consequence_of_defect."*
- **Current:** `"Opaque hazard objects; may be null."`
- **Discrepancy (LOW):** current understates provenance (no CPSC-only/null-for-four; no "only Name is populated"). Confidence **HIGH**.
- **UNVERIFIED:** the "HazardType/HazardTypeID empty at source" claim is from the CPSC raw dictionary, not independently re-confirmable here (no dedicated hazards coverage column).

---

### 3.21 `product_upcs` (RecallDetail) → `mart_recall_summary.product_upcs`

- **Lineage:** **CPSC-only** jsonb passthrough (`recall_event.sql:72`). Others `cast(null as jsonb)`: FDA `:165`, USDA `:246`, NHTSA `:320`, USCG `:397`. Gold stores `[{"upc":"..."}]` objects (`mart_recall_summary.sql:106`); the API `flatten_upcs` validator unwraps to bare strings (`models/common.py:13-25`, `models/recalls.py:113-117`), mapping null→`[]`.
- **True meaning:** CPSC-only, sparse recall-level array of product UPC codes (1-20 each, max observed 39). Other sources embed UPC-like codes only in free-text product descriptions.
- **populated_by:** CPSC ✓ FDA – USDA – NHTSA – USCG – — `product_upcs_nonempty` CPSC 453, all others 0; array stats non_null 9853 / empty 9400 → 453 non-empty (~4.6% of CPSC), avg_card 0.15 (`audit_coverage.txt:10,90-92`).
- **PROPOSED:** *"Recall-level product UPC codes (flattened from gold's [{upc:…}] objects to bare strings; [] when absent). Sources: CPSC only and sparse (~4.6% of CPSC recalls); null/empty for FDA/USDA/NHTSA/USCG."*
- **Current:** `"Recall-level UPCs (CPSC-sourced; sparse). Flattened from gold's object array."` — accurate and complete.
- **Discrepancy: NONE** (could add explicit "[] for non-CPSC" but not required). Confidence **HIGH**. (First-pass "~2.7%" sparse rate corrected to ~4.6% by gold count; both reflect "sparse".)

---

### 3.22 `primary_firm_name` (RecallSummary / RecallDetail) → `mart_recall_summary.primary_firm_name`

- **Lineage:** `firm_rollup` CTE — `(array_agg(f.canonical_name order by CASE role manufacturer=1 establishment=2 filer=3 importer=4 distributor=5 else=6, f.canonical_name))[1]` from `recall_event_firm` join `firm` (`mart_recall_summary.sql:48-58`, exposed `:111`, LEFT JOIN `:143` → NULL possible). Role split confirmed in `recall_event_firm.sql`: CPSC manufacturer/importer/distributor (`:46-70`), FDA establishment (`:72-84`), USDA establishment (`:86-103`), NHTSA filer (`:115`) + manufacturer (`:125`), USCG manufacturer (`:146`). `canonical_name = (array_agg(resolved_name order by resolved_name))[1]` (`firm.sql:216`).
- **True meaning:** the single display firm name, picked by role priority (manufacturer > establishment > filer > importer > distributor, alphabetical tiebreak). **Not necessarily the manufacturer** — establishment for FDA/USDA, possibly filer for NHTSA, possibly importer/distributor for CPSC (~55% of CPSC recalls name no manufacturer). It is the cleaned `firm.canonical_name`, not the raw source string. NULL possible for firm-less recalls.
- **populated_by:** all five ✓ — role counts establishment 12464 / manufacturer 8446 / filer 3213 / importer 2549 / distributor 1546 (all nonzero); source counts FDA 12047 / CPSC 8062 / NHTSA 3447 / USCG 710 / USDA 531 (`audit_coverage.txt:294-310`). NULL-firm path substantiated by 14 zero-recall firms + the documented USCG Finding-S exclusion (`recall_event_firm.sql:180-182`).
- **PROPOSED:** *"Primary display firm for the recall: the single firm name picked from all linked firms by role priority (manufacturer > establishment > filer > importer > distributor, then alphabetical). Cleaned, cross-source-deduped canonical name. Role varies by source. Sources: CPSC, FDA, USDA, NHTSA, USCG. Null only if a recall has no resolvable firm."*
- **Current:** `null` (no gold yml description either).
- **Discrepancy: NONE** (nothing to compare). Confidence **HIGH**.
- **UNVERIFIED:** exact corpus rate of NULL primary_firm_name (zero-bridge recalls) and the role-win distribution not separately tabulated.

---

### 3.23 `firm_count` (RecallSummary / RecallDetail) → `mart_recall_summary.firm_count`

- **Lineage:** `count(distinct ref.firm_id)` grouped by recall_event_id (`mart_recall_summary.sql:36`, group `:61`); `coalesce(fr.firm_count, 0)` (`:112`) → never NULL. `bigint` (`audit_schema.txt:208`).
- **True meaning:** number of DISTINCT canonical firms across all roles. **`count(distinct firm_id)`**, so a firm in two roles on one recall (e.g. NHTSA filer == manufacturer) counts once — `firm_count` can be `< len(firms)`. Coalesced to 0.
- **populated_by:** all five ✓ (source-agnostic count; all sources contribute bridge rows).
- **PROPOSED:** *"Count of distinct firms linked to this recall across all roles (count(distinct firm_id)). A firm in multiple roles counts once, so this may be less than len(firms). 0 when no firm resolves. Always present (non-null integer). Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.
- **UNVERIFIED:** corpus frequency of `firm_count = 0`.

---

### 3.24 `firms` (RecallDetail) → `mart_recall_summary.firms`

- **Lineage:** `jsonb_agg(jsonb_build_object('firm_id', ref.firm_id, 'name', f.canonical_name, 'role', ref.role, 'match_confidence', ref.match_confidence) order by ref.role, f.canonical_name)` (`mart_recall_summary.sql:37-45`); `coalesce(fr.firms, '[]'::jsonb)` (`:113`) → **ALWAYS a (possibly empty) array, never NULL** (ADR-0042 invariant the API relies on to type the field `list`, not `list | None`).
- **True meaning:** array of all firms, **one element per (firm, role) bridge row** — an NHTSA filer that is also the manufacturer appears twice, so `len(firms) ≥ firm_count`. `name` = cleaned `firm.canonical_name`. `match_confidence` exposes the firm-resolution path (`exact_name` default + per-source disambiguation tiers). Roles: manufacturer/importer/distributor (CPSC), establishment (FDA/USDA), filer+manufacturer (NHTSA), manufacturer (USCG); **retailers deliberately absent** (CPSC Option B).
- **populated_by:** all five ✓.
- **PROPOSED:** *"Array of all firms tied to this recall, one object per firm-role: {firm_id, name, role, match_confidence}, ordered by role then name. Roles vary by source (manufacturer/importer/distributor, establishment, filer). name is the cleaned canonical firm name; match_confidence is the firm-resolution path/quality. Always a (possibly empty) array, never null. Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null` (Pydantic). Existing gold yml: `"jsonb array of {firm_id, name, role, match_confidence} for the recall."` (`_gold.yml:191`).
- **Discrepancy (LOW):** the gold yml description is accurate but thin — omits the ordering, the per-role-row grain, that `name` is canonical, and the never-null/empty-array ADR-0042 invariant. Confidence **HIGH**.
- **UNVERIFIED:** corpus rate of empty `[]` firms arrays; match_confidence value distribution per source.

---

### 3.25 `product_count` (RecallSummary / RecallDetail) → `mart_recall_summary.product_count`

- **Lineage:** `product_rollup` `count(*)` over `recall_product` grouped by recall_event_id (`mart_recall_summary.sql:67`); `coalesce(pr.product_count, 0)` (`:115`). Silver per-source grain differs: CPSC explodes `Products[]` (`recall_product.sql:38-66`), FDA per-PRODUCTID (`:86-88`), **USDA `recall_product_id = recall_event_id`, one row per recall** (`:118-119`), NHTSA md5 7-tuple snapshot (`:146-183`), **USCG one row per recall** (`:188-189`).
- **True meaning:** count of distinct `recall_product` rows for the event. **USDA and USCG are structurally always 1** (one-product-per-recall modeling, ADR 0002 defers USDA product_items parsing); CPSC/FDA/NHTSA can exceed 1. `count(*)` but `recall_product_id` is unique per row, so it equals the distinct product count.
- **populated_by:** all five ✓ — corroborated by event→product row counts: CPSC 9853→11839, FDA 50552→134602, NHTSA 30075→321223 (fan-out); **USCG 1681→1681 and USDA 1217→1217 (exactly 1:1)**.
- **PROPOSED:** *"Number of distinct product rows associated with this recall (derived count over recall_product, grouped by recall event). Per-source grain: CPSC = count of items in the source Products[] array (usually 1, up to ~57); FDA = count of recalled product lines (PRODUCTIDs); NHTSA = count of distinct recall-component rows in the campaign; USDA and USCG are always 1 (these sources are modeled at one-product-per-recall; their product detail is not exploded). Never null (floored to 0). Sources: all five (CPSC, FDA, NHTSA can exceed 1; USDA, USCG always 1)."*
- **Current:** `null` (gold yml has only a not_null test).
- **Discrepancy: NONE.** Confidence **HIGH**.
- **UNVERIFIED:** at-scale per-source distribution not re-measured; CPSC max=57 figure from field-audit, not re-run.

---

### 3.26 `product_names` (RecallDetail) → `mart_recall_summary.product_names`

- **Lineage:** silver `product_name` unioned from five distinct source fields: CPSC `Products[].Name` (`recall_product.sql:42`), FDA `productdescriptiontxt` (`:92`), USDA `title` (`:122`), NHTSA `compname` (`:157`), USCG `model_name` (`:192`). Gold: `jsonb_agg(distinct product_name) filter (where product_name is not null)` (`mart_recall_summary.sql:68`); `coalesce(pr.product_names, '[]')` (`:116`).
- **True meaning:** deduplicated array of distinct product names. **Cross-source semantic alias** — a true product/model name only for CPSC and USCG; for FDA it is the paragraph-length product DESCRIPTION (Bug 3, no short-name field); for USDA the recall TITLE; for NHTSA the COMPONENT description. USDA/USCG always single-element; CPSC/FDA/NHTSA can have several. Never null (`[]`).
- **populated_by:** all five ✓.
- **PROPOSED:** *"Deduplicated array of product names for the recall (jsonb array of distinct, non-null recall_product.product_name; never null, [] when empty). Source-dependent semantics: CPSC = product name (Products[].Name); USCG = boat model name; FDA = the product DESCRIPTION text (no short name field exists — paragraph-length); USDA = the recall TITLE (firm + product + reason); NHTSA = the recalled COMPONENT description. USDA/USCG always yield a single element; CPSC/FDA/NHTSA may yield several. Sources: all five."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.
- **UNVERIFIED → corrected:** the first-pass "CPSC 3.3% empty (archival cohort)" caveat is **unsupported** — CPSC `product_name` is 100% non-null in gold (11839/11839). Real null exposure is FDA ~0.01% (18 rows) and USCG ~6.2% (`audit_coverage.txt:117-120`).

---

### 3.27 `models` (RecallDetail) → `mart_recall_summary.models`

- **Lineage:** silver `model` = CPSC `Products[].Model` (`recall_product.sql:44`), NHTSA `modeltxt` (`:158/159`); FDA/USDA/USCG `cast(null as text)` (`:97/124/196` — USCG via the Bug 1 fix: boat name routed to `product_name`, not `model`). Gold: `jsonb_agg(distinct model) filter (where model is not null)` (`mart_recall_summary.sql:70`); `coalesce(pr.models, '[]')` (`:117`).
- **True meaning:** deduplicated array of model identifiers — **effectively NHTSA-only** (MODELTXT, e.g. 'F-150'). FDA/USDA/USCG are NULL by construction. **CPSC is the subtle case:** `Products[].Model` is non-null but **empty string (`""`)** on 100% of rows (`prod.value->>'model'`); because the gold filter is only `where model is not null` (NOT `<> ''`), CPSC empty-string models **pass the filter and appear in the array as `""`**.
- **populated_by:** CPSC **Y (`""` only)**, FDA – USDA – NHTSA ✓ USCG – — `model_pop` CPSC 11839/11839 (empty strings), NHTSA 321223/321223; FDA/USDA/USCG 0 (`audit_coverage.txt:117,227-231`; `audit_coverage.sql:137` comment "confirm CPSC+NHTSA only carry model").
- **PROPOSED:** *"Deduplicated array of product model identifiers for the recall (jsonb array of distinct, non-null recall_product.model; never null, [] when empty). Populated only for NHTSA, from MODELTXT (the recalled vehicle/equipment model, e.g. 'F-150'). Always [] for FDA, USDA, and USCG (model is NULL by construction — USCG's boat name is exposed as a product name, not a model). For CPSC the source Products[].Model is empty at source, so the array may contain a literal empty string ''. Sources: NHTSA (CPSC contributes only empty-string values)."*
- **Current:** `null`.
- **Discrepancy:** this is one of the **5 known carry-forward findings** ("product model"). Provenance/no-useful-CPSC-model is right, but the first pass's `populated_by.CPSC = false` and "100% EMPTY" framing were **wrong**: CPSC is non-null empty-string, not NULL, and the empties survive the not-null filter (so the `models` array can contain `""` for CPSC recalls). Confidence **HIGH** on the correction; first-pass `confirmed` was false for exactly this reason.

---

### 3.28 `hins` (RecallDetail) → `mart_recall_summary.hins`

- **Lineage:** **USCG-only.** `hin` = USCG hin (`recall_product.sql:202`); CPSC/FDA/USDA/NHTSA `cast(null as text)` (`:78/103/132/166`). Gold: `jsonb_agg(distinct hin) filter (where hin is not null)` (`mart_recall_summary.sql:71`); `coalesce(pr.hins, '[]')` (`:118`).
- **True meaning:** deduplicated array of Hull Identification Numbers (boating analog of VIN/UPC). USCG one-product-per-recall, so a populated array has exactly one HIN. ~54% of USCG recalls carry a real HIN. **The `'N/A'` sentinel (~1.2%) is NOT NULL**, so it passes the `filter (where hin is not null)` and can appear as the literal string `'N/A'`.
- **populated_by:** CPSC – FDA – USDA – NHTSA – USCG ✓ — `hin_pop` USCG 914/1681 (~54.4%), others 0 (`audit_coverage.txt:120,236-240`).
- **PROPOSED:** *"Deduplicated array of USCG Hull Identification Numbers (HINs) for the recall (jsonb array of distinct, non-null recall_product.hin; never null, [] when empty). USCG-only — the boating analog of a VIN/UPC. Always [] for CPSC, FDA, USDA, and NHTSA (no hull-ID concept). Only ~54% of USCG recalls carry a real HIN; ~1% carry the literal 'N/A' sentinel (which survives the not-null filter) and ~46% are empty. Sources: USCG only."*
- **Current:** `"USCG Hull IDs."`
- **Discrepancy (LOW):** current is accurate but understates caveats (`[]` for four sources; only ~54% populated; the `'N/A'` literal leak). Confidence **HIGH** (first-pass ~52.8% real-HIN split corrected to ~54.4% net non-null by gold count; the real/`'N/A'` sub-split is unverified here).
- **UNVERIFIED:** whether any upstream step nullifies `'N/A'` before gold (recall_product passes it verbatim, so it appears to survive).

---

### 3.29 `recall_product_id` (ProductSearchHit) → `mart_product_search.recall_product_id`

- **Lineage:** per-source surrogate PK in silver `recall_product`: CPSC `md5('CPSC'|recall_number|product_ordinal)` (ADR 0031 stable (event,ordinal), name/model demoted out of the key, `:66`), FDA `md5('FDA'|productid)` (`:88`), USDA `md5('USDA'|recall_number)` (`:118`), NHTSA md5 7-tuple from the SCD-2 current view (`:153,182`), USCG `md5('USCG'|recall_number)` (`:188`); unique index `:4`. Gold pass-through verbatim (`mart_product_search.sql:47`), unique btree.
- **True meaning:** stable surrogate PK of one product row, reused verbatim from silver. md5 with per-source inputs; durable across CPSC post-publication name edits. For USDA/USCG it equals `md5(recall number)` (1:1 with the recall); for CPSC/FDA/NHTSA it is finer-grained.
- **populated_by:** all five ✓ (unique + not-null across all).
- **PROPOSED:** *"Stable surrogate primary key for a single recalled product line, reused verbatim from silver recall_product (md5 hash, unique, never null). Hash inputs are per-source: CPSC = source recall number + product ordinal (durable across product-name edits); FDA = the FDA product id; NHTSA = a 7-tuple of campaign/make/model/component identifiers (SCD-2 current); USDA and USCG = the source recall number (one product per recall). Sources: all five."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.30 `recall_event_id` (ProductSearchHit) → `mart_product_search.recall_event_id`

- **Lineage:** parent-event surrogate in silver `recall_product`: CPSC `md5('CPSC'|recall_number)` (`:41`), **FDA `md5('FDA'|recalleventid)` — the event, NOT productid** (`:89`), USDA (`:119`), NHTSA `md5('NHTSA'|campno)` (`:154`), USCG (`:189`); index `:5`. Gold pass-through (`mart_product_search.sql:48`), join key to `recall_ctx` (`:74`).
- **True meaning:** surrogate key of the parent recall EVENT. Many product rows share one `recall_event_id` for CPSC/FDA/NHTSA; 1:1 with `recall_product_id` for USDA/USCG.
- **populated_by:** all five ✓.
- **PROPOSED:** *"Surrogate key of the parent recall event for this product, reused verbatim from silver (md5, never null; joins to mart_recall_summary.recall_event_id). Per-source inputs: CPSC/USDA/USCG = source recall number; FDA = the recall EVENT id (recalleventid, not the product id); NHTSA = the campaign number (campno). Multiple products share one event for CPSC/FDA/NHTSA; 1:1 for USDA/USCG. Sources: all five."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.31 `source` (ProductSearchHit) → `mart_product_search.source`

- **Lineage:** literal constant per silver branch (`recall_product.sql:68/90/120/155/190`); gold pass-through (`mart_product_search.sql:49`); accepted_values 5-enum + not_null (`_gold.yml:245-250`).
- **True meaning:** originating source system; always exactly one of CPSC/FDA/USDA/NHTSA/USCG.
- **populated_by:** all five ✓ (`audit_coverage.txt:117-121`).
- **PROPOSED:** *"Originating data source for this product row. One of: CPSC (Consumer Product Safety Commission), FDA (iRES Enforcement Reports), USDA (FSIS), NHTSA (vehicle/equipment recalls), USCG (boating recalls). Always populated. Sources: all five."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.32 `source_recall_id` (ProductSearchHit) → `mart_product_search.source_recall_id`

- **Lineage:** source-native identifier carried from staging: CPSC RecallNumber (`recall_product.sql:69`), **FDA productid (`:91`)**, USDA field_recall_number trimmed (`:121`), NHTSA campno (`:156`), USCG recall number (`:191`). Gold pass-through (`mart_product_search.sql:50`).
- **True meaning:** source-native id; recall-grain for CPSC/USDA/NHTSA/USCG, but **product-grain for FDA** (it is `productid`, not a recall number — the FDA recall-event id is `recall_event_id`). With `source` forms the public natural key.
- **populated_by:** all five ✓ (`source_recall_id_pop = n_rows`).
- **PROPOSED:** *"Source-native recall identifier for this product, carried verbatim from staging and paired with `source` to form the public natural key. Per source: CPSC = public recall number; USDA = DDD-YYYY recall number; NHTSA = CAMPNO campaign number; USCG = recall number — all recall-grain. FDA is the exception: it is the FDA product id (productid), so it is product-grain (the FDA recall-event id is exposed separately as recall_event_id). Always populated. Sources: all five."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.33 `product_name` (ProductSearchHit) → `mart_product_search.product_name`

- **Lineage:** scalar per product row — same five-source union as `product_names` (`recall_product.sql:42/92/122/157/192`); gold pass-through (`mart_product_search.sql:51`), feeds `search_vector` (`:68`).
- **True meaning:** the un-aggregated source of `RecallDetail.product_names`. True name only for CPSC/USCG; FDA = product-description text (Bug 3), USDA = recall title, NHTSA = component description.
- **populated_by:** all five ✓.
- **PROPOSED:** *"Product name for this single recalled product. Source-dependent semantics: CPSC = product name (Products[].Name); USCG = boat model name; FDA = the product DESCRIPTION text (paragraph-length, no short-name field); USDA = the recall TITLE (firm + product + reason); NHTSA = the recalled COMPONENT description. May be null/empty for some rows (e.g. ~6% of USCG; ~0.01% of FDA). Sources: all five."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**. (First-pass "CPSC ~3.3% empty" caveat corrected: CPSC is 100% non-null in gold; real null exposure is FDA ~0.01% / USCG ~6.2%.)

---

### 3.34 `product_description` (ProductSearchHit) → `mart_product_search.product_description`

- **Lineage:** CPSC `Products[].Description` (`recall_product.sql:43`), FDA `productdescriptiontxt` (= `product_name`, Bug 3, `:96`), USDA `product_items` (`:123`), NHTSA `mfr_comp_desc` (`:158`), USCG `coalesce(problem_1, problem_2)` (`:193`). Gold pass-through (`mart_product_search.sql:52`), feeds `search_vector`.
- **True meaning:** free-text product description; heterogeneous and partly populated. FDA duplicates `product_name`; USDA = product-items blob (~40% null); NHTSA = supplier component description; USCG = the defect/reason narrative (≤25 chars). **CPSC is non-null but empty string (`""`)** — `Products[].Description` is empty at source, carried verbatim (no filter on the per-row scalar passthrough), feeds `search_vector` via `coalesce(...,'')`.
- **populated_by:** CPSC **Y (`""` only)**, FDA ✓ USDA ✓ NHTSA ✓ USCG ✓ — `product_description_pop` CPSC 11839/11839 (empty strings), FDA 134584/134602, USDA 725/1217 (~40% null), NHTSA 321223/321223, USCG 1511/1681.
- **PROPOSED:** *"Free-text description of the single recalled product. Source-dependent: FDA = the product description text (same value as product_name); USDA = the product-items blob (embedded UPCs, lot codes, weights; ~40% null); NHTSA = the manufacturer-supplied component description; USCG = the defect-narrative (problem_1/problem_2, capped at 25 chars — effectively a reason snippet, not a neutral description). CPSC carries only an empty string (its per-product description field is empty at source). Sources: FDA, USDA, NHTSA, USCG (empty-string for CPSC)."*
- **Current:** `null`.
- **Discrepancy: NONE** (no current doc). Confidence **HIGH** on the corrections; first-pass `confirmed` was false because it marked **CPSC false** by conflating empty-string with not-populated. Also note: the first-pass "NHTSA ~48% empty" caveat is contradicted by gold coverage (NHTSA `product_description` 100% non-null in gold — the ~48% is likely empty-string-at-source, same conflation).

---

### 3.35 `model` (ProductSearchHit) → `mart_product_search.model`

- **Lineage:** same as `RecallDetail.models` but scalar/per-product: CPSC `Products[].Model` (empty), NHTSA `modeltxt` (`recall_product.sql:159`), FDA/USDA/USCG NULL (`:97/124/196`). Gold pass-through (`mart_product_search.sql:53`), **btree-indexed** for exact lookup (`:7`).
- **True meaning:** scalar model id, effectively NHTSA-only (MODELTXT). FDA/USDA/USCG NULL by construction. **CPSC is non-null empty string (`""`)** — and because gold passes `rp.model` verbatim, the btree on `model` indexes the CPSC empty strings too (an exact-match on `''` would return all CPSC rows).
- **populated_by:** CPSC **Y (`""` only)**, FDA – USDA – NHTSA ✓ USCG – — `model_pop` CPSC 11839/11839, NHTSA 321223/321223; FDA/USDA/USCG 0 (`audit_coverage.txt:117,227-231`).
- **PROPOSED:** *"Product model identifier for exact-match lookup (btree-indexed). Populated only for NHTSA, from MODELTXT (the recalled vehicle/equipment model). Null for FDA, USDA, USCG (no model concept; USCG's boat name is in product_name). CPSC carries only an empty string (Products[].Model is empty at source) — note the btree indexes these empty strings. Sources: NHTSA (CPSC contributes only empty-string values)."*
- **Current:** `null`.
- **Discrepancy: NONE** (no current doc). Confidence **HIGH** on corrections; first-pass `confirmed` false for the same CPSC empty-string-vs-NULL conflation as §3.27.

---

### 3.36 `type` (ProductSearchHit) → `mart_product_search.type`

- **Lineage:** CPSC `Products[].Type` (`recall_product.sql:45`), FDA `producttypeshort` (`:98`), USDA `processing` (Bug 1, comma-joined multi-value, `:127`), NHTSA `rcltype` (Bug 1, `:161`), USCG `boat_type` (`:197`). USDA-only `processing_categories` jsonb derived from this column (`:245-254`). Gold pass-through (`mart_product_search.sql:54`).
- **True meaning:** cross-source product-category label, **vocabulary entirely source-specific and NOT harmonized**: FDA commodity (Devices/Food/Drugs/Veterinary/Biologics/Cosmetics); USDA FSIS processing category (comma-joined when multi-valued); NHTSA single-letter recall-type code (V/T/E/C/I/X); USCG 2-digit numeric boat-type code (name lookup undocumented); CPSC free-text type. Compare only within a single source.
- **populated_by:** all five ✓ — by gold coverage non-null is ~100% CPSC / ~64% USCG, with blanks (empty strings) for the rest: CPSC blank type=4783 (so ~59.6% non-blank), USCG blank=599 (`audit_coverage.txt:117,120,176,178`). Vocabularies confirmed (`:166-208`).
- **PROPOSED:** *"Source-specific product category code/label (vocabulary is NOT harmonized across sources): FDA = commodity (Devices/Food/Drugs/Veterinary/Biologics/Cosmetics); USDA = FSIS processing category, comma-joined if multi-valued (e.g. 'Heat Treated - Shelf Stable'); NHTSA = recall-type code (V/T/E/C/I/X); USCG = a numeric boat-type code (name lookup undocumented); CPSC = a free-text product type (~60% non-blank). Compare only within a single source. Sources: all five."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH** (first-pass "CPSC ~60% populated / USCG ~35% null" reframed: non-null is ~100% CPSC / ~64% USCG — the gaps are empty strings, not NULL).
- **UNVERIFIED:** USCG boat_type code-to-name mapping (USCG OII ask pending).

---

### 3.37 `model_year` (ProductSearchHit) → `mart_product_search.model_year`

- **Lineage:** NHTSA `model_year` (from YEARTXT, `'9999'`→NULL in staging, `recall_product.sql:165`), USCG `model_year` (text, diverse formats, `:201`); CPSC/FDA/USDA NULL (`:77/102/131`). Gold pass-through verbatim (`mart_product_search.sql:55`), kept as text.
- **True meaning:** model year as text. **NHTSA + USCG only** (vehicle/vessel sources). USCG values are messy free-text (4-digit ~60%, 2-digit, ranges, `'9999'` sentinel). Kept TEXT because USCG values are not uniformly numeric.
- **populated_by:** CPSC – FDA – USDA – NHTSA ✓ USCG ✓ — `model_year_pop` NHTSA 290815/321223 (~90.5%, 9999 nulled), USCG 1137/1681 (~67.6%); CPSC/FDA/USDA 0.
- **PROPOSED:** *"Model year of the recalled item (text). Populated only for NHTSA (from YEARTXT, with the '9999' Unknown sentinel nulled) and USCG (boat model year — varied formats: 4-digit, 2-digit, or range-lists; ~32% null). Always null for CPSC, FDA, USDA (no model-year concept). Kept as text because USCG values are not uniformly numeric. Sources: NHTSA, USCG (null for CPSC/FDA/USDA)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.
- **UNVERIFIED:** whether USCG `'9999'` survives to `model_year` as text (recall_product passes verbatim; staging handling not re-read).

---

### 3.38 `hin` (ProductSearchHit) → `mart_product_search.hin`

- **Lineage:** **USCG-only.** `hin` = USCG hin (`recall_product.sql:202`); CPSC/FDA/USDA/NHTSA NULL (`:78/103/132/166`). Gold pass-through (`mart_product_search.sql:56`), **btree-indexed** for exact lookup (`:6`).
- **True meaning:** scalar HIN per product (boating analog of VIN/UPC). USCG-only; ~54% of USCG rows carry a real HIN; `'N/A'` sentinel (~1.2%) passed through verbatim (non-null), ~46% NULL.
- **populated_by:** CPSC – FDA – USDA – NHTSA – USCG ✓ — `hin_pop` USCG 914/1681, others 0 (`audit_coverage.txt:236-240`).
- **PROPOSED:** *"USCG Hull Identification Number (HIN) for the recalled boat — the boating analog of a VIN/UPC; btree-indexed for exact lookup. USCG-only: null for CPSC, FDA, USDA, NHTSA. Only ~54% of USCG products carry a real HIN; ~1% carry the literal 'N/A' sentinel and ~46% are null. Sources: USCG only."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.
- **UNVERIFIED:** whether staging nullifies the `'N/A'` sentinel (recall_product passes verbatim).

---

### 3.39 `upc` (ProductSearchHit) → `mart_product_search.upc`

- **Lineage:** `cast(null as text)` on **every** silver branch (`recall_product.sql:81/106/135/169/205`; header `:35-36`). Gold pass-through (`mart_product_search.sql:57`); the all-NULL `upc` btree was **DROPPED 2026-06-15** (gold-audit G5/O2); column kept as a forward-looking placeholder. Recall-level UPC search uses `recall_product_upcs` (jsonb GIN) instead.
- **True meaning:** per-product UPC — **NULL for every row of every source today**, a placeholder. No source supplies a product-grain UPC (CPSC UPCs are recall-level; FDA bulk returns none; USDA/NHTSA/USCG have none).
- **populated_by:** none — `upc_pop = 0` all sources, `rows_with_nonnull_upc = 0` (`audit_coverage.txt:117-121,216`); no upc index on the mart (`audit_schema.txt:241-246`).
- **PROPOSED:** *"Per-product UPC. Currently NULL for every row of every source — a forward-looking placeholder, not a populated field. No source supplies a product-grain UPC: CPSC UPCs are recall-level only (surfaced as recall_product_upcs for containment search, not here), FDA returns none via the bulk endpoint, and USDA/NHTSA/USCG have none. Sources: none (null for all five)."*
- **Current:** `"Product-grain UPC; currently null for all rows."`
- **Discrepancy (LOW):** current is accurate/concise but omits WHY (no source supplies a per-product UPC) and where to look instead (`recall_product_upcs`); could note the dropped empty btree. Confidence **HIGH**.

---

### 3.40 `recall_title` (ProductSearchHit) → `mart_product_search.recall_title`

- **Lineage:** same silver `title` as §3.6 (native CPSC/USDA, synthesized FDA/NHTSA/USCG). `recall_ctx` CTE selects `mart_recall_summary.title`, aliased `rc.title as recall_title` (`mart_product_search.sql:35,58`).
- **True meaning:** headline of the recall the product belongs to. Native for CPSC/USDA; synthesized composites for FDA/NHTSA/USCG. Non-null for all five.
- **populated_by:** all five ✓ (non-null by construction; corroborated by 100% `published_at` population).
- **PROPOSED:** *"Headline of the recall this product belongs to. Native agency title for CPSC and USDA; for FDA/NHTSA/USCG it is a synthesized title combining the recall identifier with the firm name (and boat model for USCG). Always populated. Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH** (first-pass CPSC title line `:42`; actual `:41`, immaterial).
- **UNVERIFIED:** no `_gold.yml` column description for `mart_product_search.recall_title`.

---

### 3.41 `published_at` (ProductSearchHit) → `mart_product_search.published_at`

- **Lineage:** same coalesced silver `published_at` as §3.9; `recall_ctx` selects `mart_recall_summary.published_at` as `rc.published_at` (`mart_product_search.sql:38,61`).
- **True meaning:** publication/last-published timestamp; source-specific derivation; guaranteed non-null; canonical sort/index key.
- **populated_by:** all five ✓ — 100% (`audit_coverage.txt:10-14`).
- **PROPOSED:** *"Publication / last-published timestamp of the recall record (UTC). Source-specific: CPSC LastPublishDate, FDA event-last-modified (fallback recall-initiation), USDA last-modified (fallback recall date), NHTSA record-creation (fallback report-received), USCG last-editorial (fallback announced). Always populated. Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH** (first-pass CPSC line `:40`; actual `:39`).

---

### 3.42 `url` (ProductSearchHit) → `mart_product_search.url`

- **Lineage:** same silver `url` as §3.7; `recall_ctx` selects `mart_recall_summary.url` as `rc.url` (`mart_product_search.sql:39,62`).
- **True meaning:** agency detail-page URL. CPSC/USDA/USCG populated; FDA/NHTSA NULL.
- **populated_by:** CPSC ✓ FDA – USDA ✓ NHTSA – USCG ✓ — FDA/NHTSA false forced by `cast(null)`; CPSC/USDA/USCG rest on SQL construction (no direct url coverage column).
- **PROPOSED:** *"Agency detail-page URL for the recall (CPSC cpsc.gov page, USDA fsis.usda.gov page, USCG constructed recalls-details link). Sources: CPSC, USDA, USCG (null for FDA/NHTSA)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.43 `firm_name` (ProductSearchHit) → `mart_product_search.firm_name`

- **Lineage:** `= mart_recall_summary.primary_firm_name`, aliased `firm_name` (`mart_product_search.sql:41,64`). Derived in `firm_rollup` (role-priority `array_agg`[1], `mart_recall_summary.sql:48-58`), LEFT JOIN so nullable.
- **True meaning:** primary display firm (role priority manufacturer > establishment > filer > importer > distributor, alpha tiebreak); cleaned `firm.canonical_name`. Only ONE firm shown here (the full set is `mart_recall_summary.firms`, not carried into the product mart). May be NULL when no firm resolves.
- **populated_by:** all five ✓ — source counts FDA 12047 / CPSC 8062 / NHTSA 3447 / USCG 710 / USDA 531; all roles present (`audit_coverage.txt:294-310`).
- **PROPOSED:** *"Primary display firm for the recall — canonical name of the highest-priority associated firm by role (manufacturer > establishment > filer > importer > distributor, alpha tie-break), from the cross-source firm rollup. May be null when no firm is resolvable. Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.44 `recall_product_upcs` (ProductSearchHit) → `mart_product_search.recall_product_upcs`

- **Lineage:** **CPSC-only** `product_upcs` (`recall_event.sql:72`); FDA/USDA/NHTSA/USCG `cast(null as jsonb)` (`:165/246/320/397`). `mart_recall_summary.product_upcs` (`mart_recall_summary.sql:107`) → `recall_ctx` selects it as `rc.product_upcs as recall_product_upcs` (`mart_product_search.sql:65`), **verbatim passthrough** (not flattened in gold). GIN-indexed — the real UPC-search path; the per-product `upc` column is NULL for every row.
- **True meaning:** recall-level (recall-event grain) UPC codes denormalized onto each product row for UPC-containment search. CPSC-only and sparse (~4.6% of CPSC recalls). NULL for the other four (USDA UPCs are buried in free-text product_items; vehicles/boats use VIN/HIN).
- **populated_by:** CPSC ✓ FDA – USDA – NHTSA – USCG – — `recall_product_upcs_nonempty` CPSC 466, all others 0 (`audit_coverage.txt:117`).
- **PROPOSED:** *"Recall-level UPC codes (recall-event grain, denormalized onto each product row for UPC-containment search). Populated only for CPSC's ProductUPCs array and sparse there (~5% of CPSC recalls); the per-product upc column is null for all sources. Passed through verbatim from mart_recall_summary (not flattened in the gold mart; any flattening to strings is API-side). Sources: CPSC (null for FDA/USDA/NHTSA/USCG)."*
- **Current:** `"Recall-level UPCs, flattened from gold's object array."`
- **Discrepancy (LOW):** current understates two facts — (1) CPSC-only and sparse (no provenance tag); (2) **"flattened" is misleading** — the gold mart passes `rc.product_upcs` through verbatim; any flattening is API-side, not in gold. Confidence **HIGH**.

---

### 3.45 `firm_id` (FirmProfile) → `mart_firm_profile.firm_id`

- **Lineage:** silver `firm.sql:191` `coalesce(x.canonical_firm_id, md5(an.normalized_name))`; final `firm_id = r.canonical_firm_id` (`:214`, grouped `:223`). Gold pass-through (`mart_firm_profile.sql:113`); not_null + unique + relationships (`_gold.yml:210-217`).
- **True meaning:** synthetic PK of the canonical (cross-source clustered) firm — the cluster-representative id from the Phase 6b crosswalk, falling back to `md5(normalized name)` for unclustered names. A firm appearing under several agencies collapses to one `firm_id`. **Not stable across rebuilds** (md5 of a normalized name changes if the representative name or clustering changes).
- **populated_by:** all five ✓ (derived key; all sources contribute names — `audit_coverage.txt:294-301`).
- **PROPOSED:** *"Synthetic primary key of the canonical firm (cross-source cluster). Derived as the cluster representative id from the Phase 6b firm-resolution crosswalk, falling back to md5(normalized firm name) for unclustered names. One row per canonical firm across all agencies. Always present. Sources: derived (all of CPSC/FDA/USDA/NHTSA/USCG contribute firm names that resolve to a firm_id)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**. **Correction to first-pass framing:** the "firm_crosswalk has 0 rows until the resolver runs" caveat overstates live state — `has_alternate_names=1213`, `has_structural_ids=20994` (`audit_coverage.txt:251`) show clustering **has** been applied in the live gold build; `firm_id` is genuinely a cross-source cluster id, not always a singleton md5.
- **UNVERIFIED:** the RapidFuzz/FEI-merge logic inside the `recalls resolve-firms` CLI (Python, not read).

---

### 3.46 `canonical_name` (FirmProfile) → `mart_firm_profile.canonical_name`

- **Lineage:** `canonical_name = (array_agg(r.resolved_name order by r.resolved_name))[1]` where `resolved_name = coalesce(x.canonical_name, an.raw_name)` (`firm.sql:192,216`). Raw names: CPSC `firm_json->>'name'` (`:63`), FDA `firm_legal_nam` (`:77`), USDA `r.establishment` (`:88`), NHTSA `mfgname`/`mfgtxt` (`:106/115`), USCG `coalesce(directory.company_name, recalls.company_name, mic)` (`:157`). not_null. Gold pass-through (`mart_firm_profile.sql:114`).
- **True meaning:** human-readable representative name of the canonical firm — either the crosswalk cluster name, or (for unclustered firms) the **alphabetically-first** raw firm name in the cluster. Not an authoritative legal name. For USCG it can degrade to a bare MIC. Excludes CPSC retailers.
- **populated_by:** all five ✓ (every firm has a name from ≥1 source; not_null across 24331 firms).
- **PROPOSED:** *"Human-readable display name of the canonical firm — the cluster's resolved canonical name, or the representative (alphabetically-first) raw firm name when unclustered. Always present. Sources: CPSC (manufacturer/importer/distributor name), FDA (firmlegalnam), USDA (field_establishment), NHTSA (mfgname/mfgtxt), USCG (directory or scraped company name, MIC as last resort)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.47 `normalized_name` (FirmProfile) → `mart_firm_profile.normalized_name`

- **Lineage:** `normalized_name = upper(trim((array_agg(r.resolved_name order by r.resolved_name))[1]))` (`firm.sql:215`) — upper-trim of the **same** representative `resolved_name` that yields `canonical_name`. The per-CTE `normalized_name` only feeds the md5 key. **Unique test dropped** (Phase 6b critic C5 — two spellings can clean to one canonical); not_null retained; btree-indexed (`firm.sql:5`, `mart_firm_profile.sql:5`, `audit_schema.txt:240`).
- **True meaning:** upper/whitespace-normalized display/search representative. **NOT unique** — `firm_id` is the key. Only `upper()+trim()`, no punctuation/legal-suffix stripping (`'AC DELCO'` vs `'ACDELCO'` stay distinct). Can be a bare MIC for USCG.
- **populated_by:** all five ✓.
- **PROPOSED:** *"Upper-cased, whitespace-trimmed form of the firm's representative name, for case-insensitive lookup. A display/search representative of the canonical firm, not a unique key (firm_id is the key). Always present. Sources: same upstream firm-name fields as canonical_name (CPSC/FDA/USDA/NHTSA/USCG)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.48 `observed_names` (FirmProfile) → `mart_firm_profile.observed_names`

- **Lineage:** `observed_names = jsonb_agg(distinct r.raw_name)` over the resolved CTE grouped by `canonical_firm_id` (`firm.sql:217`). `raw_name` is the un-normalized per-source name from every source CTE unioned in `all_normalized` (`:168-178`). Gold pass-through (`mart_firm_profile.sql:116`); jsonb (`audit_schema.txt:153`).
- **True meaning:** jsonb array of every distinct RAW (un-normalized) firm name that collapsed into this canonical firm — case/whitespace variants and per-source spellings; the provenance/audit trail. Distinct is exact-string. For USCG mic-only firms an entry may be a bare MIC. Always ≥1 element.
- **populated_by:** all five ✓.
- **PROPOSED:** *"JSONB array of all distinct raw firm-name surface forms (across sources and spellings) that map to this canonical firm — the provenance/audit trail of names that were collapsed together. Always present (>=1 element). Sources: CPSC/FDA/USDA/NHTSA/USCG firm-name fields."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.49 `observed_company_ids` (FirmProfile) → `mart_firm_profile.observed_company_ids`

- **Lineage:** `observed_company_ids = jsonb_agg(distinct r.company_id) FILTER (where company_id is not null)` (`firm.sql:218-219`). Per source: **FDA `firm_fei_num::text`** (`:79`), **USDA `e.establishment_number`** via LEFT JOIN on normalized name (`:90-93`), **USCG `r.mic`** (`:160`); CPSC `firm_json->>'company_id'` (100% empty at source), NHTSA `cast(null as text)` (`:108/117`). Gold pass-through (`mart_firm_profile.sql:117`); also UNNESTED and left-joined id→sidecar (FDA FEI→`firm_fda_attributes`, USDA establishment_number→`firm_usda_attributes`, USCG MIC→`firm_uscg_attributes`, `:22-52`).
- **True meaning:** jsonb array of distinct structured source-issued firm ids — **FDA FEI numbers, USDA FSIS establishment numbers, USCG MICs**. NULL/absent for CPSC-only and NHTSA-only firms (CPSC CompanyID is empty at source; NHTSA has no firm-id analog), and for FDA/USDA/USCG firms missing their structured id. The id namespaces are disjoint (long-numeric FEI vs `'M1234'` establishment vs 3-char MIC), enabling sidecar routing.
- **populated_by:** CPSC – FDA ✓ USDA ✓ NHTSA – USCG ✓ — `has_structural_ids=20994` of 24331; sidecar blocks FDA 12010 / USCG 678 / USDA 529 (`audit_coverage.txt:251`); sidecar tables 13418 / 16260 / 8003 rows (`audit_schema.txt:26-28`).
- **PROPOSED:** *"JSONB array of distinct structured firm identifiers observed for this firm: FDA FEI numbers, USDA FSIS establishment numbers, and USCG MICs. Null/empty for firms sourced only from CPSC (CompanyID is empty at source) or NHTSA (no firm-id field). Sources: FDA, USDA, USCG (null for CPSC/NHTSA)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**. Sharper-than-first-pass nuance: the not-null filter catches NHTSA nulls but **not** CPSC empty-strings (`''` is not NULL) — a CPSC `''` may appear as a no-op token in the array, but sidecar routing (numeric FEI / `'M1234'` / 3-char MIC) makes it harmless, so CPSC contributes no usable id.

---

### 3.50 `alternate_names` (FirmProfile) → `mart_firm_profile.alternate_names`

- **Lineage:** originates from `enrichment.firm_crosswalk.alternate_names` (a jsonb array per crosswalk row), surfaced via `resolved` (x.alternate_names) and flattened in `alias_flat`: `jsonb_agg(distinct alias order by alias)` over `jsonb_array_elements_text(coalesce(alternate_names,'[]'))` grouped by canonical_firm_id; LEFT JOIN so firms with no aliases get NULL (`firm.sql:193,199-211,220-223`). Gold pass-through (`mart_firm_profile.sql:118`).
- **True meaning:** jsonb array of brand/surface-form aliases — DBA brands and brand-bearing parentheticals (e.g. `'John Deere'` from `'Deere & Company (John Deere)'`) extracted by the Phase 6b resolver for search + RapidFuzz match recall. **Derived enrichment, NOT copied from any single agency field.** NULL for firms with no extracted aliases (and historically NULL for all firms until the resolver runs — though `has_alternate_names=1213` shows it is now populated for some).
- **populated_by:** n/a per source (derived; `firm_crosswalk` enrichment).
- **PROPOSED:** *"JSONB array of brand/surface-form aliases for the firm (DBA brands and brand-bearing parentheticals, e.g. 'John Deere' for 'Deere & Company (John Deere)'), derived by the Phase 6b firm-resolution step for search and fuzzy matching. Null when the firm has no aliases. Sources: derived (firm_crosswalk enrichment; not a per-agency field)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **LOW** — this is the one record with **no verifier output** (the verification block returned `confirmed:false, confidence:low, "no verifier output"`). The lineage is taken from the first pass + `_silver.yml:151-156` but was **not re-verified line-by-line** in the empirical pass. See §5.
- **UNVERIFIED:** whether `firm_crosswalk.alternate_names` currently has rows (the `has_alternate_names=1213` count from `firm_id`'s verification suggests yes, but `alternate_names`'s own block was not independently confirmed); the alias-extraction rules inside the CLI (Python, not read).

---

### 3.51 `total_recalls` (FirmProfile) → `mart_firm_profile.total_recalls`

- **Lineage:** `firm_event_stats.total_recalls = count(distinct recall_event_id)` over `firm_recalls` (recall_event_firm join recall_event) grouped by firm_id (`mart_firm_profile.sql:75`, group `:81`); `coalesce(fes.total_recalls, 0)` (`:119`); not_null (`_gold.yml:221-223`). `firm_id` is the cross-source 6b cluster id.
- **True meaning:** total DISTINCT recall events the canonical firm is linked to, summed **across every source the firm appears in**. A firm in multiple roles on one recall counts once. Always present (coalesce 0).
- **populated_by:** all five ✓ — a firm can carry up to 3 source keys (460 firms span 2 sources, 10 span 3, `audit_coverage.txt:286-292`); `max_total_recalls=1952` (e.g. FORD MOTOR COMPANY, `:501`); 14 zero-recall firms coalesce to 0 (`:278`).
- **PROPOSED:** *"Total distinct recalls this firm is linked to, across all sources the firm appears in (count(distinct recall_event_id)). The firm_id is a cross-source cluster, so this aggregates a firm's recalls across agencies. A firm in multiple roles on one recall counts that recall once. Always present (non-null integer). Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.52 `active_recalls` (FirmProfile) → `mart_firm_profile.active_recalls`

- **Lineage:** `count(distinct recall_event_id) FILTER (where is_active)` over `firm_recalls`; `coalesce(...,0)` (`mart_firm_profile.sql:76,120`). `is_active` is tri-state in silver (CPSC `cast NULL`, NHTSA `cast NULL`; FDA/USDA/USCG derived). **FILTER keeps only TRUE rows — NULL and FALSE are both dropped.**
- **True meaning:** count of distinct currently-active recalls. **Source-asymmetric:** because `is_active` is NULL for CPSC and NHTSA, those recalls **NEVER** count toward `active_recalls` — a firm with only CPSC/NHTSA recalls has `active_recalls=0` regardless of real-world status. Only FDA/USDA/USCG recalls can be active. Always present (coalesce 0).
- **populated_by:** CPSC – FDA ✓ USDA ✓ NHTSA – USCG ✓ — empirically backed by `is_active_pop` by source: CPSC=0, FDA=50552, NHTSA=0, USCG=1681, USDA=1217 (`audit_coverage.txt:10-14`); `firms_with_active=2662` (`:278`).
- **PROPOSED:** *"Count of this firm's distinct currently-active recalls (count(distinct recall_event_id) where is_active). Only FDA, USDA, and USCG recalls can be active; CPSC and NHTSA have no lifecycle status (is_active NULL) and never count. Always present (non-null integer; 0 if none). Sources counted: FDA, USDA, USCG (CPSC/NHTSA never contribute)."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**. Minor wording nit (not a population error): the first-pass `active_recalls` raw_field for USDA says `field_active_notice`, but silver `is_active` is derived from `recall_type` (`recall_event.sql:209-213`); `active_notice` is a separate staging column not used for `is_active`.

---

### 3.53 `first_recall_at` (FirmProfile) → `mart_firm_profile.first_recall_at`

- **Lineage:** `min(published_at)` over `firm_recalls` grouped by firm_id (`mart_firm_profile.sql:77`), **NOT coalesced** (`:121`). `published_at` is per-source-coalesced (§3.9).
- **True meaning:** earliest `published_at` across the firm's recalls. **Based on `published_at` (a per-source 'last published / record-created' date), NOT `announced_at`** — not the public announcement date. min across all sources the firm spans.
- **populated_by:** all five ✓ — `published_at_pop=100%` all sources, so populated for any firm with ≥1 recall. **NULL for exactly 14 zero-recall firms** (`first_recall_at_pop=24317 of 24331`, `audit_coverage.txt:496`).
- **PROPOSED:** *"Earliest recall publication timestamp for this firm (min of published_at across its recalls). published_at is a per-source 'last published / record-created' date (CPSC LastPublishDate, FDA event-last-modified, USDA last-modified, NHTSA record-creation, USCG last-edit), not a uniform announcement date. Populated for any firm with at least one recall. Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH** (the first-pass's "NULL reachable?" hedge is now confirmed: NULL for the 14 zero-recall firms).

---

### 3.54 `last_recall_at` (FirmProfile) → `mart_firm_profile.last_recall_at`

- **Lineage:** symmetric to §3.53 — `max(published_at)` over the firm's recalls, not coalesced (`mart_firm_profile.sql:78,122`).
- **True meaning:** latest `published_at` across the firm's recalls. Same per-source `published_at` semantics caveat; not the announcement date.
- **populated_by:** all five ✓ — NULL only for the same **14** zero-recall firms (`last_recall_at_pop=24317 of 24331`).
- **PROPOSED:** *"Most recent recall publication timestamp for this firm (max of published_at across its recalls). published_at is a per-source 'last published / record-created' date, not a uniform announcement date. Populated for any firm with at least one recall. Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH**.

---

### 3.55 `roles` (FirmProfile) → `mart_firm_profile.roles`

- **Lineage:** `jsonb_agg(distinct role)` over `firm_recalls` grouped by firm_id (`mart_firm_profile.sql:79`), **not coalesced** (`:123`). Role vocabulary = silver accepted set manufacturer/importer/distributor/establishment/filer, **retailer absent** (CPSC Option B, `_silver.yml:299-304`).
- **True meaning:** jsonb array of DISTINCT roles the canonical firm has played across all its recalls. A cross-source firm can carry several roles (e.g. an FDA establishment + NHTSA manufacturer → `['establishment','manufacturer']`). `'establishment'` (FDA/USDA) = recalling establishment, not literally manufacturer; `'filer'` (NHTSA) = Part-573 filer, not necessarily the maker.
- **populated_by:** all five ✓ — all roles nonzero (`audit_coverage.txt:303-310`); all sources contribute (`:294-301`). **NULL for the 14 zero-recall firms** (`jsonb_agg` over an empty group returns NULL, not coalesced).
- **PROPOSED:** *"Distinct set of roles this firm has played across all its recalls, as a JSONB array. Values: manufacturer, importer, distributor (CPSC), establishment (FDA/USDA), filer/manufacturer (NHTSA), manufacturer (USCG). A cross-source firm may carry several roles. Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **HIGH** (first-pass "NULL vs [] for zero-bridge firms" resolved to NULL for the 14 zero-recall firms).

---

### 3.56 `recalls_by_source` (FirmProfile) → `mart_firm_profile.recalls_by_source`

- **Lineage:** `firm_source_agg.recalls_by_source = jsonb_object_agg(source, count(distinct recall_event_id))` over `(firm_id, source)` (`mart_firm_profile.sql:84-92`), **not coalesced** (`:124`); `_gold.yml:224-225`.
- **True meaning:** sparse jsonb object mapping each source (UPPERCASE) → distinct recall count for the firm. **Only sources where the firm has ≥1 recall appear as keys** (`n_source_keys` distribution: 14 firms=0 keys, 23847=1, 460=2, 10=3, `audit_coverage.txt:286-292`). Values sum to `total_recalls`. Keys are the closed UPPERCASE source enum. **NULL for the 14 zero-recall firms** (`jsonb_object_agg` over empty group → NULL, uncoalesced).
- **populated_by:** all five ✓ (all appear as keys across the corpus).
- **PROPOSED:** *"JSONB object mapping source -> distinct recall count for this firm (e.g. {'NHTSA': 12, 'CPSC': 3}). Only sources where the firm has at least one recall appear as keys; values sum to total_recalls. Keys are the UPPERCASE source enum. Sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null` (Pydantic). Existing gold yml: `"jsonb object {source -> distinct recall count}."` (`_gold.yml:225`).
- **Discrepancy (LOW):** the gold yml description omits that the object is sparse (only sources with ≥1 recall are keys), that keys are UPPERCASE enum, and that values sum to `total_recalls`. Confidence **HIGH**.

---

### 3.57 `distinct_products` (FirmProfile) → `mart_firm_profile.distinct_products`

- **Lineage:** `event_products` CTE: `count(distinct recall_product_id)` per recall_event_id; `firm_product_counts`: `sum(ep.n_products)` over `(select distinct firm_id, recall_event_id from firm_recalls)`; `coalesce(fpc.distinct_products, 0)` (`mart_firm_profile.sql:99-110, 125`). Computed sum-per-event (not a firm×product distinct) to avoid the firm×product fan-out bottleneck. A `recall_product_id` belongs to exactly ONE event, so per-event distinct counts sum without intra-firm double-counting — but a product on a multi-firm event is counted under **each** of those firms.
- **True meaning:** total distinct product rows across all recall events the firm is associated with (any role). **Per-firm footprint, NOT a global distinct** — summing `distinct_products` across firms over-counts shared products. For USDA/USCG-only firms it equals the distinct recall count (one product per recall). Coalesced to 0.
- **populated_by:** all five ✓ — `avg_products=25.69`, `max_products=48006`, `zero_products=14` (`audit_coverage.txt:283`); `fct_recalls_by_firm.product_count` corroborates per-firm attribution (e.g. Mercedes-Benz product_count=48006 on 517 events, `:515`).
- **PROPOSED:** *"Total distinct recalled-product rows across all recalls this firm is associated with, in any role (synthesized statistic; never null, floored to 0). Computed as the sum over the firm's distinct recall events of the per-event distinct product count — so a product on a multi-firm recall is attributed to each of those firms (this is a per-firm footprint, not a globally-deduplicated count). Because product grain is per-source, USDA/USCG-only firms have one product per recall (so this equals their recall count), while CPSC/FDA/NHTSA firms may have many products per recall. Sources: all five."*
- **Current:** `null`.
- **Discrepancy: NONE.** Confidence **MEDIUM** — the `mart_firm_profile.sql:99-110/125` CTE structure was **not re-read line-by-line** in the empirical pass; the claim rests on the first pass + corroborating coverage shapes (which are strongly consistent). See §5.

---

### 3.58 `edit_event_count` → `mart_recall_summary.edit_event_count`

- **Lineage:** `_api_synthesized`. Silver `recall_event_history` emits one row per (source, source_recall_id, langcode, field_name, changed_at) where a tracked canonical field changed between consecutive bronze content-hash snapshots. Tracked fields = `['recall_reason','classification','lifecycle_status','title','terminated_at']` (`recall_event_history.sql:40-123`, lateral unnest `:183-184`). Per-source field coverage: **CPSC** reason+title only (`:47-51`); **NHTSA** reason only (`:101-105`); **FDA** reason+classification+lifecycle+terminated, NO title (`:65-69`); **USCG** reason+classification+lifecycle+terminated, NO title (`:117-121`); **USDA** all five + langcode kept (`:83-87`). WHERE: prev_ts not null (creation excluded, `:219`), ADR-0027 rebaseline exclusion (`:220`), `norm_text_for_change` cosmetic + `''<->NULL` folding (`:221-222`). Gold `history_rollup`: `count(*) group by (source, source_recall_id)` — **drops langcode + field_name**, so USDA folds EN+ES change rows (`mart_recall_summary.sql:79-86`); `coalesce(hr.edit_event_count, 0)` (`:126`), LEFT JOIN (`:146-147`). ADR 0022: FDA's native field-history endpoints returned RESULTCOUNT 0, so ALL FIVE sources use the same LAG-over-bronze synthesis.
- **True meaning:** a synthesized activity counter — number of field-level edit events DETECTED by diffing consecutive bronze snapshots of a curated 5-field set, grouped to the recall. NOT a count of agency amendments and NOT distinct snapshots — it counts individual tracked-field value changes (a snapshot changing 3 fields contributes 3). **Bounded by bronze snapshot retention and RESET by a Phase 6a.5 re-seed** (table is SPARSE post-reseed). Distinct from the sibling `edit_count` (from `recall_lifecycle` = distinct content-hash versions).
- **populated_by:** structurally non-null for every source's rows (LEFT JOIN + coalesce 0). **Per-source non-zero population is UNVERIFIED** — the only ground truth is corpus-wide `has_been_edited t=45 / f=93333` (`audit_coverage.txt:74-78`) with **no per-source split**. The matrix marks these `n/a` precisely because the synthesized field is structurally non-null everywhere but its real edit population (which sources contribute the 45) is unknown.
- **PROPOSED:** *"Number of field-level edit events the pipeline has detected for this recall by diffing consecutive bronze snapshots of tracked event fields (recall_reason, classification, lifecycle_status, title, terminated_at). Counts change rows in the synthesized recall_event_history (one per changed tracked field per snapshot interval), grouped to the recall; 0 when no edits were detected. This is an observed-activity proxy, NOT a count of official agency amendments: cosmetic/whitespace and empty<->null flips are suppressed, and the count is bounded by bronze snapshot retention and was reset by a pipeline re-seed, so it reflects edits seen by this pipeline (not the recall's full history). Tracked fields vary by source (CPSC: reason/title; NHTSA: reason only; FDA & USCG: reason/classification/status/terminated; USDA: all five, counting English + Spanish edits). Synthesized field, populated (>=0) for all sources."*
- **Current:** `null` (and undocumented in `_gold.yml`; `bigint` `audit_schema.txt:219`).
- **Discrepancy (LOW):** undocumented; has a confusable sibling `edit_count` on the same mart with no Pydantic-level disambiguation. Confidence **HIGH on mechanism**, but first-pass `confirmed` was false because it **overclaimed per-source non-zero population** — the proposal/matrix now treat that as structural non-null only.
- **UNVERIFIED:** corpus distribution of `edit_event_count`; whether any source has meaningful edit-row population post-reseed; which sources own the 45 edited recalls.

---

### 3.59 `has_been_edited` → `mart_recall_summary.has_been_edited`

- **Lineage:** boolean existence flag over the **same** `recall_event_history` synthesis as `edit_event_count`: `(hr.source_recall_id is not null) as has_been_edited`, LEFT JOIN to `history_rollup` (`mart_recall_summary.sql:79-86,127,146-147`). True iff the recall has ≥1 detected field-level edit row; equivalent to `edit_event_count > 0`. Never null (left-join miss → false).
- **True meaning:** synthesized boolean — true iff the pipeline detected ≥1 editorially-meaningful change to a tracked field. Does NOT mean the agency formally amended the recall. Per-source tracked-field coverage means `false` is asymmetric (NHTSA `false` only means desc_defect never changed). Bounded by retention + the 6a.5 reseed, so `false` can mean "no change observed since the reseed".
- **populated_by:** structurally non-null (true/false) for every source's rows. **Per-source true population UNVERIFIED** — corpus `t=45 / f=93333` (`audit_coverage.txt:74-78`), no per-source split; which sources own the 45 is unknown.
- **PROPOSED:** *"True if the pipeline has detected at least one editorially-meaningful change to a tracked event field (recall_reason, classification, lifecycle_status, title, terminated_at) for this recall by diffing consecutive bronze snapshots; false otherwise. Equivalent to edit_event_count > 0 and never null. This is observed-edit evidence, NOT a flag of an official agency amendment: cosmetic/whitespace and empty<->null changes are suppressed, tracked fields vary by source, and detection is bounded by bronze snapshot retention and was reset by a pipeline re-seed — so false can mean 'no change seen by this pipeline since the last reseed', not 'never edited'. Synthesized field, populated (true/false) for all sources."*
- **Current:** `null` (undocumented; `boolean` `audit_schema.txt:220`).
- **Discrepancy (LOW):** undocumented; risks over-trust as authoritative recall-revision state. Confidence **HIGH on mechanism**; first-pass `confirmed` false for overclaimed per-source true population (now downgraded to structural non-null).
- **UNVERIFIED:** corpus true/false ratio per source; whether post-reseed sparse history yields almost all false.

---

### 3.60 `edit_count` → `mart_recall_summary.edit_count`

- **Lineage:** `_api_synthesized`. Silver `recall_lifecycle`: `count(distinct content_hash)` per recall identity in each per-source CTE (`recall_lifecycle.sql:41,52,65,77,89`), UNION ALL into `bronze_stats`, projected `bs.edit_count` (`:211`). Gold pass-through via LEFT JOIN `recall_lifecycle` (`mart_recall_summary.sql:122,145`). **Distinct lineage from `edit_event_count`/`has_been_edited`** (those come from `recall_event_history`). ADR 0026 line 164 `edit_count = COUNT(DISTINCT content_hash)` matches as-built exactly. Explicitly NOT derived from `last_modified_date`.
- **True meaning:** number of distinct bronze content-hash versions the pipeline banked. 1 = seen but never observed to change; >1 = N distinct versions. A proxy for edit activity, **reseed-bounded** (since 6a.5). For multi-row sources (FDA per-PRODUCTID, NHTSA per-component) it aggregates version diversity across the event's child rows. Minimum 1 wherever a bronze row exists (not 0-based).
- **populated_by:** all five ✓ — structurally sound via the bronze UNION + left join (no `edit_count` pop column in coverage). A unit test pins `edit_count=2` for a 2-content-version USDA recall (`recall_lifecycle_unit_tests.yml:51`).
- **PROPOSED:** *"Count of distinct bronze content-hash versions of the recall observed by this pipeline (count(distinct content_hash) per recall identity). 1 = seen but never observed to change. A proxy for edit activity, not an authoritative agency edit count: counts only changes seen since the 6a.5 bronze reseed, and for multi-row sources (FDA per-product, NHTSA per-component) it aggregates version diversity across the event's child rows. Populated for all sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null` (undocumented; `bigint` `audit_schema.txt:216`).
- **Discrepancy (LOW):** undocumented; the name overstates precision and is confusable with `edit_event_count`. Confidence **HIGH**.
- **UNVERIFIED:** empirical per-source distribution of `edit_count` (how many recalls have >1); per-source null rate (inferred from UNION ALL + left join, not measured).

---

### 3.61 `first_seen_at` → `mart_recall_summary.first_seen_at`

- **Lineage:** `_api_synthesized`. Silver `recall_lifecycle`: `min(extraction_timestamp)` per source/identity in each CTE (`recall_lifecycle.sql:39,50,63,75,86`), UNION ALL `bronze_stats`, left-joined onto recall_event by (source, source_recall_id), projected `bs.first_seen_at` (`:209`). Gold pass-through (`mart_recall_summary.sql:120,145`). **As-built uses `MIN(bronze.extraction_timestamp)`, NOT `MIN(extraction_runs.started_at)` that ADR 0026 line 162 specifies** — equivalent intent, manifest-independent, available for all five sources.
- **True meaning:** earliest extraction_timestamp at which **OUR pipeline** banked a bronze row — when this pipeline first observed the record, **NOT** the agency announcement date. **Bounded by the 6a.5 bronze reseed** (history wiped), so it reads "first seen since the reseed", not the recall's true age. For recall age use `announced_at`.
- **populated_by:** all five ✓ structurally (bronze UNION covers all 5). **Per-source population NOT empirically measured** — no `first_seen_at` coverage column; the all-five claim is inference from the UNION ALL + left join. `timestamptz`, nullable (`audit_schema.txt:214`).
- **PROPOSED:** *"Earliest extraction timestamp at which this pipeline banked a bronze row for the recall (pipeline-observed first-seen time, derived from bronze extraction_timestamp). NOT the agency announcement date — for recall age use announced_at. Bounded by the 6a.5 bronze reseed (bronze history was wiped), so it reflects 'first seen since the reseed', not the recall's true age. Populated for all sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null` (undocumented).
- **Discrepancy (LOW):** undocumented; the name risks implying recall age/announcement time. Confidence **HIGH on lineage/transform** (the as-built-vs-ADR divergence is confirmed); the per-source non-null claim is inference-only.
- **UNVERIFIED:** per-source population/null rates (no coverage figure); exact 6a.5 reseed date (only referenced in model header).

---

### 3.62 `last_seen_at` → `mart_recall_summary.last_seen_at`

- **Lineage:** `max(extraction_timestamp)` per identity in each CTE (`recall_lifecycle.sql:40,51,64,76,87`), UNION ALL, projected `bs.last_seen_at` (`:210`). Gold pass-through (`mart_recall_summary.sql:121,145`). As-built `MAX(bronze.extraction_timestamp)` vs ADR 0026 line 163 `MAX(extraction_runs.started_at)`.
- **True meaning:** latest extraction_timestamp at which the pipeline **inserted a new bronze content version**. Because bronze is content-hash-keyed insert-only (ADR 0007 — no row when content is unchanged), this is the **last OBSERVED-CHANGE time, not the last time the record was seen present** in the feed. For "currently published upstream" use `is_currently_active`. Reseed-bounded.
- **populated_by:** all five ✓ structurally (no `last_seen_at` pop column; `timestamptz` nullable `audit_schema.txt:215`).
- **PROPOSED:** *"Latest extraction timestamp at which this pipeline inserted a new bronze content version for the recall (derived from bronze extraction_timestamp). Because bronze dedups unchanged content, this is the last OBSERVED-CHANGE time, not the last time the record was seen in the feed — for 'currently published upstream' use is_currently_active. Bounded by the 6a.5 bronze reseed. Populated for all sources: CPSC, FDA, USDA, NHTSA, USCG."*
- **Current:** `null` (undocumented).
- **Discrepancy (LOW):** undocumented; the name invites "last time seen in the feed" but the as-built semantics are "last observed content change". Confidence **HIGH on lineage**; per-source population inference-only.
- **UNVERIFIED:** per-source population/null rates; whether any recall_event row can have a null `last_seen_at`.

---

### 3.63 `is_currently_active` → `mart_recall_summary.is_currently_active`

- **Lineage:** presence-manifest-derived flag (requires `extraction_run_identities`). **USDA** branch (`recall_lifecycle.sql:103-149`): `bool_or(run_id = latest enumerating run)` per `trim(source_recall_id)`, `langcode='English'`. **NHTSA** branch (`:163-202`): identical shape on `campno`, manifest written ONLY by `NhtsaDeepRescanLoader` (full-corpus). `coalesce(ul.is_currently_active, nl.is_currently_active)`, source-gated join (`:212,218-223`). Gold pass-through (`mart_recall_summary.sql:123,145`). Computed against the latest **ENUMERATING** run (not merely successful) so a 304-no-op run doesn't read as "all retracted" (ADR 0026 lines 399-405). **Track-presence sources = {USDA, NHTSA} only** (ADR 0026 lines 12,239); CPSC/FDA/USCG write no manifest → NULL.
- **True meaning:** whether the recall's identity was present in the most recent enumerating run (true = still listed) or absent (false). It is **OBSERVED feed presence**, NOT an authoritative agency active/withdrawn status. **NOT to be conflated with `is_active`** (§3.13, lifecycle_status-derived). USDA presence is English-only.
- **populated_by:** CPSC – FDA – **USDA ✓ NHTSA ✓** USCG – — empirically backed: `was_ever_retracted_pop` (same presence-CTE pair) = USDA 1217, NHTSA 30075, CPSC/FDA/USCG 0 (`audit_coverage.txt:10-14`). **NHTSA is now populated** (deep-rescan manifest has been banked; ADR 0026 line 227 "Verified PASS 2026-06-13") — the historical "NULL until first deep-rescan" caveat is design behavior, not current state.
- **PROPOSED:** *"Whether the recall was present in the most recent enumerating extraction run (true = still listed in the source feed, false = absent). This is OBSERVED feed presence from the pipeline's presence manifest, not an authoritative agency active/withdrawn status. Sources: USDA, NHTSA (null for CPSC/FDA/USCG, which do not track presence)."*
- **Current:** `null` (undocumented).
- **Discrepancy (MEDIUM):** undocumented despite being NULL for 3 of 5 sources; the name `is_currently_active` strongly implies an authoritative per-recall status applicable to all recalls — a likely consumer trap, and easily conflated with `is_active`. Confidence **HIGH**; first-pass `confirmed` was false only because it **under-claimed NHTSA** (marked it unverified when coverage confirms it populated).
- **UNVERIFIED (residual):** empirical true/false distribution for USDA/NHTSA (coverage gives population, not the active/inactive split); no direct `is_currently_active` pop column (NHTSA=true transitively inferred via the shared presence CTE with `was_ever_retracted`).

---

### 3.64 `was_ever_retracted` → `mart_recall_summary.was_ever_retracted`

- **Lineage:** presence-manifest-derived. USDA (`recall_lifecycle.sql:139-149`): `was_ever_retracted = present_runs < (count of enumerating runs since this identity's first_present)` — i.e. the identity appeared in FEWER enumerating runs than existed since it first appeared (a mid-lifespan toggle OR an end retraction). NHTSA identical on campno (`:195-202`). `coalesce`, source-gated join (`:213,218-223`). Gold pass-through (`mart_recall_summary.sql:124,145`). Unit-test-verified (`recall_lifecycle_unit_tests.yml:20-51`: R1 present run1+run3, absent run2 → true). **{USDA, NHTSA} only.**
- **True meaning:** whether the recall was ever absent from an enumerating run between its first and latest appearance. An **OBSERVED feed-presence gap**, NOT an authoritative agency retraction; only detects absences across runs tracked since manifest start / the 6a.5 reseed. NULL for CPSC/FDA/USCG.
- **populated_by:** CPSC – FDA – **USDA ✓ NHTSA ✓** USCG – — **the one lifecycle field with a direct per-source coverage number**: `was_ever_retracted_pop` USDA 1217, NHTSA 30075, CPSC/FDA/USCG 0 (`audit_coverage.txt:10-14`). This is the highest-confidence presence field. NHTSA is fully populated (30075/30075) at the audit snapshot.
- **PROPOSED:** *"Whether the recall was ever absent from an enumerating extraction run between its first and latest appearance (true = a presence gap was observed, indicating a retract/republish toggle or a terminal disappearance). OBSERVED feed-presence gap from the pipeline's presence manifest, not an authoritative agency retraction record; accrues only over runs tracked since manifest start. Sources: USDA, NHTSA (null for CPSC/FDA/USCG, which do not track presence)."*
- **Current:** `null` (undocumented).
- **Discrepancy (MEDIUM):** undocumented despite NULL for 3 of 5 sources; the name `was_ever_retracted` overstates the semantics (it is an observed feed-presence gap, can be a transient toggle); a uniform `false`/NULL could be misread as "never retracted" vs "not tracked". Confidence **HIGH**; first-pass `confirmed` false only because it marked NHTSA/USDA population unverified when coverage now confirms full population.
- **UNVERIFIED (residual):** live true/false **distribution** (the unit-test comment notes live USDA positives are currently scarce; that is a design-time note, not measured gold data — population is full, the true/false split is unmeasured).

---

### 3.65 `distribution_state_codes` → `mart_recall_summary.distribution_state_codes`

- **Raw sources:** FDA distributionareasummarytxt (free-text distribution pattern), USDA field_states (comma list).
- **Lineage:** staging `stg_fda_recalls.sql:43` `nullif(distribution_area_summary_txt,'')`; `stg_usda_fsis_recalls.sql:73` `nullif(jsonb_array_to_csv('states'),'')`. Silver `recall_event`: FDA → `distribution_area_summary` (`:133`), USDA → `distribution_states` (`:226`); CPSC/NHTSA/USCG hardcode both to NULL (`:47,55,292,303,369,380`). Silver `recall_distribution_area` parses STATE codes: FDA cuts at the first international marker and parses only the DOMESTIC HEAD (state names + standalone uppercase USPS code tokens; West Virginia stripped before bare 'Virginia'; Georgia-the-country guard); USDA maps comma tokens to USPS codes; UNION → `array_agg(distinct abbr)` (`:58-172,236-243`), `'{}'` for country-only rows (`:256`). Gold pass-through via LEFT JOIN (`mart_recall_summary.sql:104,148`), GIN-indexed (`:8`).
- **True meaning:** array of 2-letter USPS state/territory codes for the US states the product was distributed to (initial distribution area). **FDA + USDA only.** NULL (no rda row) when nothing parsed; empty `'{}'` when only foreign countries parsed (country-only recall); populated otherwise. The FDA side is a **precision-first regex parse** — high-precision, not exhaustive (absence of a code is NOT proof of non-distribution).
- **populated_by:** CPSC – **FDA ✓ USDA ✓** NHTSA – USCG – — `dist_state_codes_nonempty` FDA=36344, USDA=793, CPSC/NHTSA/USCG=0 (`audit_coverage.txt:10-14`); gold-grain `non_null=40064 / empty=2927`, avg_card 5.77 (`:82`).
- **PROPOSED:** *"USPS 2-letter state/territory codes for the US states where the recalled product was distributed (initial distribution area). Derived in silver recall_distribution_area: FDA from a precision-first parse of the free-text distribution pattern (domestic-head state names + standalone uppercase USPS code tokens); USDA from the field_states comma list mapped to USPS codes. Null when no geography parsed; an empty array indicates a foreign-country-only recall. Sources: FDA, USDA (null for CPSC/NHTSA/USCG, which have no distribution field)."*
- **Current:** `"Parsed USPS codes."`
- **Discrepancy:** this is one of the **5 known carry-forward findings** — and it is the **highest-severity (MEDIUM)** of them. The current "Parsed USPS codes." is technically correct but materially incomplete: omits (1) source provenance (FDA+USDA only; null for CPSC/NHTSA/USCG), (2) that it is distribution/where-sold geography not firm geography, (3) NULL-vs-empty-array semantics, (4) the precision-over-recall caveat. Confidence **HIGH**.
- **UNVERIFIED:** whether the FDA parse misses real state mentions (recall side of the tradeoff) not quantified; `us_state_abbr` seed contents (confirmed to contain GEORGIA,GA so the country guard is needed, but not exhaustively audited).

---

### 3.66 `distribution_country_codes` → `mart_recall_summary.distribution_country_codes`

- **Raw sources:** FDA distributionareasummarytxt (international TAIL); USDA field_states (states-only today → dormant path).
- **Lineage:** same upstream as §3.65. Silver `recall_distribution_area` country block (C12): FDA keeps only marker-bearing recalls, trims to the international TAIL (strips 'new mexico' so bare 'Mexico' doesn't fire), matches the `country_iso` seed names → alpha2; USDA exact comma-token match (yields nothing today). UNION → `array_agg(distinct alpha2)` (`:174-233,245-251`); `'{}'` for state-only rows (`:258`); FULL OUTER JOIN of state/country aggs guarantees a row when either parsed (`:254-261`). **`country_iso` seed deliberately EXCLUDES the United States** (foreign-only by design) and **excludes 'Georgia'** (US-state collision). Foreign 2-letter codes NOT matched (curated NAMES only). Gold pass-through via LEFT JOIN (`mart_recall_summary.sql:105,148`), GIN-indexed (`:9`).
- **True meaning:** array of ISO-3166-1 alpha-2 codes for the FOREIGN countries the product was distributed to. **Foreign-only by design** (US excluded — domestic geography is `distribution_state_codes`). **FDA-only in practice** — the USDA path exists for symmetry but `field_states` is states-only. NULL when nothing parsed; empty `'{}'` for a domestic-only recall. Precision-first names-only parse.
- **populated_by:** CPSC – **FDA ✓** USDA – NHTSA – USCG – — `dist_country_codes_nonempty` FDA=7237, USDA=0, all others 0 (`audit_coverage.txt:10-14`). Foreign-only confirmed empirically by `rows_with_us_country = 0` (`:95-98`) and the seed lacking US/Georgia rows; gold-grain `non_null=40064 / empty=32827` (domestic-only), avg_card 3.12 (`:87`).
- **PROPOSED:** *"ISO-3166-1 alpha-2 codes for the FOREIGN countries the recalled product was distributed to (foreign-only by design: the United States is excluded — domestic distribution is in distribution_state_codes). Parsed in silver recall_distribution_area from the international tail of the FDA free-text distribution pattern, matching curated country names only (foreign 2-letter codes are intentionally not matched). Null when no geography parsed; an empty array indicates a domestic-only recall. Sources: FDA (null for CPSC/USDA/NHTSA/USCG — the USDA path exists but field_states is states-only today)."*
- **Current:** `"ISO alpha-2, foreign-only (US excluded by design)."`
- **Discrepancy:** this is one of the **5 known carry-forward findings**. Current is correct on the two load-bearing facts (alpha-2 + foreign-only/US-excluded) but incomplete — omits source provenance (FDA-only in practice; USDA dormant; null for CPSC/NHTSA/USCG), the precision-first names-only caveat, the Georgia-country exclusion, and NULL-vs-empty-array semantics. Severity **LOW**. Confidence **HIGH**.
- **UNVERIFIED:** whether any USDA `field_states` value has EVER emitted a country code (header asserts "yields nothing today", not re-verified); full `country_iso` seed contents beyond the 155-row / no-US / no-Georgia confirmation.

---

### 3.67 `firm_usda_attributes` → `mart_firm_profile.firm_usda_attributes`

- **Lineage:** sole source **USDA FSIS Establishment Listing API (MPI Directory)** — NOT the recall feed. Staging `stg_usda_fsis_establishments` (latest-per-establishment by `row_number() partition by source_recall_id order by extraction_timestamp desc`; value normalizations incl. `nullif(establishment_number,'')` `:33`, `nullif(county|geolocation,'false')`, activities trim+re-agg, dbas placeholder strip). Silver SCD-2 `firm_usda_attributes_snapshot` (strategy='check', unique_key='establishment_number'; check_cols EXCLUDE `latest_mpi_active_date` heartbeat; `where establishment_number is not null`). Silver current view `firm_usda_attributes` (where dbt_valid_to is null; **the one rename `establishment_number → establishment_id`**; 17 output columns). Bridge: `firm.usda_normalized` captures `e.establishment_number as company_id` via LEFT JOIN `upper(trim(r.establishment))=upper(trim(e.establishment_name))` (`firm.sql:85-96`) into `observed_company_ids`. Gold: unnest `observed_company_ids`, LEFT JOIN `firm_usda_attributes ea on ea.establishment_id = fi.company_id`, `jsonb_agg(to_jsonb(ea) order by establishment_id) FILTER (where establishment_id is not null)` (`mart_firm_profile.sql:42,50`), final select `:126`. Disjoint id namespaces (FDA FEI / USDA `'M1234'` / USCG MIC) route each id to exactly one sidecar.
- **True meaning:** jsonb array of per-establishment FSIS regulatory/demographic blocks for the USDA-FSIS-regulated establishments the firm is registered as. Each element = one FSIS establishment record (current SCD-2 view) keyed on `establishment_id` (= grant-prefixed M/P/I/G/V number), carrying name, full mailing address, regulatory metadata (status_regulated_est, size, district, circuit, activities, dbas), grant/inspection dates. An ARRAY because a canonical firm can map to >1 establishment. NULL for any firm with no matched FSIS establishment id.
- **populated_by:** **USDA only** (CPSC/FDA/NHTSA/USCG –) — `has_usda_block=529` of 24331 firms; dim `firm_usda_attributes`=8003 rows, establishment_id 100% populated (`audit_coverage.txt:249-251,980-982`; `audit_schema.txt:28,271`).
- **PROPOSED:** *"USDA FSIS establishment attributes for this firm, as a JSON array of per-establishment blocks (one per matched FSIS establishment_number). Each block carries the FSIS Establishment Listing / MPI Directory record: establishment_id (grant-prefixed FSIS number, e.g. 'M1234'), establishment_name, mailing address (address, city, state, zip, county, fips_code, geolocation), regulatory metadata (status_regulated_est, size, district, circuit, activities, dbas), and grant_date / latest_mpi_active_date. Reflects the current SCD-2 view (latest known values). NULL when the firm matches no FSIS establishment record. Sources: USDA only (null for CPSC/FDA/NHTSA/USCG)."*
- **Current:** `null` (and no `_gold.yml` column entry).
- **Discrepancy (LOW):** an ADR-0042-contracted serving column ships with zero schema-level documentation on either side. Confidence **HIGH**. First-pass corrections: 17 columns via `to_jsonb` (not 16); 8003 rows (not the stale ~7945/7979); coverage gaps now pinned (county 98.5%, fips 95.8%, geolocation 98.8%, size 97.3%, etc.).
- **UNVERIFIED:** NULL-vs-`[]`-vs-absent for a no-USDA firm (reasoned from SQL, not query-confirmed); whether any firm's `observed_company_ids` holds >1 USDA establishment_number (array length >1 in gold — structurally possible, not data-confirmed); size-class distribution percentages (not in coverage table); exact FSIS source-field wording (street vs address; separate lat/long vs collapsed geolocation — from supplied dict, PDF not re-opened).

---

### 3.68 `firm_uscg_attributes` → `mart_firm_profile.firm_uscg_attributes`

- **Lineage:** sole source **USCG HTML-scraped manufacturer directory** (uscgboating.org — no official API/PDF). Staging `stg_uscg_manufacturer_details` (latest-per-MIC; `source_recall_id AS mic` `:39`; sentinel 'UNK'/'-'/''→NULL; `nullif(state,'')`). Silver SCD-2 `firm_uscg_attributes_snapshot` (strategy='check', unique_key='mic'=`upper(trim(mic))`; check_cols include `out_of_business`, EXCLUDE `date_modified`+`in_business` heartbeats; `where company_name is not null`). Silver current view `firm_uscg_attributes` (where dbt_valid_to is null; derived MIC-recycle flags `mic_has_prior_holder`/`mic_oob_recycled`/`mic_renamed_not_recycled` + `prior_holders` jsonb). Bridge: `firm.uscg_normalized` `company_id = r.mic` (`firm.sql:160`) into `observed_company_ids`. Gold: LEFT JOIN `firm_uscg_attributes ma on ma.mic = fi.company_id`, `jsonb_agg(to_jsonb(ma) order by mic) filter (where mic is not null)` (`mart_firm_profile.sql:43,51`), select `:127`.
- **True meaning:** jsonb ARRAY of USCG boat-manufacturer directory blocks, one element per distinct MIC the canonical firm is observed under. Each block carries directory-canonical company name, dba, parent_company/parent_mic, past_company_1/2/3 (succession lineage), full mailing address, status, in/out-of-business + modified dates, uscg_directory_id, detail_url, and the derived MIC-recycle flags. SCD-2 because **USCG recycles a finite 3-char MIC to a new builder** when the prior holder goes out of business (so pre-reassignment recalls must not be misattributed). NULL for any firm with no USCG MIC.
- **populated_by:** **USCG only** (CPSC/FDA/USDA/NHTSA –) — `has_uscg_block=678` of 24331 firms; dim 16260 rows = 16260 distinct MICs (`audit_coverage.txt:249-250,1303-1306`; `audit_schema.txt:27`). MIC-recycle flag prevalence: `has_prior_holder=4574`, `oob_recycled=3024` (strict subset), `renamed_not_recycled=2` of 16260 (`:1311-1313`). 113 firms carry exactly 2 sidecar blocks (cross-source clustering observed, `:253-256`).
- **PROPOSED:** *"USCG boat-manufacturer directory attributes for this firm, as a JSONB array of one block per USCG Manufacturer Identification Code (MIC) the firm is registered under (one canonical firm can span several MICs). Each block carries the directory-canonical company name, DBA, parent company/MIC, prior MIC holders (succession lineage), full mailing address, operating status, in/out-of-business and modified dates, plus derived MIC-recycle flags (a finite 3-char MIC is reused for a new builder when the prior one goes out of business, so pre-reassignment recalls must not be misattributed). Built from USCG HTML-scraped directory data (no official USCG API), conformed to the current view of an SCD-2 snapshot. Sources: USCG only (null for CPSC/FDA/USDA/NHTSA firms — those have no USCG MIC)."*
- **Current:** `null` (no `_gold.yml` column description). **Important API-layer correction:** at the published API the field is **never null** — Pydantic coerces NULL→`[]` (`models/firms.py:110` `firm_uscg_attributes: list[UscgManufacturer] = Field(default_factory=list)`, `_none_to_list` validator `:113-125`). The dbt gold output is nullable; the API normalizes it. A `UscgManufacturer` Pydantic model with a docstring exists (`firms.py:41-68`) — the nested block shape is partially documented; only the top-level field prose description is missing.
- **Discrepancy (LOW):** no top-level Pydantic `Field(description=)` and no `_gold.yml` column doc, on an ADR-0042-frozen contract column. Confidence **HIGH**.
- **CAVEATS to preserve:** `in_business` is CONTAMINATED by record-touch dates (never read as a founded date); top-level `out_of_business` (current holder defunct = SCD valid_to) ≠ a Past Company '(OOB)' marker (prior holder ceased → MIC recycled); block reflects the CURRENT MIC holder, so recall_event_firm's `uscg_mic_time_sensitive_unresolved` flags pre-reassignment attribution risk separately.
- **UNVERIFIED:** that the three id namespaces never collide in live data (asserted in model header, not empirically re-verified); full domain of directory `status`/sentinel enum meanings (documented as pending USCG OII asks; passed through verbatim).

---

### 3.69 `firm_fda_attributes` → `mart_firm_profile.firm_fda_attributes`

- **Lineage:** sole source **FDA iRES Enforcement Reports** feed. Staging `stg_fda_recalls` (latest-per-product by `row_number() partition by source_recall_id order by extraction_timestamp desc`; 11 firm fields with `nullif(col,'')`; camelCase→snake_case renames; address/continuity fields from migration 0019). Silver SCD-2 `firm_fda_attributes_snapshot` (strategy='check', check_cols = 10 non-key attribute cols; `DISTINCT ON (firm_fei_num) ... ORDER BY firm_fei_num, event_lmd desc nulls last, extraction_timestamp desc` — latest-per-FEI Type-1 collapse; `where firm_fei_num is not null`). Silver current view `firm_fda_attributes` (where dbt_valid_to is null; `firm_country_nam = coalesce(c.firm_country_nam, ov.country)` data-quality override, e.g. FEI 3012569470 Visaris→'Serbia'). Bridge: `firm.fda_normalized` `company_id = firm_fei_num::text` (`firm.sql:79`). Gold: LEFT JOIN `firm_fda_attributes fa on fa.firm_fei_num::text = fi.company_id`, `jsonb_agg(to_jsonb(fa) order by firm_fei_num) FILTER (where firm_fei_num is not null)` (`mart_firm_profile.sql:44,52`), select `:128`.
- **True meaning:** jsonb array of FDA-registered recalling-firm (establishment) attribute blocks, one element per distinct FEI the firm clusters under. Each block: `firm_fei_num` (FDA Establishment Identifier, the join key) + the 'Original Recalling Firm' identity/address-at-time-of-recall (legal name, address lines 1-2, city, 2-letter state code, full state/province, postal code, country) + FDA's firm-succession signal `firm_surviving_nam`/`firm_surviving_fei` (current name/FEI if renamed post-recall). Latest-per-FEI Type-1 (15.3% of FEIs carry >1 address; only the most recent is shown). Empty array for any firm without an FDA identity.
- **populated_by:** **FDA only** (CPSC/USDA/NHTSA/USCG –) — `has_fda_block=12010` (vs USDA 529, USCG 678, `audit_coverage.txt:251`); dim 13418 rows (`audit_schema.txt:26`). Only FDA writes an FEI to `observed_company_ids` (NHTSA `cast(null)`, USDA writes establishment_number, USCG writes MIC — disjoint namespaces).
- **PROPOSED:** *"Per-source FDA sidecar: a jsonb array of FDA-registered recalling-firm (establishment) attribute blocks for this canonical firm, one element per FDA FEI it clusters under. Each block carries firm_fei_num (FDA Establishment Identifier — the join key), the 'Original Recalling Firm' identity and address at time of recall (firm_legal_nam, firm_line1_adr, firm_line2_adr, firm_city_nam, firm_state_cd, firm_state_prvnc_nam, firm_postal_cd, firm_country_nam), and FDA's firm-succession signal firm_surviving_nam/firm_surviving_fei (current name/FEI if the firm was renamed post-recall, ~12% populated). Values are latest-per-FEI from the FDA SCD-2 snapshot current view; firm_country_nam may be a data-quality override for known foreign firms. Empty list for firms with no FDA identity. Sources: FDA only (empty [] for CPSC/USDA/NHTSA/USCG-only firms)."*
- **Current:** `null` (Pydantic `list[FdaAttributes] = Field(default_factory=list)`, `models/firms.py:111`, no `description=`; no `_gold.yml` column doc). Like the USCG sidecar, the API coerces NULL→`[]`.
- **Discrepancy (LOW):** missing Pydantic/gold-yml description on an ADR-0042-contracted column. Confidence **HIGH**. First-pass corrections (from full-corpus coverage): **`firm_line2_adr` is ~7.5% populated, NOT ~0%/100%-NULL** (1003 of 13418); `firm_surviving_nam`/`firm_surviving_fei` ~12.3% (1647, exactly paired), not ~15%; **13418 rows** (the 14285/53-excluded figures are a 2026-06-03 profiling snapshot, not current cardinality); `firm_state_cd` is 85.0% populated and `firm_postal_cd` 92.7% — sizeable gaps (~2008 null state_cd far exceed the ~985 non-US firms), not just "the few international firms".
- **UNVERIFIED:** the CPSC "100% empty CompanyIDs" claim could not be checked (no firm-dimension company_id coverage; raw CPSC dict not read) — but the FDA-only conclusion does not depend on it; `firm_state_cd` 2-letter-code semantics inferred (not in FDA Definitions PDF; the valid 2-letter US/territory distribution supports but does not formally document it); per-corpus exact population rates from field-audit probe windows (100/447-record), not full-corpus; count of multi-FDA-FEI clusters (array length >1) not isolated (max sidecar blocks per firm is 2, but that does not distinguish intra-FDA multiplicity).

---

## 4. Discrepancies & Systemic Findings (ranked by severity)

### The 5 known carry-forward findings (status after empirical verification)

| # | Field | Status | Severity | Note |
|---|---|---|---|---|
| 1 | `announced_at` | Confirmed | (doc gap) | Nullable by design (~20 FDA events null via ≥1940 guard; USCG epoch rows dropped). Substance correct; needs Pydantic description. |
| 2 | `risk_level` | Confirmed | (doc gap) | USDA-only, **derived 1:1 from classification (not lifted)**. Coverage proves the deterministic mapping. Needs description. |
| 3 | `reason_category` | Confirmed (refined) | (doc gap) | USDA-only FSIS taxonomy CSV; **multi-valued (~26 distinct combined values), not a closed 9-value set**. Needs description. |
| 4 | `distribution_country_codes` | Confirmed | LOW | Current "ISO alpha-2, foreign-only" is right on the load-bearing facts but omits FDA-only-in-practice / precision parse / NULL-vs-empty semantics. |
| 5 | `product model` (`RecallDetail.models` / `ProductSearchHit.model`) | **Corrected** | (data-shape) | First pass wrong: CPSC is non-NULL **empty-string** `""`, not NULL/100%-empty; the not-null gold filter does NOT drop empties, so the `models` array can contain literal `""` for CPSC; the btree on `model` indexes those empties. Effectively NHTSA-only for real values. |

### New / additional systemic findings (ranked)

**MEDIUM severity**

1. **`distribution_state_codes` documentation gap** (§3.65). Current "Parsed USPS codes." is the single largest description deficit by impact: omits FDA+USDA-only provenance, distribution-vs-firm geography, NULL-vs-empty-array semantics, and the precision-over-recall caveat. Promote to the proposed string.
2. **`is_currently_active` / `was_ever_retracted` naming + scope trap** (§3.63, §3.64). Both are presence-manifest flags populated for **{USDA, NHTSA} only**, NULL for CPSC/FDA/USCG, and represent OBSERVED feed presence — NOT authoritative agency status. The names strongly imply universal authoritative status. `is_currently_active` is additionally easily conflated with the separate `is_active` lifecycle flag. Both undocumented. (NHTSA is now fully populated — the "NULL until deep-rescan" caveat is historical, not current.)

**LOW severity (each: undocumented and/or under-specified; no factual contradiction)**

3. **Pervasive missing Pydantic descriptions.** The overwhelming majority of fields have `current_description = null`. Every `mart_firm_profile` field, every lifecycle/history/presence field, every product-search context field, and both recall_event_id projections ship undocumented. The apply step should add the proposed strings.
4. **`RecallDetail.is_active` vs `RecallSummary.is_active` inconsistency** (§3.13). The same column has a (terse) description on RecallSummary but none on RecallDetail. Make them identical.
5. **Synthesized-field naming over-precision** (`edit_count`, `edit_event_count`, `has_been_edited`, `first_seen_at`, `last_seen_at`, §3.58-3.62). Names imply authoritative agency edit/age semantics; reality is pipeline-observability proxies, reseed-bounded, with two confusable edit signals (`edit_count` from `recall_lifecycle` vs `edit_event_count`/`has_been_edited` from `recall_event_history`) on the same mart and no Pydantic disambiguation.
6. **Empty-string vs NULL across CPSC product fields** (`model`, `product_description`, `type`, §3.27/3.34/3.35/3.36). CPSC contributes non-NULL **empty strings** for `model`, `product_description`, and (partly) `type`. Coverage `*_pop` counts these as "populated" (100% non-null), but they carry no information and survive not-null filters. Any "populated_by" derived from naive coverage `count()` over-counts CPSC for these fields — the matrix marks them `Y (""")`.
7. **Thin gold-yml descriptions** (`firms`, `recalls_by_source`, §3.24/3.56). Existing `_gold.yml` text is accurate but omits load-bearing details (per-role grain / never-null invariant for `firms`; sparse-object / sum-to-total for `recalls_by_source`).
8. **Under-specified honesty flags** (`rank`, `upc_is_recall_level`, `upc`, `hazards`, `distribution_states`, `hins`, `recall_product_upcs`, §3.2/3.3/3.39/3.20/3.19/3.28/3.44). Current descriptions exist but understate provenance/constancy/caveats; `recall_product_upcs`'s "flattened" wording is actively misleading (gold passes it verbatim; flattening is API-side).

### Systemic cross-cutting truths (apply once, everywhere)

- **Event grain vs product grain:** `recall_event_id` is event-grain; for FDA the event id is hashed from RECALLEVENTID while `source_recall_id` on the product mart is `productid` (product-grain). USDA/USCG are 1 product per recall by construction.
- **Conformed-but-not-normalized enums:** `classification`, `lifecycle_status`, and `type` keep each source's native vocabulary side-by-side (FDA classification is `1/2/3/NC`, not Roman). `is_active` and `distribution_scope` *are* conformed; `risk_level`/`reason_category`/`distribution_states` are USDA-only.
- **Tri-state asymmetry:** `is_active` (and downstream `active_recalls`) is NULL for CPSC+NHTSA exactly — those sources can never be "active". `null=39928 == CPSC 9853 + NHTSA 30075`.
- **Disjoint firm-id namespaces** drive the three firm sidecars; each `observed_company_ids` entry routes to exactly one of FDA/USDA/USCG.
- **Pipeline-observability bounding:** every `recall_lifecycle`/`recall_event_history`/presence-manifest field is bounded by bronze snapshot retention and the Phase 6a.5 reseed, and (for presence) by the {USDA,NHTSA} track-presence set.

---

## 5. Confidence / Needs-Human-Check

### Low-confidence fields (verification did not fully clear)

1. **`alternate_names`** (§3.50) — **✅ RESOLVED 2026-06-17 → HIGH (see §6.2).** ~~LOW confidence ("no verifier output").~~ Re-verified line-by-line: `firm_crosswalk.alternate_names` → `alias_flat` CTE → gold passthrough (`firm.sql:193,204-211,220,222`; `mart_firm_profile.sql:118`); populated `has_alternate_names=1213/24331` (~5%, `audit_coverage.txt:251`); meaning per `_silver.yml:151-156`. *Remaining residual (narrow):* the upstream Python alias-extraction rules (`extract_paren_aliases` / DBA detection in `recalls resolve-firms`) live outside dbt and were not read — only the SQL-side consumption is dbt-verifiable.

2. **`distinct_products`** (§3.57) — **✅ RESOLVED 2026-06-17 → HIGH (see §6.3).** ~~MEDIUM confidence.~~ CTEs re-read line-by-line: `event_products` (`count(distinct recall_product_id)` per event, `:99-103`) → `firm_product_counts` (`sum(n_products)` over the firm's distinct events, `:105-110`) → `coalesce(...,0)` (`:125`). Per-firm footprint (not global-distinct) confirmed at the SQL level and corroborated by coverage (Mercedes 48006/517 events). No residual.

### Fields whose `populated_by` is structural-only (NOT empirically per-source measured)

These carry an all-source `populated_by` that is **inferred from SQL structure (UNION ALL / left join / not-null coalesce), not backed by a per-source coverage number** — the synthesized/pipeline fields. Treat their per-source population as *structurally guaranteed non-null*, not as *empirically confirmed edit/observation activity*:

- `edit_event_count`, `has_been_edited` (§3.58, §3.59) — only corpus-wide `t=45 / f=93333`; **no per-source split**. Which sources own the 45 edited recalls is unknown.
- `edit_count` (§3.60), `first_seen_at` (§3.61), `last_seen_at` (§3.62) — no per-column coverage figure; all-five claim is UNION-ALL + left-join inference (a unit test pins `edit_count=2` for one USDA recall, but no corpus distribution).
- `url` (CPSC/USDA/USCG true, §3.7/3.42) — no direct url coverage column; the *true* values rest on SQL construction (FDA/NHTSA *false* is hard-forced by explicit null casts).

### Fields with a residual UNVERIFIED aspect (otherwise HIGH confidence)

- **ADR documents (all fields)** — ~~no ADR text exists on disk; every ADR attribution rests on model-header comments.~~ **✅ RESOLVED 2026-06-17 → HIGH (see §6.1).** The ADRs DO exist (`documentation/decisions/`, 43 pipeline + 15 API); a follow-up read `0035`/`0036`/`0038`/`0042` in full and **confirmed every cited attribution — 0 corrections**. *Remaining residual (non-load-bearing):* secondary citations (`0002`/`0007`/`0022`/`0026`/`0027`/`0031`/`0033`/`0034`) were corroborated indirectly but not each opened.
- **`is_currently_active` NHTSA** (§3.63) — populated, but NHTSA=true is *transitively* inferred from the shared presence CTE with `was_ever_retracted_pop` (no direct `is_currently_active` pop column). The true/false **distribution** for USDA and NHTSA is unmeasured.
- **`was_ever_retracted` distribution** (§3.64) — population is fully confirmed (the only presence field with a direct per-source coverage number), but the true/false split is unmeasured.
- **`firm_usda_attributes`** (§3.67) — array length >1 (multi-establishment firms) structurally possible but not data-confirmed; size-class distribution not in coverage; FSIS source-field exact wording from the supplied dict, PDF not re-opened.
- **`firm_fda_attributes`** (§3.69) — CPSC "100% empty CompanyIDs" claim unchecked (raw CPSC dict not read; FDA-only conclusion is independent of it); `firm_state_cd` 2-letter semantics inferred (not in FDA PDF); multi-FDA-FEI cluster count not isolated.
- **Raw-dictionary-sourced sub-field claims** — e.g. CPSC `Hazards` `HazardType/HazardTypeID` always empty (§3.20), CPSC `Products[].Model` empty-string (§3.27/3.35), USCG `'N/A'` HIN sentinel survival (§3.28/3.38). These are from raw dictionaries / sampled exploratory JSON, consistent with coverage, but not independently re-derivable from dbt SQL alone.
- **Classification corpus distribution & `risk_level` 4-value domain (§3.10, §3.11)** — **✅ RESOLVED 2026-06-19** by the independent data-side audit (`data-side-provenance-handover-2026-06-19.md` §3): the live per-source classification distribution was measured and only the 4 `risk_level` CASE values confirmed (no `Medium - Class I`). Both are now warn-guarded by dbt `accepted_values` tests on the pipeline's nightly build.

---

## 6. Gap-Closure Verification (2026-06-17)

A focused follow-up pass closed the three open verification gaps from §5 with independent high-effort verifier agents reading the exact source files. All three are now **HIGH confidence**.

### 6.1 ADR attributions — confirmed (0 corrections)

The §1 "ADR text unread" caveat is fully discharged. The four load-bearing ADRs were read in `consumer-product-recalls/documentation/decisions/` and every cited attribution confirmed against the ADR text:

- **ADR 0038** (gold-layer modeling) §Decision 2: "Gold reuses silver surrogate keys verbatim — never re-keyed" → confirms the `recall_event_id` verbatim-reuse claim (§3.1); also grounds the `mart_*`/`fct_*` shape and FTS-GIN indexing.
- **ADR 0036** (cross-source canonical silver naming) §D2/D1/D3: `classification` source-native, NOT normalized (FDA `1/2/3/NC`, USDA `Class I/II/III/PHA`, USCG `H/L/M/S`); `recall_event.description → recall_reason` rename with USDA's structured enum split into `reason_category`; per-source disjoint `type` domains → confirms §3.10, §3.14, §3.30.
- **ADR 0042** (gold serving marts read contract) §Context: `firms`/`product_names`/`models`/`hins` are always non-null `'[]'::jsonb` arrays (API types them `list`, never `list | None`); `classification`/`risk_level`/`is_active`/`announced_at`/`distribution_states` are deliberately un-normalized contract shapes; `firm_{usda,uscg,fda}_attributes` names are frozen → confirms §3.24, §3.8–3.13/§3.19, and the firm-sidecar columns.
- **ADR 0035** (cross-source SCD-2 silver dimensions) §Decision 3 + the 2026-06 amendments: SCD-2 sidecars built for USCG/USDA/FDA, renamed source-uniform (C19), CPSC kept name-keyed (no sidecar) → confirms the FDA/USDA/USCG-only firm-sidecar matrix.

**Verdict: 0 attributions wrong, 0 corrections.** The semantic/naming/combine ADRs all live in the **pipeline** repo; the API-repo `decisions/` (0001–0014) cover serving-layer concerns and are not the cited semantic ADRs. *Residual (non-load-bearing):* secondary citations (0002/0007/0022/0026/0027/0031/0033/0034) corroborated indirectly, not each opened.

### 6.2 `alternate_names` — LOW → HIGH

Lineage confirmed line-by-line: `enrichment.firm_crosswalk.alternate_names` (jsonb array per crosswalk row) → surfaced as `x.alternate_names` in the `resolved` CTE via LEFT JOIN on `x.firm_id = md5(normalized_name)` (`firm.sql:193, 195-196`) → flattened in `alias_flat` with `lateral jsonb_array_elements_text(coalesce(alternate_names,'[]'::jsonb))` + `jsonb_agg(distinct alias order by alias)` grouped by `canonical_firm_id` (`firm.sql:204-211`) → final SELECT `left join alias_flat af using (canonical_firm_id)`, NULL when no aliases (`firm.sql:220,222`) → gold passthrough `f.alternate_names`, no transform (`mart_firm_profile.sql:118`). Meaning per `_silver.yml:151-156`: brand/surface-form aliases (DBA brand + brand-bearing parentheticals, e.g. "Deere & Company (John Deere)" → "John Deere") for search + RapidFuzz recall; nullable, untested. Distinct from `observed_names` (`firm.sql:217` = raw agency name spellings). **Populated:** live, `has_alternate_names=1213` of `total_firms=24331` (~5.0%) per `audit_coverage.txt:251`. **Residual (only piece unverifiable from dbt alone):** the upstream Python alias-extraction rules (`extract_paren_aliases` / DBA detection in `recalls resolve-firms`) were not read — dbt only consumes the resulting array.

### 6.3 `distinct_products` — MEDIUM → HIGH

The full CTE chain in `mart_firm_profile.sql` was re-read; per-firm attribution confirmed at the SQL level:

- `event_products` (`:99-103`): `count(distinct recall_product_id) as n_products` grouped by `recall_event_id` — distinct products counted once per **event**.
- `firm_product_counts` (`:105-110`): `sum(ep.n_products) as distinct_products` joined to `(select distinct firm_id, recall_event_id from firm_recalls)` grouped by `firm_id` — sums per-event counts over the firm's **distinct events** (per-firm aggregation).
- Projection (`:125`, LEFT JOIN `:132`): `coalesce(fpc.distinct_products, 0)` — floored to 0, never null.
- Model comment (`:94-98`) documents intent: count per-event once then sum over the firm's distinct events to avoid the firm×product fan-out; a `recall_product_id` belongs to exactly one event, so per-event counts sum with no intra-firm double-count — but a product on a multi-firm event is attributed to **each** firm. Per-firm footprint, **not** globally deduplicated.

**Cross-check:** `audit_coverage.txt:283` (avg=25.69, max=48006, zero=14, gt100=590) and `fct_recalls_by_firm:515` (Mercedes-Benz 48006 products / 517 events, ~93/event) are reachable only under summed-per-event attribution, independently corroborating the SQL. **No residual.**
