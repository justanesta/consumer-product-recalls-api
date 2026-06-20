# Handover: API-docs work — UPC-search discoverability + USCG severity caveat (2026-06-20)

**Branch (this repo):** `feature/announce-date-and-usda-uscg-firm-model-sync`. **In scope for this
branch.** This is the docs/description companion to the two other items already staged on it:
- `handover-usda-uscg-firm-sidecar-500-2026-06-20.md` (the `/firms/{id}` 500 fix), and
- `handover-announce-date-timeseries-2026-06-20.md` (the announce-date basis).

All three ship and **redeploy together**; the website does **one** `npm run gen:api` re-sync afterward
(see "Drift-gate coupling" below). Raised by the website repo's pre-deployment audit.

## TL;DR

Two **description-only** changes to the OpenAPI spec (no schema/behavior change):

1. **UPC search is undiscoverable in the rendered `/api` docs.** The capability exists
   (`GET /products/search?upc=…`) but the param has a one-line description and nothing at the top of the
   docs points to it, so the site owner "can't find how to search by a UPC." → Enrich the `upc` param
   description (+ example) and add a "common lookups" pointer to the app-level description.
2. **USCG `H/L/M/S` severity codes are passed through with no caveat**, but their official meaning is
   **undocumented** (see evidence below). → Add an "unverified semantics, provisional ordering" caveat to
   the `classification` field description(s), mirroring the tone already used on `UscgManufacturer.status`.

Both are honesty/discoverability fixes, not bugs. The website ships matching front-end behavior already
(a UPC search field; a provisional USCG ordering with a "pending USCG confirmation" note + a
`/methodology` caveat the site adds separately).

---

## Workstream A — UPC search discoverability

### Why
`/api` renders the deployed `openapi.json` via Scalar. UPC lookup works
(`GET /products/search?upc=012345678905` → recall-level containment), but in the rendered docs it's
buried: the `upc` query param reads only *"UPC — matched recall-level via containment."* and the docs
landing doesn't tell a reader "to look up a barcode, use this endpoint." Result: a real user (the site
owner) couldn't find it. The website already exposes a UPC field that calls this endpoint; we just need
the docs to advertise it.

### How (exact edits)
1. **Enrich the `upc` query-param description** — `src/recalls_api/routers/products.py:54-55`.
   Current: `Query(max_length=32, description="UPC — matched recall-level via containment.")`.
   Suggested: plain-language + scope + example, and add `examples=`:
   > "Look up recalled products by 12-digit UPC barcode. Matched at the RECALL level via array
   > containment — CPSC-sourced and sparse (~5% of CPSC recalls; empty for FDA/USDA/NHTSA/USCG). A miss
   > means no recall lists that UPC, **not** that the product is safe."
   …and `examples=["012345678905"]` so Scalar shows a ready-to-run value.
2. **Add a discoverable "common lookups" pointer to the app description** — `_DESCRIPTION`,
   `src/recalls_api/main.py:31-36` (renders at the top of the Scalar page; Scalar renders markdown).
   Append something like:
   > "**Common lookups:** by product name → `GET /products/search?q=`; by **UPC barcode** →
   > `GET /products/search?upc=`; vehicle/boat by identifier → `?model=` / `?hin=`; one recall →
   > `GET /recalls/{source}/{recall_id}`."
3. **(Optional) Cross-link from recall search** — `src/recalls_api/routers/recalls.py:46` already
   contrasts `/recalls/search` with `/products/search`; add "(including UPC lookup via `?upc=`)" so the
   pointer exists on both endpoints.

### Open questions
- Want a short **"Recipes"** block in `_DESCRIPTION` (3-4 canonical `curl`s)? Scalar renders the markdown;
  it's the highest-leverage discoverability win but is editorial — confirm tone/length.
- Add `openapi_examples` on the `/products/search` operation (named example "by UPC")? Nice-to-have.

---

## Workstream B — USCG `H/L/M/S` severity caveat

### Why
The `classification` field enumerates "USCG: H/L/M/S", but **the meaning of those codes is not publicly
documented** and the descriptions present them with no caveat — implying a known, ordered scale. Evidence
gathered during the website audit (2026-06-20):
- The public USCG recall index (`uscgboating.org/content/recalls.php`) exposes **no severity column** at
  all (Number, MIC, Company, Model, Problem, Opened-On only).
- **33 CFR 179** (the recall regulation) defines the trigger as "substantial risk of personal injury" but
  **no H/L/M/S taxonomy**.
- The only third-party scrape (`m-nolan/USCG_Boat_Recalls`) just *assumed* L/M/H = Low/Med/High and was
  explicitly unsure about `S`.
- This repo's own data side flagged it: the pipeline field audit notes *"enum meanings undocumented —
  email USCG OII"* (distribution H 38% / L 35% / M 1.4% / S 0.1%).

The site owner has an email out to USCG to confirm; until then the **website ships a provisional reading**
(H/M/L ≈ High/Medium/Low colored red/amber/green; `S` last, neutral, with a "meaning unconfirmed — pending
USCG" note) and is adding the same caveat to `/methodology`. The **API descriptions should carry the same
honesty caveat** so programmatic consumers don't treat H/L/M/S as a confirmed ordered scale.

### How (exact edits)
1. **`_D_CLASSIFICATION`** — `src/recalls_api/models/recalls.py:50-54` (the canonical constant; used by
   `RecallSummary` + `RecallDetail`). Append, e.g.:
   > "⚠ USCG's H/L/M/S are passed through verbatim from the USCG directory; their official severity
   > semantics are **not publicly documented** (the public USCG recall index exposes no severity; 33 CFR
   > 179 defines none) — do **not** assume an ordered scale. Provisional working assumption (pending USCG
   > confirmation): H/M/L ≈ High/Medium/Low; `S` unverified."
   This matches the tone already used on `UscgManufacturer.status` (`models/firms.py:59-68`).
2. **Keep the parallel copies consistent** — the same "USCG: H/L/M/S" sentence is **duplicated** in:
   - `src/recalls_api/models/products.py:111-115` (`ProductSearchHit.classification`)
   - `src/recalls_api/models/stats.py:94-98` (`ClassificationCount.classification`)
   Update both, **or** (preferred) centralize: import one shared constant so the caveat can't drift across
   the three model modules (see open question).

### Open questions
- **Centralize the classification description?** It's currently the same sentence in 3 modules
  (`recalls.py`, `products.py`, `stats.py`). Recommend hoisting `_D_CLASSIFICATION` to a shared
  descriptions module and importing it, so this caveat (and future edits) live in one place. Confirm you
  want that small refactor in this branch vs. just editing all three inline.
- **`risk_level`** (USDA-only, `_D_RISK_LEVEL`) needs **no** change — it's well-defined. Caveat is
  USCG-specific.
- Machine-readable signal? A description caveat is sufficient for now; an explicit
  "uscg_classification_unconfirmed" flag would be over-engineering — flagging in case product disagrees.

---

## Drift-gate coupling (why batch all three, and what the site must do after)

Editing **any** description string changes `openapi.json` (descriptions live in the spec). The website
repo (`consumer-product-recalls-site`) commits a pinned `openapi.json` + generated `schema.d.ts` and its
CI **fails on drift** vs. the deployed spec. So:
- **Batch** Workstreams A + B with the firm-sidecar 500 fix and deploy **once** (this branch).
- After deploy, the site re-runs `npm run gen:api` and commits the refreshed `openapi.json` /
  `schema.d.ts` **one time** — clearing the gate. (The site owner / its Claude instance handles that;
  it's already flagged on the website side.)
- None of these change wire **types**, only descriptions (+ one `examples=`), so there's no breaking
  client change — the site's typed client is unaffected beyond the regenerated doc comments.

## Verify (definition of done)
- `/api` (Scalar) shows a top-of-page "common lookups" pointer including `?upc=`, and the `upc` param
  reads in plain language with an example.
- The `classification` field description (recalls, products, stats) carries the USCG caveat.
- `openapi.json` regenerates cleanly; existing API tests pass (these are description-only, so behavior
  tests are unaffected — but `export_openapi` / any snapshot of the spec must be refreshed).
- Hand back to the website: it regenerates `schema.d.ts`, and the site adds the matching `/methodology`
  USCG note + any `/api`-page intro copy.

## References
- UPC: `routers/products.py:24-27` (endpoint desc), `:54-55` (`upc` param), `main.py:31-36`
  (`_DESCRIPTION`), `routers/recalls.py:46` (cross-link), `queries/products.py:146-161` (containment impl).
- USCG severity: `models/recalls.py:50-54` (`_D_CLASSIFICATION`), `models/products.py:111-115`,
  `models/stats.py:94-98`; tone exemplar `models/firms.py:59-68` (`UscgManufacturer.status`).
- Companions on this branch: `handover-usda-uscg-firm-sidecar-500-2026-06-20.md`,
  `handover-announce-date-timeseries-2026-06-20.md`.
