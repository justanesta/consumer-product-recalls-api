This is a document of questions and notes I have reacting to the [api-reference.md](../documentation/api-reference.md) document.

# GET /recalls

## Filter parameters
Why are these recall filter parameters only available for **one** value and not multiple such as via a comma separate list or array-like object? Especially because there is a defined known list of available options

> **✅ Resolution — multi-value filters (agreed 2026-06-16; implementation deferred until the full audit is reviewed).**
>
> There's no technical reason these are single-value — it was a v1 simplicity choice. We'll add **multi-value filtering** with the standard convention: **multiple values for the *same* field = OR (any-of); different fields still AND.** So `?source=CPSC&source=FDA&classification=Class%20I` means `(source IN ('CPSC','FDA')) AND (classification = 'Class I')`. This maps directly onto a faceted filter UI (checkbox groups) on the website.
>
> **Which fields, the operator, and the live backing index** (from the gold index audit; `mart_recall_summary` = 93,386 rows):
>
> | Filter | Multi-value | Operator | Live index | Index-backed? |
> |---|---|---|---|---|
> | `source` | yes | `IN` | btree `(source, published_at)` | ✅ leading col |
> | `classification` | yes | `IN` | btree `(classification)` | ✅ |
> | `distribution_state` | yes | `&&` (overlap) | GIN `(distribution_state_codes)` | ✅ |
> | `distribution_country` | yes | `&&` (overlap) | GIN `(distribution_country_codes)` | ✅ |
> | `lifecycle_status` | yes | `IN` | — none | seq scan (fine — low cardinality at 93k rows) |
> | `distribution_scope` | yes | `IN` | — none | seq scan (correctly unindexed — NOT NULL 4-value enum) |
> | `is_active` | **no** | — | btree `(is_active)` | tri-state boolean; "both" = omit the filter |
> | `firm` | **no** | — | — | free-text substring; a firm name can contain a comma |
> | `published_*` / `announced_*` | **no** | — | — | already ranges |
>
> **Mechanism (keeps every FastAPI nicety):** declare each as `list[Source]` / `list[str]` so FastAPI validates every element (precise 422 with `loc`), renders a typed array param in `openapi.json` (Swagger multi-add widget; the committed snapshot describes it), and needs zero parsing. Layer **comma-tolerance** with a ~5-line Pydantic `BeforeValidator` that splits comma-bearing elements *before* enum coercion — so `?source=CPSC,FDA` and `?source=CPSC&source=FDA` are equivalent. Safe because none of these fields' legal values contain a comma (that's exactly why `firm`/dates stay single-value).
>
> **Format:** the *declared* form is the repeated/array param (clean validation + honest OpenAPI); comma-separated is a documented convenience layered on top. **No length cap** on the facet filters (the 5-value `source` etc. can't get long). A cap belongs only to the unbounded bulk-ID lookup (see Q2/Q3 → [`../TODO.md`](../TODO.md) → "Bulk identifier lookup").
>
> **Not POST.** A POST-body query for facets would forfeit HTTP caching (ADR 0007 — POST is uncacheable by browsers/CDNs/proxies), linkability/bookmarking, the GET-only CORS surface (ADR 0014; POST+JSON adds an `OPTIONS` preflight per call), and safe-method retry semantics. CSV-in-GET covers even "12 states" (~35 chars, far under URL limits) and still hits the GIN. POST is reserved for genuinely large/unbounded *identifier* lists (Q2/Q3).
>
> **Non-breaking + keyset-safe:** a single value still behaves exactly as today; the `ORDER BY (published_at DESC, recall_event_id)` and the cursor codec are unchanged — multi-value only adds an `IN`/`&&` predicate to the WHERE. The same `RecallFilters` powers `/recalls`, `/recalls/search`, and (for `source`) `/products/search`, so all three benefit. Planner stats are fresh (audit §D), so there's no stale-stats seq-scan risk.
>
> **🟢 Implemented 2026-06-17 (`feature/api-audit`).** `deps.split_query_list` (comma-tolerant `BeforeValidator`) + per-element-constrained list query types; `RecallFilters` categorical fields are now `list[…]`; `recalls_predicates` emits expanding `IN` for `source`/`classification`/`lifecycle_status`/`distribution_scope` and array overlap `&&` for `distribution_state`/`distribution_country`; `/products/search` `source` is multi-value too. `openapi.json` regenerated (array params). Coverage: unit (`test_deps`, `test_queries_recalls`, `test_queries_products`) + integration (comma + repeated forms, any-of/AND composition, `&&` overlap). Full suite green (147 passed).

### classification
Distinct values:
```
   classification    
---------------------
- 1
- 2
- 3
- Class I
- Class II
- Class III
- H
- L
- M
- NC
- Public Health Alert
- S
``` 

### lifecycle_status
```
  lifecycle_status   
---------------------
 
- Open
- Closed
- Active Recall
- Public Health Alert
- Completed
- Ongoing
- Closed Recall
- Terminated

```

### distribution_scope
```
 distribution_scope 
--------------------
- Regional
- Nationwide
- Unspecified
- International
```

### distribution_state_codes
```
code 
------
- AK
- AL
- AR
- AS
- AZ
- CA
- CO
- CT
- DC
- DE
- FL
- GA
- GU
- HI
- IA
- ID
- IL
- IN
- KS
- KY
- LA
- MA
- MD
- ME
- MI
- MN
- MO
- MS
- MT
- NC
- ND
- NE
- NH
- NJ
- NM
- NV
- NY
- OH
- OK
- OR
- PA
- PR
- RI
- SC
- SD
- TN
- TX
- UT
- VA
- VI
- VT
- WA
- WI
- WV
- WY

```
### distribution_country_codes

```
 code 
------
 AE
 AF
 AL
 AM
 AO
 AR
 AT
 AU
 AZ
 BA
 BB
 BD
 BE
 BG
 BH
 BN
 BO
 BR
 BS
 BW
 BY
 BZ
 CA
 CH
 CI
 CL
 CM
 CN
 CO
 CR
 CU
 CY
 CZ
 DE
 DK
 DO
 DZ
 EC
 EE
 EG
 ES
 ET
 FI
 FJ
 FR
 GB
 GH
 GR
 GT
 GY
 HK
 HN
 HR
 HT
 HU
 ID
 IE
 IL
 IN
 IQ
 IR
 IS
 IT
 JM
 JO
 JP
 KE
 KH
 KP
 KR
 KW
 KZ
 LA
 LB
 LK
 LT
 LU
 LV
 LY
 MA
 MD
 ME
 MG
 MK
 MM
 MN
 MT
 MU
 MV
 MW
 MX
 MY
 MZ
 NA
 NG
 NI
 NL
 NO
 NP
 NZ
 OM
 PA
 PE
 PG
 PH
 PK
 PL
 PT
 PY
 QA
 RO
 RS
 RU
 RW
 SA
 SD
 SE
 SG
 SI
 SK
 SN
 SO
 SR
 SV
 SY
 TH
 TN
 TR
 TT
 TW
 TZ
 UA
 UG
 UY
 UZ
 VE
 VN
 YE
 ZA
 ZM
 ZW

```

### source_recall_id

These are unique per recall but I'm trying to think of a way to batch lookup a collection of recalls based on a list/array of `source_recall_id`s a user has without looping through individual calls.

# GET /firms/{firm_id}
Similarly for `GET /recalls`. Is there not a way to supply an array/list of `firm_ids` and get back an array/list of matching `FirmProfile` objects?

**✅ Resolution to both `source_recall_id` and `firm_id` bulk lookup deferred to [TODO](../TODO.md) task "Bulk identifier lookup — recalls and firms (audit Q2 / Q3)"**

## Response Fields

### General Questions
I am trying to think through the difference between the fields in `RecallSummary` and `RecallDetail` and the differences in the models overall. Questions:
- Does it make sense to have these separate models for these endpoints? Why is it set up this way?
- What are we losing and gaining by not having some fields that are available in `RecallDetail` available in `RecallSummary`? 
- What are standard/typical API setups for databases with this structure? 

> **✅ Resolution — keep the list/detail split (analyzed 2026-06-16).**
>
> `RecallSummary` and `RecallDetail` are two **projections of the same `mart_recall_summary` row** (a denormalized OBT — pipeline ADR 0038/0042), not a normalized parent/child. List/search select an 18-column scalar subset (`_LIST_COLS` → `RecallSummary`); detail selects the full ~35-field row (`RecallDetail` = the 18 + 17 detail-only fields: narrative, geo arrays, the jsonb rollups `firms`/`product_names`/`models`/`hins`/`hazards`/`product_upcs`, and provenance/lifecycle).
>
> **Decision: keep the split — it's the canonical, correct shape here.** (1) Payload — the detail-only fields are the heavy jsonb arrays + narrative; shipping them ×100 list rows bloats pages from KB to MB. (2) Cost — the 18 scalars ride the keyset index; the rollups are TOAST blobs not worth reading for rows nobody opens. (3) Semantics — a list is for *scanning to choose*, detail is for *reading one fully*. (4) Contract — two independently-evolvable, separately-typed OpenAPI models. The summary deliberately keeps the **counts/flags** (`firm_count`, `product_count`, `edit_event_count`, `has_been_edited`) as teasers, so a list row shows "3 firms · 12 products" without the arrays.
>
> **Gain/loss:** gain small/fast/index-aligned list pages; the cost is an extra round-trip (or N+1) only when a list context needs a detail-only *array's contents*. The counts cover the common "how many?" need, so the real gap is narrow.
>
> **Standard pattern:** mainstream REST "two fixed representations" (GitHub's minimal-vs-full reps). Alternatives — sparse fieldsets (`?fields=`), `?expand=`/include (Stripe/JSON:API), GraphQL — all fight this API's HTTP-cache + committed-OpenAPI-snapshot model, so the fixed split is right for a public, cached, read-only API.
>
> **Frontend mapping (per the Phase-9 website plan):** `RecallDetail` → the templated individual recall page `/recalls/{source}/{recall_id}` (§5.3) — header, products, firms, lifecycle timeline (your assumption is correct). `RecallSummary` → **one row in a *table*** on the recalls browser `/recalls` (§5.2; columns date·source·title·classification·firm·status), the firm page's "this firm's recalls" table (§5.4), and recall-search results (`RecallSearchHit` = summary + `rank`). Summary = "scan many → click one"; detail = "read one." **Those §5.2 columns are all summary fields**, so the current projection already covers the v1 frontend with **no field promotion needed**.
>
> **Future flag (promote vs expand):** only if a list row/chip later needs detail-only data (most likely `distribution_state_codes` as a geo badge, or a `product_names` preview) — then either promote that one field into `_LIST_COLS` + `RecallSummary` (cache-friendly; preferred for 1–2 fields) or add an `?expand=` mechanism (if general flexibility is wanted). Not needed for v1.
>
> **Minor code nit:** `RecallSearchHit` inherits `RecallSummary`, but `RecallDetail` re-declares the 18 summary fields verbatim — a deliberate decoupling (independent defaults/descriptions), not a flaw. Leave as-is; a shared base mixin is an option only if DRY ever matters.

### RecallDetail
- Would `last_seen_at` make the most sense as a "last edit date" or based on the database is there another date value that would make more sense utilize for such a date on the individual recall page.

> **✅ Resolution — show "Published: {published_at}"; defer a dated "last revised" (decided 2026-06-16).**
>
> `last_seen_at` is the **wrong** field — it's `max(extraction_timestamp)` (our pipeline's last poll, all 5 sources), so it ticks every cron run with no edit. And there is **no dedicated cross-source "source last-edited" timestamp on gold**: gold surfaces edits only as `edit_event_count` + `has_been_edited`; the underlying `recall_event_history.changed_at` (= our *detection* time, not the agency's stamp) is dropped at the rollup, and the source-stated watermarks (`event_lmd` / `last_publish_date` / `last_modified_date`) are noisy (ADR 0023 archive-migrations), 3/5-source, and not exposed (FDA's is folded into `published_at`).
>
> **For now:** keep the API as-is; the recall page shows **"Published: {published_at}"** (optionally a `has_been_edited` "(revised)" tag, no date). A trustworthy *dated* "Last revised" is logged as a cross-repo gold change → [`../TODO.md`](../TODO.md) → "Surface a 'last revised' date — gold `last_edited_at` + API field".
>
### ProductSearchHit
Are UPCs actually matched at the recall level via array containment? And if so, why? How exactly **do** I product search by `upc`?

These are three upcs I know for a fact are in the database and return nothing:

```
justanesta ~/projects/consumer-product-recalls-api feature/api-audit > curl -s "https://consumer-product-recalls-api.fly.dev/products/search?upc=082294319754" | jq 
{
  "items": [],
  "next_cursor": null,
  "limit": 25,
  "total": null
}
justanesta ~/projects/consumer-product-recalls-api feature/api-audit > curl -s "https://consumer-product-recalls-api.fly.dev/products/search?upc=3086120600051" | jq 
{
  "items": [],
  "next_cursor": null,
  "limit": 25,
  "total": null
}
justanesta ~/projects/consumer-product-recalls-api feature/api-audit > curl -s "https://consumer-product-recalls-api.fly.dev/products/search?upc=072000729700" | jq 
{
  "items": [],
  "next_cursor": null,
  "limit": 25,
  "total": null
}
```

> **✅ Resolution — confirmed UPC bug (two breakages, one root cause); fix batched (2026-06-16).**
>
> **How UPC search is *meant* to work:** the per-product `upc` column is **100% NULL** (all sources, by construction — its empty btree was dropped in gold-audit G5), so `?upc=` matches at the **recall level** via jsonb containment over `recall_product_upcs` (CPSC supplies UPCs at recall grain as `product_upcs`, denormalized onto each product row). It is also **extremely sparse** — only **~453–466 CPSC recalls** carry any UPC (≈0.5% of the corpus; ~0% of recent CPSC).
>
> **Why your three known-good UPCs returned nothing — a confirmed shape mismatch.** Gold stores UPCs as an **array of objects** `[{"upc": "082294319754"}]` (lowercase key — confirmed via `jsonb_typeof(product_upcs->0) = object`), but the API assumes an **array of strings**. Two live bugs result:
> - **Bug A — detail 500s:** `RecallDetail.product_upcs` is `list[str]`; Pydantic can't validate a `{"upc": …}` dict as `str`, so **every UPC-carrying recall detail returns HTTP 500** (verified live: `GET /recalls/CPSC/03051` → 500). ~453 broken detail pages.
> - **Bug B — search misses:** `recall_product_upcs @> '["X"]'` can never match `[{"upc":"X"}]` → `0 hits` even for codes confirmed present in gold.
>
> **Why CI was green:** `tests/fixtures/seed_gold.sql` seeds UPCs as *strings* — a shape that doesn't exist in production — so the tests validated fiction.
>
> **Fix (batched with the other audit fixes; this repo):** (1) `RecallDetail.product_upcs` — a `BeforeValidator` mapping `{"upc": x} → x`; (2) `ProductSearchHit.recall_product_upcs` — same; (3) `_upc_where` — containment bind `[{"upc": upc}]` (stays GIN/R3-served); (4) fix `seed_gold.sql` to the real object shape + turn the two UPC tests into genuine regression coverage. No OpenAPI change (fields stay `list[str]`); all four tolerate a future string shape.
>
> **Cleaner long-term (cross-repo):** flatten gold to string arrays → [`../TODO.md`](../TODO.md) → "Flatten gold UPC arrays to plain strings". Non-blocking (the API fix tolerates both shapes).
>
> **🟢 Implemented 2026-06-17 (`feature/api-audit`).** Shared `models/common.flatten_upcs` (`{"upc": x} → x`, None → `[]`, bare strings pass through) wired into `RecallDetail.product_upcs` and `ProductSearchHit.recall_product_upcs`; `_upc_where` binds `[{"upc": upc}]`; `seed_gold.sql` switched to the real object shape `[{"upc":"…"}]`. Regression tests added (model-level both shapes + integration: detail no longer 500s and flattens, search containment matches). Full suite green (147 passed); no OpenAPI change (fields stay `list[str]`).

### FirmProfile
- Why is the `roles` jsonb column from `mart_firm_profile` not included?

> **✅ Resolution — `roles` IS exposed; the gap was the docs (fixed 2026-06-16).**
>
> Premise correction: `roles` is **not** omitted from the API — it's a `FirmProfile` field (`models/firms.py`), selected from the mart (`queries/firms.py`), and **present in `openapi.json`**, so `GET /firms/{id}` returns it today. What was missing was its row in `api-reference.md`'s FirmProfile table — along with two siblings that were also returned-but-undocumented: `observed_company_ids` and `alternate_names`. **Fixed:** all three added to the api-reference FirmProfile field table.
>
> What they are (from the gold defs): `roles` = `jsonb_agg(distinct role)` across the firm's recall links — the distinct roles played (`manufacturer` / `establishment` / `filer` / `importer` / `distributor`). `observed_company_ids` = every structured government id (FDA FEI / USDA establishment number / USCG MIC / CPSC company_id) that folded into the cluster (the merge audit trail + the sidecar join key). `alternate_names` = brand / DBA surface-form aliases (a search/alias field), distinct from `observed_names`'s raw spellings.

# General Question
I want to be very explicity about which return fields for each endpoint have data for all five sources and which only have either one or a collection of less than five. If a data field is populated by only one or a non-universal number of sources it should say which sources feed that data field explicitly. Is that wired into our plan of how to build this API documentation?

Additionally, where in the documentation (either in the dynamically created/updated docs or on another page/resource) should we put an actual data dictionary with definitions for each exposed field in the API? Is any of the above in any of our front-end website/web app planning documentation in this repo (do we even have any of those docs or is it just what I have in the `consumer-product-recalls/` repo)

> **✅ Resolution — provenance NOT systematically wired in; single-home it in OpenAPI + a matrix (analyzed 2026-06-16).**
>
> **State today:** per-source provenance lives as **scattered prose** (per-field notes + Caveats in `api-reference.md`; root-cause prose in `data_contract.md`). There is **no field × source matrix**, and the **OpenAPI spec carries none** — so the website's auto-generated endpoint pages (rendered from `openapi.json`) show zero provenance. The prose is also **incomplete/wrong in ≥5 places** (per the gold coverage audit): `announced_at` is **populated for all 5 sources** (doc says null CPSC/NHTSA — likely a coalesce; reconcile); `risk_level` and `reason_category` are **USDA-only** (undocumented); `distribution_country_codes` is **FDA-only** in practice (doc says FDA/USDA; USDA=0); product `model` is **CPSC+NHTSA-only** (unqualified). That five-field error rate is the case for a systematic source.
>
> **Decision (single-home):** (1) **per-field definition + provenance → Pydantic `Field(description=…)` → OpenAPI** = the SSOT (standard tag e.g. `Sources: FDA, USCG, USDA (null for CPSC/NHTSA).`); it auto-renders wherever a field is shown (Swagger/Starlight/Scalar), no hand-maintained duplicate. (2) **A consolidated field × source matrix → `data_contract.md`** (new "Per-source field provenance" section) = the at-a-glance human view. (3) `api-reference.md` per-endpoint tables get a **"Sources"** column linking the matrix — never restate. (4) Website handoff `/api/caveats/` excerpts/links the matrix; endpoint pages carry provenance for free via the spec.
>
> **Data-dictionary home:** the OpenAPI `Field` descriptions ARE the per-field dictionary (machine-readable SSOT); `data_contract.md`'s matrix is the overview. Not a separate hand-written doc.
>
> **Frontend docs:** this repo has only [`../documentation/frontend-api-docs-handoff.md`](../documentation/frontend-api-docs-handoff.md) (narrow — how to render the API-docs page from OpenAPI); it has **no** provenance/dictionary. The full website plan lives in the pipeline repo at `consumer-product-recalls/project_scope/future-repos/website-frontend-plan.md`; the website repo doesn't exist yet.
>
> **Build (batched doc work + the 5 discrepancy fixes):** → [`../TODO.md`](../TODO.md) → "Per-source field provenance + field data dictionary".