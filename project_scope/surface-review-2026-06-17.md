# API Surface Review — Consumer Product Recalls API

**Date:** 2026-06-17
**Posture:** READ-ONLY. No code was changed in producing this review; every finding cites a concrete `file:line` that was read, and every "X is unused / Y is untested" claim was cross-checked with a grep or read before being asserted.
**Repo:** `consumer-product-recalls-api` (branch `feature/api-audit`)

## Purpose

A surface-level review of the API repo's public contract and test suite, looking for dead code, redundant/over-built features, naming-and-semantics drift between code/docs/spec, cross-endpoint inconsistencies, and test redundancy/gaps. The goal is a single reviewable action list that distinguishes work that should **fold into the in-flight Q2 provenance prune** from **standalone fixes**, and that separates clear defects from genuine design calls.

## Method

For each review dimension (dead-code, redundant-features, naming-semantics, consistency, test-redundancy, test-gaps): enumerate candidate findings → locate them in code → run an independent **adversarial** verification pass (re-derive from source, attempt to falsify the claim, confirm with grep/read) → synthesize. Findings that survived verification are **confirmed** or routed to **needs-human-judgment**; findings whose central claim did not hold are **rejected** and recorded so they are not re-raised.

## Counts

| Bucket | Count |
|---|---|
| Confirmed | 22 |
| Needs human judgment | 4 |
| Rejected (false positives) | 1 |
| High severity (confirmed) | 1 |
| Medium severity (confirmed) | 6 |
| Low severity (confirmed) | 15 |

Severity is impact-weighted, not a defect/non-defect split: several confirmed mediums and the single high are documented-contract or config-trap issues rather than runtime crashes on the happy path.

---

## 1. Prioritized action list (confirmed findings)

Ranked by severity, then by effort (cheapest first within a severity band), grouped by theme. Tags:
- **[FOLD INTO PROVENANCE APPLY]** — rides the Q2 prune (TODO.md:199-222) and its naming/description cleanup; these touch the same fields/files the apply already edits.
- **[STANDALONE]** — independent fix; no dependency on the Q2 apply.

### Theme: Consistency / robustness

#### A1. Cross-path cursor replay yields 5xx, not the 400 ADR 0004 promises — **HIGH** — effort: small — **[STANDALONE]**
- **Where:** `src/recalls_api/pagination.py:48-53,66-70,79-82`; `src/recalls_api/routers/products.py:69,73,77`; `src/recalls_api/routers/recalls.py:65,96`; contract in `documentation/decisions/0004-keyset-cursor-codec.md:50`.
- **What & why:** The opaque cursor is a 2-tuple with two shapes minted on different endpoints — `(ISO-string, id)` for published_at paths and `(float, id)` for rank/FTS paths — but `Cursor.decode` guards only **arity** (`len==2`, pagination.py:51-52), never element **type**. A rank cursor replayed on a published_at path passes decode, then at pagination.py:67 the `isinstance(cur_pub_raw, str)` check is False for the float, so it skips the `fromisoformat` parse and binds the float as `TIMESTAMP(timezone=True)` → asyncpg/SQLAlchemy error at execute → falls through `register_error_handlers` (errors.py:146 registers only `OperationalError/DBAPIError/SqlTimeoutError/OSError`) to `_catch_all` → **HTTP 500**. The reverse direction (ISO string into the untyped numeric `ts_rank_cd <` comparison, pagination.py:80) raises a numeric `DataError` → `_db_error_handler` → **HTTP 503 + Retry-After** (misleading: implies DB outage). ADR 0004 §2/Consequences explicitly promises the arity guard converts a wrong-shape cross-endpoint cursor into a 400 "before the seek-WHERE builder ever unpacks the tuple" — directly contradicted. Untested (test_pagination.py covers only round-trip/tamper/arity; test_recalls.py:257 covers only a garbage-base64 400).
- **Recommendation:** Make the cursor self-describing — tag the encoded payload with its sort kind (`'p'` vs `'r'`) and reject a mismatched shape with `BadCursor(400)` at decode/use time. Cheapest acceptable: type-guard at the seek boundary (`published_at_keyset_where` raises `BadCursor` if `cur_pub_raw` is not a parseable timestamp; `rank_keyset_where` raises if `cur_rank` is not numeric). Add a regression test minting a rank cursor and replaying it on a published_at endpoint (and vice versa) asserting 400.
- **Breaking-ness:** None for legitimate clients (cursors are opaque and normally fed back to the same endpoint+params). Real-world hit probability is low — this is a contract-hygiene/robustness fix, not a happy-path bug. Severity HIGH is driven by the documented-contract violation, not blast radius.
- **Note:** The precise 500-vs-503 split per direction is runtime-dependent (could not be confirmed without a live Postgres); either way it is a 5xx, not the promised 400. Deduped with A8 and T6/T7 below (same mechanism, different lens).

#### A2. firm= filter's served OpenAPI description omits that it matches ONLY `primary_firm_name` — **MEDIUM** — effort: trivial — **[STANDALONE]**
- **Where:** `src/recalls_api/deps.py:130-133` (served Query description) vs `src/recalls_api/queries/recalls.py:121-122` (predicate).
- **What & why:** The predicate compiles to `c.primary_firm_name ILIKE '%firm%'` — primary firm only, not the multi-firm `firms[]` rollup or any secondary/co-recalled firm. The served description (deps.py:132) is just `"Case-insensitive substring (unindexed)."` — it states substring/unindexed but not the load-bearing **scope** limitation. A client searching a secondary firm gets a silent miss with no signal. `api-reference.md:129` *does* say "substring match on primary_firm_name," proving maintainers know scope matters — but that detail never reached the spec consumers actually see.
- **Recommendation:** Add the scope to the served description, e.g. `"Case-insensitive substring on the recall's PRIMARY firm name only (not secondary/co-recalled firms); unindexed."`
- **Breaking-ness:** None (description text only). Regenerate `openapi.json`.

### Theme: Naming & semantics

#### A3. `is_currently_active` documented as "Most recent lifecycle state from the source feed" — it is a presence-manifest flag, NULL for 3 of 5 sources, confusable with `is_active` — **MEDIUM** — effort: small — **[FOLD INTO PROVENANCE APPLY]**
- **Where:** `documentation/api-reference.md:300`; field `models/recalls.py:104` (no code-level description, so the doc line is the sole consumer prose).
- **What & why:** Per provenance §3.63 (provenance-analysis-2026-06-17.md:846-853) the field is a presence-manifest `bool_or` flag (was the recall in the source's latest enumerating run), populated **only for USDA + NHTSA**, NULL for CPSC/FDA/USCG. The doc both misstates the derivation (presence vs lifecycle) and omits the 3-of-5 NULL. provenance rates it MEDIUM and calls the name a "likely consumer trap, easily conflated with `is_active`" — which is a genuinely different tri-state field with a *different* null set (CPSC/NHTSA per models/recalls.py:32), amplifying the trap.
- **Recommendation:** This field is on the Q2 prune list (TODO.md:212), so the primary disposition is **removal**. Until pruned, if it must stay, correct the doc to: presence-manifest flag, USDA/NHTSA only, null for CPSC/FDA/USCG, NOT a feed lifecycle state, distinct from `is_active`.
- **Note:** The per-source-NULL specifics rest on cross-repo gold lineage (provenance doc, not API-readable); the lifecycle-vs-presence mischaracterization and `is_active` confusability are directly in-repo verifiable.

#### A4. `firm=` semantic (A2) — see Consistency above; also a naming/scope issue. Deduped into A2.

### Theme: Dead code / dead config

#### A5. `Settings.page_limit_default` is defined but never consumed; the real default is a hardcoded literal — **MEDIUM** — effort: small — **[STANDALONE]**
- **Where:** `src/recalls_api/settings.py:49` (defined); `src/recalls_api/deps.py:75` (real default).
- **What & why:** `page_limit_default: int = Field(default=25, ...)` is declared but referenced nowhere in `src/` (tree-wide grep returns only the definition). The actual default is baked into the function signature: `limit: Annotated[int, Query(...)] = 25` (deps.py:75), which never reads settings. By contrast `page_limit_max` IS wired (deps.py:82). This is a **config trap, not just dormant code**: an operator who sets `PAGE_LIMIT_DEFAULT=50` gets zero behavior change. The two `25`s are duplicated and can silently drift.
- **Recommendation:** Pick one: (a) **wire it** — source the default from `settings.page_limit_default` inside `pagination_params` instead of the static `= 25`; or (b) **delete** the orphaned field and keep the single hardcoded 25 as the source of truth. Do not leave both. `could_be_intentional` (option b is valid).
- **Breaking-ness:** Option (a) makes `PAGE_LIMIT_DEFAULT` live (could change response page sizes if anyone already set it). Option (b) is inert.

### Theme: Naming & semantics (low severity, doc/description text)

#### A6. `recall_product_upcs` / `product_upcs` descriptions say "flattened from gold's object array" — flattening is API-side, not gold-side — **LOW** — effort: trivial — **[STANDALONE]**
- **Where:** `models/products.py:42-44` (ProductSearchHit.recall_product_upcs); `models/recalls.py:92-95` (RecallDetail.product_upcs).
- **What & why:** Gold passes the array through verbatim as `[{"upc":"X"}]` objects (queries/products.py:64, queries/recalls.py:40 select unchanged); flattening to bare strings happens only in the Pydantic `flatten_upcs` validator (models/common.py:13-25, wired at products.py:53-57 and recalls.py:113-117). provenance:637 independently flags this exact wording. The phrasing reads as if gold ships flat strings — misleading when reasoning about the raw containment-query shape (still object-array).
- **Recommendation:** Reword to attribute flattening to the API and note the gold shape, e.g. `"Gold stores them as [{\"upc\": ...}] objects; the API flattens to bare strings ([] when absent)."`

#### A7. `was_ever_retracted` documented as "ever marked inactive then reactivated" — name/semantics are about retraction, not a reactivation cycle — **LOW** — effort: trivial — **[FOLD INTO PROVENANCE APPLY]**
- **Where:** `documentation/api-reference.md:301`; field `models/recalls.py:105` (no code description).
- **What & why:** The field name means "was ever retracted" (ever absent from an enumerating run, provenance §3.64:858-866); the doc inverts it into a reactivation (inactive-then-active-again) predicate — a different predicate — and omits the USDA/NHTSA-only NULL. On the Q2 prune list (TODO.md:212).
- **Recommendation:** Prune alongside `is_currently_active`; if kept, reword to match the name and note the 3-of-5 NULL.

#### A8. A single opaque cursor param does two jobs (rank vs published_at) with no path tag — **LOW** — effort: small — **[STANDALONE]**
- **Where:** `routers/products.py:32-35,65-85`; `pagination.py:51-53,66-70`.
- **What & why:** This is the **redundant-features lens on the same mechanism as A1** (one param, two shapes, no discriminator; cross-path replay produces a 5xx instead of `BadCursor(400)`). Kept as a distinct entry only to record the "one param doing two jobs" design observation; **deduped into A1 for action** — fixing A1 (self-describing cursor / type-guard) resolves this. Do not double-count effort.

#### A9. `ProductSearchHit.upc` is projected and serialized null on every row of every source — **LOW** — effort: trivial/small — **[FOLD INTO PROVENANCE APPLY]**
- **Where:** `queries/products.py:33,56`; `models/products.py:32-34`. (Two source findings — `forward-compat-product-upc-column` and `product-upc-placeholder-2` — describe the **same column**; merged here.)
- **What & why:** `product_search.c.upc` is declared (products.py:33, comment "ALL-NULL today — never filtered"), selected into `_HIT_COLS` (products.py:56), and surfaced as `ProductSearchHit.upc` ("currently null for all rows"). Grep confirms `c.upc` appears only in the table literal and the projection — never in a predicate. The UPC *search* path (`_upc_where`, products.py:146-152) uses the different `recall_product_upcs` column via JSONB containment. Per provenance §3.39 (lines 574-579): `cast(null as text)` on every silver branch, `upc_pop=0` for all five sources, btree DROPPED 2026-06-15 — a forward-looking placeholder. So it serializes a guaranteed-null field on every product hit.
- **Recommendation:** Confirm with gold owners it is still 100% NULL (not verifiable from this repo). If population is not imminent, drop `c.upc` from `_HIT_COLS` and the model — the recall-level `recall_product_upcs` + `upc_is_recall_level=True` honesty flag already carry the UPC story. If imminent, leave and note the target gold release in the field description. The existing description ("currently null for all rows") is adequate if kept. Track with the Q2 prune.
- **Note:** Defensible documented forward-compat, not a bug — flagged as excess.

#### A10. `firm_count` and `firms[]` both documented as "firms linked to this recall" yet `len(firms)` can exceed `firm_count` — **LOW** — effort: trivial — **[STANDALONE]**
- **Where:** `api-reference.md:161` (firm_count) and `:297` (firms); model fields `models/recalls.py:36,99` (no descriptions).
- **What & why:** Identical "linked to this recall" framing, but `firm_count = count(distinct firm_id)` (provenance §3.23) while `firms[]` has one element per `(firm, role)` bridge row (§3.24), so a firm with two roles yields `len(firms) > firm_count`. A consumer would reasonably expect equality.
- **Recommendation:** Disambiguate in api-reference: `firm_count` = "distinct firms (a firm in multiple roles counts once)"; `firms` = "one entry per firm-role, so its length can exceed firm_count." (Divergence magnitude rests on gold lineage.)

#### A11. `reason_category` described as "null when the source provides none" — it is USDA-only, structurally null for 4 of 5 sources — **LOW** — effort: trivial — **[STANDALONE]**
- **Where:** `api-reference.md:158`; field `models/recalls.py:33,67` (no description).
- **What & why:** Per provenance §3.14 (lines 288-295) it is a USDA-FSIS taxonomy field, structurally NULL for CPSC/FDA/NHTSA/USCG (their reason is free text in `recall_reason`). "null when the source provides none" implies per-record sparsity rather than the actual 4-of-5-source structural NULL — could mislead a consumer into expecting CPSC/FDA recalls to carry a category.
- **Recommendation:** Clarify source scope: `"USDA-only FSIS reason taxonomy; null for CPSC/FDA/NHTSA/USCG, whose free-text reason lives in recall_reason."` (Source-scope specifics rest on cross-repo lineage; the misleading per-record framing is verifiable from the doc text.)

### Theme: Redundant features (Q2 prune projections)

#### A12. Pipeline-observability fields on RecallDetail are NULL for 3/5 sources and confusably named (Q2 prune) — **MEDIUM** — effort: medium — **[FOLD INTO PROVENANCE APPLY]**
- **Where:** `queries/recalls.py:50-55` (table literal) + `:77` (`_LIST_COLS`); `models/recalls.py:38,72,101-105`.
- **What & why:** RecallDetail projects six pipeline-internal fields that do not earn their place: `is_currently_active` / `was_ever_retracted` (presence-manifest, USDA+NHTSA only — see A3/A7); `first_seen_at` / `last_seen_at` (the cron's first/last **poll** timestamps; `last_seen_at` already ruled out as a "last edited" date at api-audit-notes.md:329 because it ticks every poll); `edit_count` / `edit_event_count` (two separately-lineaged detection counters with no model-level disambiguation, provenance §3.58/§3.60 "confusable sibling"). `edit_event_count` is **redundant with `has_been_edited`** (provenance §3.59: "equivalent to edit_event_count > 0") and additionally rides the **list** projection (`_LIST_COLS` recalls.py:77 → `RecallSummary.edit_event_count` models/recalls.py:38), so the noise ships on every list row too. TODO.md:201-222 already resolves to drop all six and keep only `has_been_edited`.
- **Recommendation:** Per TODO.md:222 keep `has_been_edited` as the single honest "changed since first ingest" flag; remove `is_currently_active`, `was_ever_retracted`, `first_seen_at`, `last_seen_at`, `edit_count` from RecallDetail and the table literal, and remove `edit_event_count` from **both** RecallDetail and the list projection (`_LIST_COLS` + `RecallSummary`). Regenerate `openapi.json` and update `data_contract.md` detail/list projection lists (lines 26, 34). The A3 and A7 doc fixes are subsumed by this removal.
- **Breaking-ness:** Removing fields from the response is a contract change for any consumer reading them; mitigated by these being newly-shipped, unreliable, and explicitly slated for removal. This is the anchor of the provenance apply.

---

## 2. Needs human judgment

These are genuine design calls, not clear defects. Record the trade-off; route to an owner rather than auto-fixing.

### H1. `_db_error_handler` maps any `DBAPIError`/`DataError` to 503 "database temporarily unavailable" — **MEDIUM**
- **Where:** `src/recalls_api/errors.py:102-110,146`.
- **Trade-off:** `register_error_handlers` wires `OperationalError`/`DBAPIError`/`SqlTimeoutError`/`OSError` all to a handler that unconditionally returns 503 + `Retry-After:5`. `DBAPIError` is broad — it wraps `DataError` (invalid input syntax), `CheckViolation`, etc., which are **client-value** failures, not an unavailable DB. The concrete harmful instance is the A1 reverse direction: a client cursor produces a numeric-parse `DataError` reported as a transient outage with `Retry-After`, telling the caller to retry a deterministically-failing request. The intent (cold/asleep Neon → 503) is sound and **deliberate** (comment errors.py:143-145) for `OperationalError`/timeout/`OSError`; folding the entire `DBAPIError` tree into "upstream unavailable" is the coarseness. **Decision needed:** narrow the `DBAPIError` branch (connection/timeout classes → 503; `DataError`/`ProgrammingError` → 500 or raised as `BadCursor` upstream), at minimum stop advertising `Retry-After` on deterministic 4xx-class failures — vs. accept the coarse mapping as good-enough for a personal read-only API. The only cited harm depends on the A1 reverse direction surfacing as `DBAPIError`, which is itself runtime-uncertain. Fixing A1 (guard at the seek boundary) removes the concrete instance regardless of this decision.

### H2. Product FTS rank omits the `ts_rank_cd` weight vector that recall FTS uses — **LOW**
- **Where:** `queries/products.py:102` vs `queries/recalls.py:208,220` (`_RANK_WEIGHTS = '{0.1,0.2,0.4,1.0}'`).
- **Trade-off:** Recall search weights title above narrative via the explicit weight vector; product search calls `ts_rank_cd(_search_vector, tq)` with **no** weight vector (Postgres defaults). Both endpoints surface a `rank` field described as "ranked by relevance," so the two relevance scales differ silently and undocumented. Whether this is a bug depends on whether `mart_product_search.search_vector` uses `setweight` buckets — **not knowable from this repo** (mart is upstream). If unweighted, the missing vector is a no-op and this is purely a doc gap; if weighted, it is a real relevance inconsistency. **Decision needed:** confirm the mart's vector; either apply the same weight vector for parity, or add a one-line comment at products.py:102 stating the product tsvector is unweighted and note the scale difference in the description.

### H3. Date-boundary (whole-day-inclusive) semantics asserted at both unit and integration tiers — **LOW**
- **Where:** `tests/test_queries_recalls.py:71-84,127-136` and `tests/integration/test_recalls.py:79-114`.
- **Trade-off:** The "+1-day exclusive" boundary math is pinned at the unit tier (bound-param asserts) **and** re-derived end-to-end at integration for `published_before`, `announced_before`, `announced_after`. Factually duplicated — but this is a standard test-pyramid split (unit pins the math, integration pins the wiring), and the finding concedes the integration test "still earns its keep as a does-the-filter-wire-through smoke test." **Decision needed:** keep both (belt-and-suspenders) or demote the integration date cases to a single smoke pair so the boundary convention lives in one place. Not a defect.

### H4. Pervasive exact set-equality on the 6 seeded recall ids couples filter tests to the fixture inventory — **LOW**
- **Where:** `tests/integration/test_recalls.py:10,18,253` (+ many filter tests).
- **Trade-off:** `_ALL_IDS` and `assert {...} == {literal ids}` checks are exact set-equality against the precise 6 seeded recalls. Adding any new seeded recall breaks the census tests and every filter test it newly matches — the seed is effectively frozen. This is the well-understood small-cassette trade-off (the finding says so). **Decision needed:** keep exact-set equality only for the two census tests (list-all, pagination-walk) and switch filter tests to subset/containment assertions tied to intent, so the seed can grow without a cascade of unrelated edits — vs. accept the coupling for a fixed cassette.

> Also adjacent: the compile-only operator-substring assertions (`'ILIKE'`/`'&&'`/`'@>'` in SQL text, test_queries_recalls.py:88,149 and test_queries_products.py:51) are brittle restatements of the builder's SQL spelling whose semantics are already covered at integration. This was verified as **needs-human-judgment** (the unit/integration split is a legitimate intentional choice; the bound-param half of those asserts retains unique value). Covered in §4 below.

---

## 3. Tests: redundancy & gaps

### Over-coverage (remove / simplify)

| Item | Where | Action |
|---|---|---|
| Tautological rank-ordering assert | test_recalls.py:184 | Drop `items[0]["rank"] >= items[1]["rank"]` — the query orders `rank.desc()` (queries/recalls.py:226), so it holds by construction and can never fail; it tests SQLAlchemy's ORDER BY, not `_RANK_WEIGHTS`. The load-bearing assertion (`ids[0]=="24-003"`, line 183) depends on the seed's hand-written `setweight` vector (seed_gold.sql:131-144), not app code. **Confirmed, effort small.** |
| Compile-only operator-substring asserts | test_queries_recalls.py:88,149; test_queries_products.py:51 | Soften: keep the bound-param asserts (pin contract), drop the raw-operator substring checks (`'ILIKE'`/`'&&'`/`'@>'`) — integration already proves the semantics (test_recalls.py:141-147, 73-76; test_products.py:31-36,57-61) and these only lock the current SQL spelling. **needs-human-judgment** (legit intentional belt). |
| Date-boundary double-coverage | see H3 | **needs-human-judgment** — intentional pyramid layering. |
| Seed-coupled set-equality | see H4 | **needs-human-judgment** — small-cassette trade-off. |

### Gaps (add)

| Item | Severity | Where | Action |
|---|---|---|---|
| `_db_error_handler` never reached through the app stack | **MEDIUM** | errors.py:102; test_db.py:79-88 only asserts handlers are *registered* | **Highest-value operational gap.** The cold-Neon resilience contract (a request to a cold DB must be 503, not 500, no SQL leak) is wholly unexercised. Add a test overriding `get_conn` to raise `OperationalError` asserting 503 + upstream-unavailable envelope + `Retry-After`, no SQL in body. **Confirmed, effort small.** |
| Products search has zero cursor/keyset coverage; cross-path replay → 5xx not 400 | **MEDIUM** | routers/products.py:65-86; pagination.py:66-82; test_products.py (no `cursor`) | `test_products.py` has no cursor/`next_cursor` assertion and the fixture is too small (max 2 rows at limit 50) to mint one. Seed enough products to force a `next_cursor`, add keyset walks for both the rank and published_at paths, and add the cross-path replay test asserting 400 — **this is the test counterpart of A1** and will require the A1 guard to make it pass. **Confirmed, effort medium.** Deduped with A1. |
| No system/end-to-end tier | **LOW** | conftest.py:73-75 (every client overrides `get_conn` + `ASGITransport`) | The real boot path (`db.open_pool`/`get_conn`/`close_pool`, lifespan, read-only-posture boot assertion) is **never executed by any tier** with a real pool — only against `MagicMock` engines in test_db.py:54-76. On a bare machine integration also SKIPs (conftest.py:32-40). **A true system/e2e tier is missing.** Add a thin non-overridden-pool smoke tier (testcontainer pool through the real lifespan hitting `/health`, `/health/db`, one data endpoint) + an opt-in env-gated live smoke against the deployed base URL. **Confirmed, effort medium.** Down-rated to low: boot/posture logic *is* mock-unit-tested, so not zero-covered; only the wired-together real-pool path is uncovered. |
| `GET /health/db` never requested by any test | **LOW** | health.py:24-33; test_openapi.py:24 (only its path-list presence) | Neither 200 (`db.healthcheck` SELECT 1) nor the 503 cold-DB path is exercised; `db.healthcheck` (db.py:102) has no test caller. Add a 200 integration test + a 503 case (monkeypatch healthcheck to raise `OperationalError`). **Confirmed, effort small.** |
| Rate limiting (429) has no end-to-end test though enabled by default | **LOW** | settings.py:45; main.py:69-76; test_errors.py:69 | Only `rate_limited_response()` is unit-tested in isolation. The whole request-time limiter path (slowapi middleware, `_on_rate_limited`, `/health` exemption) is unexercised. Add an integration test with a tight limit firing N+1 requests at `/recalls` asserting 429 + envelope + `Retry-After`, plus `/health` stays exempt. **Confirmed, effort small.** |
| `RequestIdMiddleware` behavior not directly tested | **LOW** | logging.py:84; test_ops.py:28 (only CORS expose-headers list) | No test asserts `X-Request-ID` is present on a response, that a generated id is echoed, that an inbound id is honored, or that the request log line binds it. Add an integration test for present/echoed/honored. **Confirmed, effort small.** |
| OpenAPI contract test omits `/recalls/search` + `RecallSearchHit` | **LOW** | test_openapi.py:18-29 | The surface guard's paths/schemas loops don't list `/recalls/search` or `RecallSearchHit`, so the cross-repo consumer contract would not catch their accidental removal (the snapshot test only catches drift if the spec is regenerated+committed). Add both to the loops. **Confirmed, effort trivial.** |
| `RecallSearchHit` model has no unit test | **LOW** | models/recalls.py:42; test_models_recalls.py | The rank-bearing subclass returned by `/recalls/search` is only touched indirectly via integration. Add a `model_validate` test asserting `rank` is required/typed and inherited coercions still apply. **Confirmed, effort trivial.** |
| USCG-only firm sidecar + `firm_id` regex boundaries uncovered | **LOW** | test_firms.py; seed_gold.sql:261; firms.py:42 (`^[0-9a-f]{32}$`) | The seeded USCG-only firm (Boaty Mfg, id `55555…`) is never fetched, so `firm_uscg_attributes` parse has no end-to-end assertion; the regex is tested for one malformed id but not 31/33-char or uppercase-hex boundaries. Add a USCG-firm fetch test + boundary 422 cases. **Confirmed, effort small.** Risk small (sidecar path structurally identical to covered FDA/USDA). |
| `export_openapi.main()` CLI (`--check` exit-1 + write path) untested | **LOW** | export_openapi.py:35; test_openapi.py | The drift-gate CLI has no test; only `generate()`/`render()` are exercised via the snapshot. A regression in the exit code would silently break the drift gate. Add `main(['--check'])` tests (exit 0 on current, non-zero on mutated) + a write-path test. **Confirmed, effort small.** Backstopped by the snapshot test for content; only exit-code plumbing is uncovered. |

**Is a true end-to-end tier missing?** Yes. Every HTTP test runs in-process via `ASGITransport` with `get_conn` overridden; nothing boots a real pool through the real lifespan, and nothing hits the deployed surface. See the system/e2e gap above.

---

## 4. Rejected (false positives)

Recorded so they are not re-raised.

### R1. "Per-product `upc==None` asserted redundantly across integration tests" — **REJECTED**
- **Where claimed:** test_products.py:36,57-61.
- **Why rejected:** The headline claim is false. `hit["upc"] is None` appears **exactly once** in the whole `tests/` tree (only test_products.py:36). The two cited tests assert **different** fields: `test_upc_recall_level_containment` (31-36) asserts `upc_is_recall_level is True` (35) + per-product `upc is None` (36); `test_upc_object_shape_containment_matches` (57-61) asserts the flatten regression `recall_product_upcs == ['012345678905']` (61). They do not both "re-assert the recall-level flatten." The only shared assertion is the incidental `{rp-001}` set-membership (lines 34, 60), which is normal per-test setup. The redundancy described does not exist. Do not merge these tests on this basis.

---

## 5. Dispositions

| # | Finding | Severity | Disposition |
|---|---|---|---|
| A1 | Cross-path cursor replay → 5xx not 400 (ADR 0004) | HIGH | **Standalone PR** — self-describing/typed cursor guard + regression test. Closes A8 and the test-gap "products cross-path replay" (T6/T7). |
| A12 | RecallDetail pipeline-observability fields (Q2 prune) | MEDIUM | **Provenance apply** — anchor of the apply. Subsumes A3, A7 (their doc fixes are mooted by removal). |
| A3 | `is_currently_active` doc wrong + confusable with `is_active` | MEDIUM | **Provenance apply** — removed by A12; doc fix only if deferred. |
| A5 | `page_limit_default` dead config / config trap | MEDIUM | **Standalone PR** — wire-or-delete; pick one. |
| A2 | `firm=` served description omits primary-only scope | MEDIUM | **Standalone PR** — one-line description fix + regen `openapi.json`. |
| A6 | "flattened from gold's object array" misattribution | LOW | **Standalone PR** (description text) or fold into A12 doc pass. |
| A7 | `was_ever_retracted` doc inverts the name | LOW | **Provenance apply** — removed by A12. |
| A8 | One cursor param, two jobs (rank vs published_at) | LOW | **Deduped into A1** — no separate work. |
| A9 | `ProductSearchHit.upc` permanently-null projection | LOW | **Provenance apply** (drop) — pending gold-owner confirm it's still 100% NULL; else defer with a noted gold target. |
| A10 | `firm_count` vs `len(firms)` identical doc framing | LOW | **Standalone PR** (api-reference disambiguation). |
| A11 | `reason_category` "source provides none" framing | LOW | **Standalone PR** (api-reference source-scope clarification). |
| T-tautology | Tautological `rank >= rank` assert | LOW | **Standalone PR** (test cleanup) — bundle with the test-gap PR. |
| T-db-503 | `_db_error_handler` never reached via HTTP | MEDIUM | **Standalone PR** — add 503/opacity test. Highest-value operational gap. |
| T-products-cursor | Products cursor/keyset + cross-path coverage | MEDIUM | **Bundle with A1** — the test that forces A1's fix. |
| T-e2e | No system/e2e tier | LOW | **Defer** (effort medium; design call) — add thin smoke tier when capacity allows. |
| T-health-db | `/health/db` untested | LOW | **Standalone PR** (small). |
| T-429 | Rate-limit 429 untested | LOW | **Standalone PR** (small). |
| T-reqid | `RequestIdMiddleware` untested | LOW | **Standalone PR** (small). |
| T-openapi-surface | Contract omits `/recalls/search` + `RecallSearchHit` | LOW | **Standalone PR** (trivial) — bundle with test cleanup. |
| T-searchhit | `RecallSearchHit` model unit test | LOW | **Standalone PR** (trivial) — bundle with test cleanup. |
| T-uscg-firm | USCG sidecar + `firm_id` boundaries | LOW | **Standalone PR** (small). |
| T-export-cli | `export_openapi.main()` CLI untested | LOW | **Standalone PR** (small). |
| H1 | `_db_error_handler` over-catches `DBAPIError` → 503 | MEDIUM | **Human judgment** — taxonomy/design trade-off; A1's guard removes the concrete instance regardless. |
| H2 | Product FTS rank missing weight vector | LOW | **Human judgment** — needs upstream mart confirmation before code vs doc fix. |
| H3 | Date-boundary double-coverage | LOW | **Human judgment** — keep or demote; not a defect. |
| H4 | Seed-coupled set-equality (+ operator-substring asserts) | LOW | **Human judgment** — small-cassette trade-off; not a defect. |
| R1 | "upc==None asserted twice" | — | **Rejected** — do not re-raise. |

**Suggested bundling:** one **Provenance apply** PR (A12 anchor; absorbs A3, A7, A9, and the A6 doc pass + `openapi.json`/`data_contract.md` regen); one **cursor robustness** PR (A1, absorbing A8 and the products cross-path test); one **doc/description** PR (A2, A10, A11); one **dead-config** PR (A5); and one **test hygiene** PR (the tautology drop + all the trivial/small test-gap additions, with the e2e tier and the H3/H4 test-shape decisions deferred to owner judgment).
