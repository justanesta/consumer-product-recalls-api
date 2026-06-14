# Gold-marts audit — charter, API data-surface decisions, and where to run it

This doc does three things: (A) records my recommendation on **where** to run the full gold-marts
audit, (B) captures the **API data-surface decisions** from our discussion (the input that audit
consumes), and (C) lists the **open questions** the audit must answer. It is the "succinct workstream
seed" referenced in our conversation.

## A. Where to run the audit — recommendation: **in the `consumer-product-recalls` repo, not here**

Run the deep audit there; have it emit a short workstream doc that comes back here to drive API PRs.
Four reasons:

1. **Source of truth + branch correctness.** The audit must read the dbt model SQL at the *pinned
   authoritative commit* (`feature/pre-go-live-validation`). That's clean in that repo; from here it
   means reasoning over a possibly-stale/foreign checkout and another repo's git state.
2. **Ground-truth coverage is the whole point.** The single most valuable output is **per-field,
   per-source population / null rates + enum domains** — and that needs *querying the live gold marts*.
   That repo holds DB access in its own security context. Static doc-reading (all this repo can do
   without secrets) infers *structure* but not *coverage* — and coverage is exactly what separates a
   good param from a silent-empty trap (the `is_active` / USDA-only lesson).
3. **Ownership.** By this project's own rule, "this repo owns no schema." Schema-change proposals are
   pipeline-repo work; gold-readiness is already tracked there
   (`serving-layer-gold-readiness-plan.md`).
4. **Context.** That repo has the dbt models, ADRs, conventions, and dbt-aware tooling.

**What runs here vs there:**
- **Here (done in this doc):** the API's product-driven wishlist + param decisions = the audit's input.
- **There:** the audit workflow (fan-out one agent per gold object × the dimensions in §C), optionally
  querying for coverage → emits a workstream doc.
- **Back here:** that doc drives the API changes (new predicates, new endpoints).

**Is it a good "dynamic workflow"?** Yes — per-mart fan-out + a synthesis stage is a textbook fit. But
it should run in the pipeline repo's session (opt-in there), not here. I can hand you a ready-to-paste
workflow script as an artifact to carry over — ask and I'll draft it.

## B. API data-surface decisions (from this conversation)

Coverage facts confirmed against `01-ground-truth-gold-marts.md`. "Return" = include in responses
(many already are). "Filter" = expose as a `/recalls` query param. API-only changes are one predicate
each; array filters and the search vector need **gold** support (GIN / tsvector).

| Field | Return? | Filter? | Verdict & rationale | Needs gold? |
|---|---|---|---|---|
| `distribution_scope` | already | **YES** | NOT NULL, 4-value enum → ideal param (always populated, bounded). | No |
| `lifecycle_status` | already | **YES** | Populated for FDA/USDA/USCG; NULL for CPSC/NHTSA. Add with the same "null matches neither" caveat as `is_active`. Confirm value domain in audit. | No |
| `distribution_state_codes` | already (detail) | **YES (containment)** | text[], **FDA/USDA only**. Filter = `:code = ANY(...)` / array overlap. | **Yes — GIN** for perf |
| `distribution_country_codes` | already (detail) | **YES (containment)** | text[], **foreign-only — `US` is EXCLUDED by design**. Loud caveat: `?country=US` returns nothing; this filter means "distributed to <foreign country>". | **Yes — GIN** |
| `announced_at` | **add to summary** | **YES (date range)** | Mirror `published_at` (`announced_after`/`announced_before`). Nullable (~20 FDA rows) → range excludes nulls; document. Useful for recall *age*. | No |
| `source_recall_id` | already | **optional, exact-only** | See verdict below. | No |
| `risk_level` | already | **NO** | **USDA-only** (confirmed). A param would silently return nothing for 4/5 sources — same trap as `is_active`. Keep returning; don't filter. | — |
| `reason_category` | already | **NO** | **USDA-only** raw FSIS string (confirmed). Same trap. Keep returning; don't filter. | — |

### `source_recall_id` as a filter — verdict: **return = yes (already); filter = optional, exact-match only**
It's the human-facing agency recall number (CPSC `24-001`, NHTSA `24V123`, FDA `F-####-YYYY`, …).
- **Returning it is clearly good** — it's already in `RecallSummary`/`RecallDetail`. Keep it.
- **As a filter it's modest value and partly redundant:** canonical single-record access is already
  `GET /recalls/{source}/{recall_id}` (a point read on `UNIQUE(recall_event_id)`). The one real
  use case a list-filter adds is *"I have a recall number but don't know / don't want to specify the
  agency"* → `?source_recall_id=24V123` returns the 1–few matches across sources.
- **If added: exact-match only** (no partial/prefix → avoids seq-scan abuse; result set is tiny and
  selective, like the existing `firm` substring filter). Document that it is **not a globally unique
  key** (uniqueness is only guaranteed *with* `source`) and steer single-record fetches to the detail
  route. **Recommendation:** low priority; add it only if the "number without agency" lookup is a real
  user need (a future `/recalls/search` largely covers the same intent more flexibly).

### Net API work implied (separate from `/recalls/search`)
- API-only, cheap: `distribution_scope`, `lifecycle_status`, `announced_after`/`announced_before`,
  (optional) `source_recall_id` exact — add a `Query` param to `deps.recall_filters` + a predicate to
  `recalls_predicates`. Add `announced_at` to `RecallSummary`.
- Cross-repo: `distribution_state_codes` / `distribution_country_codes` filters want **GIN indexes**
  (gold) to be index-backed; the predicate itself is API-side.

## C. Audit scope (what the pipeline-repo audit should produce)

For **every gold mart/view** (`mart_recall_summary`, `mart_product_search`, `mart_firm_profile`,
`fct_recalls_by_firm`, plus any other gold object), per column:

- type, nullability (declared vs actual), **per-source population / null-rate**, enum/domain &
  cardinality, index coverage, stability across nightly rebuilds, and whether it's derivable/redundant.
- Per mart: **what's not surfaced today that's interesting** to an endpoint; **what's single-source**
  (param-trap candidates); **which arrays/text need GIN/FTS** to be filterable/searchable;
  **what new endpoints** the data could justify (e.g. `/firms` list/search, `/recalls/search`,
  facet/aggregate endpoints).
- Cross-cutting: enum domains that should be documented (`distribution_scope`, `lifecycle_status`,
  `classification` per source), and any column whose name/semantics mislead (the kind of thing R5 fixed).

### Open questions the audit must answer
- `lifecycle_status`: exact value domain, and per-source coverage (is it really FDA/USDA/USCG only?).
- `classification`: the per-source value sets (FDA Class I/II/III vs others) — to document, not unify.
- `distribution_scope`: the 4 enum values, verbatim.
- Array geo columns: real null-vs-`{}` rates per source; confirm `US`-exclusion in
  `distribution_country_codes`.
- `announced_at`: actual null rate per source (doc says ~20 FDA NULL — verify).
- Anything in `mart_firm_profile` worth a `/firms` *list/search* endpoint (today it's point-read only).

## Sequencing
1. `/recalls/search` (Option B) — already specced (`recalls-search-*-plan.md`); proceed now.
2. The cheap API-only filters (§B) — can ship independently of the audit; they're confirmed safe.
3. The full audit (this charter) — run in the pipeline repo → workstream doc → larger API surface
   (array filters + GIN, possible new endpoints).
