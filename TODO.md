# TODO

## Blog post: `origin/<branch>` (slash) vs `origin <branch>` (space) in git

**Action:** verify this against authoritative git documentation + other sources online, then write it
up as a blog post. The explanation below is a working draft — confirm specifics (esp. error strings,
which vary by git version) before publishing.

### The point (working explanation)

They are **not** synonymous — they're two different syntactic constructs, and which one a command
accepts depends on whether the command **talks to a remote** or **reads a local ref**.

- **`origin <branch>` (space) = two arguments:** `<remote> <refspec>`. Used by commands that open a
  connection to a remote — `git push`, `git fetch`, `git pull`. `origin` is the remote name; the branch
  is a separate refspec argument.
- **`origin/<branch>` (slash) = one argument:** a *remote-tracking ref*
  (`refs/remotes/origin/<branch>`) — your local pointer to where that branch was on origin as of the
  last fetch/push. Used by commands that take a single ref / commit-ish — `git branch -u`,
  `git switch -c <name>`, `git log`, `git merge`, `git diff`, `git reset`.

**Rule of thumb:**
- talks-to-a-remote (push / fetch / pull) → `origin <branch>` (space)
- reads-a-local-ref (branch -u, switch, log, merge, diff, reset) → `origin/<branch>` (slash)

**Why the wrong form errors (the "snag"):**
- `git push origin/feature/x` → git reads `origin/feature/x` as a *remote name* →
  *"does not appear to be a git repository."*
- `git branch -u origin feature/x` → reads upstream = `origin`, branch = `feature/x` →
  *"the requested upstream branch 'origin' does not exist."*

### Research checklist (cite real docs before publishing)

- [ ] `git help push` — the `<repository> <refspec>` argument model + `--set-upstream` (`-u`) semantics.
- [ ] `man gitglossary` — definitions of *refspec*, *remote-tracking branch*, *upstream branch*.
- [ ] `man gitrevisions` — how a `<refname>` like `origin/foo` resolves under `refs/remotes/...`.
- [ ] Pro Git book — "Remote Branches" (ch 3.5) and "Working with Remotes" (ch 2.5).
- [ ] `git config push.autoSetupRemote` + `branch.autoSetupMerge` — how upstream gets set automatically.
- [ ] Refspec deep-dive: `src:dst`, leading `+` (force), e.g. `git push origin local:remote`.
- [ ] Verify the exact error strings across a couple of git versions (wording drifts).

### Blog-post angle

- Hook: "I assumed `origin/feature` and `origin feature` were the same for years — until one errored."
- Core: space = `(remote, refspec)` for network verbs; slash = one remote-tracking ref for local verbs.
- Payoff: one rule + a table of which commands take which form, and the two classic error messages decoded.

## Features

### `/recalls` sort control — `sort` + `order` params

- [ ] Add a `sort=published_at|announced_at` + `order=asc|desc` pair to `GET /recalls`. Small, clean, and
low-risk: the R2 index `(published_at DESC, recall_event_id)` backs both directions (Postgres scans
it backward for ASC), so the change is just flipping the `ORDER BY` direction and the keyset
comparison direction (`<` for DESC → `>` for ASC). Fully keyset-compatible.

Deferred — recency sort on `/recalls/search`: it's intentionally relevance-ranked (`ts_rank_cd
DESC`), which fits that endpoint's use case. Adding a date sort there is a bigger change (needs a
mode-aware cursor toggling relevance vs recency), so not now.

### Bulk identifier lookup — recalls and firms (audit Q2 / Q3)

**Goal:** let a client fetch many records in one round-trip from a list of identifiers it already
holds — a saved set of recall ids, or the `firm_id`s collected across several recall details —
instead of N sequential calls. Resolves [`project_scope/api-audit-notes.md`](project_scope/api-audit-notes.md)
Q2 (`source_recall_id` batch) and Q3 (`firm_id` batch). Two tiers, smallest footprint first.

**Tier 1 — multi-value on the existing GET surface (small, same-context lists; rides the Q1 multi-value work).**

- [ ] Recalls: once `source_recall_id` is multi-value (Q1),
  `?source=CPSC&source_recall_id=24-001,24-002,24-003` is a source-scoped batch lookup for free.
  `source_recall_id` is unique only *with* `source`, so the single-source constraint is correct, not
  a limitation. Returns the normal keyset-paginated `Page[RecallSummary]`.
- [ ] Firms: needs a NEW `GET /firms` collection endpoint (today only `GET /firms/{firm_id}` detail
  exists) accepting `?firm_id=<hex>,<hex>,…` → `Page[FirmProfile]`. `firm_id` is a globally-unique
  32-hex md5, so no source scoping is needed.
- Good for up to ~dozens of ids: a 32-hex `firm_id` is 32 chars, so ~50 ids ≈ 1.6 KB — still under the
  ~2 KB safe URL limit. Cap the list (e.g. ≤ 100) and 422 past it.

**Tier 2 — dedicated batch endpoints (large / unbounded / cross-source lists; POST body).**

- [ ] `POST /recalls/batch` — body `{"recall_event_ids": ["<md5>", …]}` (the globally-unique
  surrogate, unambiguous across sources) and/or `{"keys": [{"source": "...", "recall_id": "..."}]}`
  for clients holding agency-native ids. Returns `[RecallDetail]` (or `[RecallSummary]`).
- [ ] `POST /firms/batch` — body `{"firm_ids": ["<32hex>", …]}` → `[FirmProfile]`.
- Decide partial-hit semantics: return only the found records (lean) vs. echo every requested id with
  `found: false` / `null` so the client can reconcile misses. Recommend the latter for batch UX.
- Cap the list (e.g. ≤ 1000), dedupe ids server-side, and document that batch responses are **not
  cached** (client-specific, not the cacheable browse traffic).

**Why POST for Tier 2:** identifier lists can be large/unbounded (the "fetch these 5,000 ids" case)
and overflow URL limits (~2 KB safe, ~8 KB practical cap). This is the one place POST earns its keep —
accepted *because* the input itself is the problem, with the lost caching an acceptable trade for
batch (vs. facet) traffic. Everything else stays GET. Full POST trade-off analysis is in the Q1
resolution in [`project_scope/api-audit-notes.md`](project_scope/api-audit-notes.md).

**Enables:** "my saved recalls" / "my watched firms" dashboards, client-side reconciliation against an
external id list, and efficient hydration of a detail view from a set of ids without request fan-out.

### Surface a "last revised" date — gold `last_edited_at` + API field (audit: RecallDetail)

**Goal:** give the recall detail page a trustworthy "last updated/revised" date. Resolves
[`project_scope/api-audit-notes.md`](project_scope/api-audit-notes.md) → RecallDetail (the
`last_seen_at`-as-"last edit date" question).

**Why the existing fields don't work:** `last_seen_at = max(extraction_timestamp)` is *our pipeline's
last poll* (all 5 sources), not a source edit — it ticks every cron run with no edit, so it can't be a
"last updated" date. `published_at` is the publication date (and for FDA it's `event_lmd`, a
last-modified date — semantics differ by source). The edit signal that *does* exist cross-source is
`recall_event_history.changed_at`, but gold rolls it up only as `edit_event_count` (count) +
`has_been_edited` (bool) — the actual timestamp is dropped.

**Cross-repo change (pipeline `consumer-product-recalls`):**
- [ ] Add `last_edited_at = max(changed_at)` to `mart_recall_summary.sql`'s `history_rollup` CTE,
  beside the existing `count(*)`. Additive, non-breaking (ADR 0042).
- [ ] Project it on `RecallDetail` in this API; the recall page shows "Last revised: {date}" only when
  `has_been_edited`.

**Honesty caveats to carry into the field description + UI:**
- It's our **detection time** (the `extraction_timestamp` at which we first saw the changed value —
  daily-cron granularity), NOT the agency's own stated edit timestamp.
- It's **sparse**: `recall_event_history` was reseeded at pipeline Phase 6a.5, so it's `NULL` for
  recalls with no detected edit since the reseed (it back-fills as daily incrementals accumulate).

**Enables:** §5.3 lifecycle-timeline "last revised" badge (the timeline *is* the `recall_event_history`
rows; this date is the `MAX` of their `changed_at`).

**For now:** API stays as-is; the recall page shows **"Published: {published_at}"** only (optionally a
`has_been_edited` "(revised)" tag, no date). This item un-blocks the dated version.

### Flatten gold UPC arrays to plain strings — `product_upcs` / `recall_product_upcs` (audit: ProductSearchHit)

**Goal:** make the recall UPC arrays a clean `list[str]` at the gold layer instead of the current
array-of-objects `[{"upc": "082294319754"}]` (the CPSC source shape, passed straight through
`recall_event.sql:72`). A plain string array `["082294319754"]` is the correct serving shape and lets
the API drop its object-extraction shims.

**Why it matters (the audit finding):** the object shape caused two live API bugs — `RecallDetail`
detail pages **500** on every UPC-carrying recall (~453 CPSC), and UPC search returned **0 hits** for
real codes (containment `@> '["X"]'` can't match `[{"upc":"X"}]`). The API-side fix is **batched with
the other audit fixes** and is written **tolerant of both shapes**, so this gold change is a
*simplification, not a blocker*. See [`project_scope/api-audit-notes.md`](project_scope/api-audit-notes.md)
→ ProductSearchHit.

**Cross-repo change (pipeline `consumer-product-recalls`):**
- [ ] Flatten in gold: `jsonb_agg(elem->>'upc')` (or flatten at the CPSC silver source) so
  `mart_recall_summary.product_upcs` and `mart_product_search.recall_product_upcs` become string arrays.
- [ ] Breaking to the gold read-contract (ADR 0042) — coordinate with the API and bump
  `gold_meta.schema_version`.
- [ ] Once shipped, simplify the API: drop the UPC object-extraction validators and revert the search
  predicate to plain-string containment.

**Distinct from:** the all-NULL per-product `upc` column (100% NULL, btree dropped in gold-audit G5) —
that was a forward-looking placeholder for *structured per-product* UPCs; this item is about the
*recall-level* arrays that actually carry data.

### Per-source field provenance + field data dictionary (audit: General Question)

**Goal:** make every exposed field state explicitly which of the 5 sources populate it, and give each
field a single-homed definition — so a consumer (and the website) knows when a field is universal vs.
source-partial. Resolves [`project_scope/api-audit-notes.md`](project_scope/api-audit-notes.md) →
General Question. Provenance is currently scattered prose (api-reference caveats), absent from
`openapi.json`, and wrong/incomplete in ≥5 places (below).

**Single-home design (per `documentation/documentation_model.md`):**
- [ ] **Per-field definition + provenance in the OpenAPI spec** via Pydantic `Field(description=…)` on
  every exposed model field (`models/recalls.py`, `models/products.py`, `models/firms.py`). Use a
  standard suffix, e.g. `Sources: FDA, USCG, USDA (null for CPSC/NHTSA).` This is the SSOT and
  auto-renders on the website's endpoint pages (starlight-openapi) — no hand-maintained duplicate.
  Regenerate + commit `openapi.json`.
- [ ] **A field × source provenance matrix** as a new "Per-source field provenance" section in
  `documentation/data_contract.md` (the at-a-glance human view). Source the cells from the gold
  coverage audit (`consumer-product-recalls/data/exploratory/gold/audit_coverage.txt`).
- [ ] **Add a "Sources" column** to the per-endpoint field tables in `documentation/api-reference.md`
  that links the matrix (don't restate).
- [ ] **Wire into the website handoff**: note in `documentation/frontend-api-docs-handoff.md` that
  provenance now travels *in* the spec (endpoint pages) and the matrix backs `/api/caveats/`.

**Provenance ground truth (from the coverage audit) — non-universal fields:**
- Recalls: `is_active`/`lifecycle_status`/`classification` = FDA+USCG+USDA (null CPSC/NHTSA);
  `is_currently_active`/`was_ever_retracted` = NHTSA+USDA; `distribution_state_codes` = FDA+USDA;
  `distribution_country_codes` = **FDA only**; `risk_level`/`reason_category`/`distribution_states` =
  **USDA only**; `product_upcs` = **CPSC only** (sparse); `hins` = **USCG only**.
- Products: `model` = CPSC+NHTSA; `model_year` = NHTSA+USCG; `hin` = USCG; `classification`/`is_active`
  = FDA+USCG+USDA; `risk_level` = USDA; `recall_product_upcs` = CPSC (sparse); `upc` = **none (100% null)**.
- Firms: sidecars `firm_{usda,uscg,fda}_attributes` per their source (CPSC/NHTSA none);
  `alternate_names` sparse; everything else cross-source.

**Discrepancies to FIX while doing this (docs vs. live data):**
- [ ] `announced_at` — api-reference says "null for all CPSC/NHTSA" but it's **100% populated for all 5**
  (likely a `coalesce(announced_at, published_at)` upstream — reconcile the wording / verify the recipe).
- [ ] `risk_level` — mark **USDA-only** (api-reference + data_contract).
- [ ] `reason_category` — mark **USDA-only**.
- [ ] `distribution_country_codes` — correct "FDA/USDA" → **FDA-only in practice** (USDA=0).
- [ ] product `model` — mark **CPSC+NHTSA-only**.

> **Note (2026-06-17):** the inline provenance ground-truth in this item is **superseded** by the empirical [`project_scope/provenance-analysis-2026-06-17.md`](project_scope/provenance-analysis-2026-06-17.md) (e.g. product `model` is **NHTSA-only for real values**; CPSC is empty-string `""`, soon NULL after the pipeline fix). Use the deliverable's matrix as SSOT for the apply; the checkboxes above stand as the original audit pointers.

## Performance

### Stop projecting pipeline-observability fields from the API (audit Q2 / provenance analysis)

**Goal:** drop the internal pipeline-observability proxies the API currently exposes. They imply
authoritative agency semantics they don't have, several are source-partial (null for most sources),
and they duplicate/confuse `is_active`. Keep only `has_been_edited` as a single honest "revised"
signal. Source of the finding:
[`project_scope/provenance-analysis-2026-06-17.md`](project_scope/provenance-analysis-2026-06-17.md)
(§3.58-3.64 + systemic findings); resolves the audit's RecallDetail observability-field question.

**Drop from the API response models** (this is **API-only** — the pipeline keeps these in gold for its
own observability; the API just stops projecting them):
- [ ] `is_currently_active`, `was_ever_retracted` (`RecallDetail`) — {USDA,NHTSA}-only *presence-manifest*
  flags (NULL for CPSC/FDA/USCG); names imply authoritative status they lack; `is_currently_active` is
  conflated with the lifecycle `is_active`.
- [ ] `first_seen_at`, `last_seen_at` (`RecallDetail`) — our cron's first/last *poll* timestamps
  (pipeline internals; `last_seen_at` already ruled out as a "last edited" date — see the "last revised"
  Features item).
- [ ] `edit_count`, `edit_event_count` — numeric pipeline-*detection* counts (content-hash versions /
  history-row counts); imply agency-edit semantics; redundant with each other and with `has_been_edited`.
  Note `edit_event_count` is in BOTH the list projection (`_LIST_COLS` → `RecallSummary`) and `RecallDetail`.

**Keep:** `has_been_edited` (boolean) as the one honest "changed since first ingest" flag — pending a
quick check of `consumer-product-recalls/project_scope/future-repos/website-frontend-plan.md` §5.3 (if
the detail page has no "revised" badge, drop this too).

**Mechanics — fold into the Provenance apply workflow:** remove the columns from `queries/recalls.py`
(`_LIST_COLS` + the `sa.table()` literal), the fields from `models/recalls.py` (`RecallSummary` +
`RecallDetail`), update `tests/fixtures/seed_gold.sql` + the affected unit/integration tests, regenerate
`openapi.json`, and reflect the removals in `documentation/data_contract.md` (detail projection list) and
`documentation/api-reference.md` (RecallDetail field table). **Breaking** to the OpenAPI contract — do it
now while pre-go-live (no consumers); after launch it would need a deprecation cycle.
