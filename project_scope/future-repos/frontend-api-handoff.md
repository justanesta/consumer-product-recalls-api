# Frontend ← API Handoff (consumer-product-recalls-api)

**Date:** 2026-06-19 · **From:** `consumer-product-recalls-api` (`feature/api-audit`) · **To:** the future website repo (Cloudflare Pages, Astro).

This is the **API-consumption** companion to the pipeline repo's `project_scope/future-repos/website-frontend-plan.md` (framework/architecture plan) and to this repo's `documentation/frontend-api-docs-handoff.md` (how to render the public **API-docs page** with Starlight/Scalar). This doc owns the **how-the-site-actually-talks-to-the-API** layer: the live contract, the data-fetch model, every operational quirk, and the **Cloudflare + Fly.io custom-domain runbook**.

> **Read §13 first if you've read the website plan.** Several of that plan's API specifics are stale or ahead of what's built — wrong filter param names, a `/stats/*` + `fct_*` dashboard family that **does not exist yet**, a `?firm_id=` recalls filter that doesn't exist, FDA `Class I/II/III` (now `1/2/3/NC`), and lifecycle/edit fields that were pruned. §3 is the authoritative current contract; §13 reconciles the two.

---

## 1. Architecture — how the site gets data

```
Browser / build step ──HTTPS GET──> FastAPI (Fly.io) ──asyncpg, read-only──> Neon Postgres gold marts
   (the website)                     consumer-product-recalls-api            mart_recall_summary / _product_search / _firm_profile
```

- The website **never touches Postgres**. It only makes **HTTPS `GET`** requests to the API and renders the JSON. The API holds a SELECT-only `recalls_readonly` role; there is no write path to expose.
- **Two-speed access (the website plan's hybrid lever), reconciled to reality:**
  - **Per-entity + search** (recalls browser, recall detail, firm profile, product search) → **fetch live** from the API. These endpoints **exist today** and are fully buildable now (§3).
  - **Aggregates / dashboards** (`/stats/*` over `fct_*`) → the plan wants a **build-time pull**, but **those endpoints are not built** (§13). Until they are, the dashboards page is blocked — either add the `/stats/*` API surface, or have the *pipeline* export `fct_*` to static JSON for a build-time bake. The website still never queries PG directly.
- **All responses are JSON**, `GET`-only, no auth, no content negotiation (send `Accept: application/json` or omit it).

---

## 2. Base URLs

| Use | URL |
|---|---|
| **Current (live)** | `https://consumer-product-recalls-api.fly.dev` |
| **Planned API custom domain** | `https://api.consumer-product-recalls.info` (set up in §14C) |
| **Website (planned)** | `https://consumer-product-recalls.info` (Cloudflare Pages, §14B) |
| OpenAPI spec | `<base>/openapi.json` |
| Interactive docs | `<base>/docs` (Swagger UI) · `<base>/redoc` (ReDoc) |

Expose the base URL to the site via a single env var (Astro convention `PUBLIC_API_URL`); never hard-code it in components. Build-time fetches and runtime islands both read it.

---

## 3. The endpoint contract (authoritative — current)

Seven endpoints. The machine-readable source of truth is `openapi.json`; **generate the TS client from it** (§12), don't hand-type these. This table is the human map.

### 3.1 `GET /recalls` — list recalls → `Page<RecallSummary>`

Newest-first (`published_at DESC, recall_event_id ASC`), keyset-paginated. **All filters optional; different filters AND together.** Six categorical filters are **multi-value** (any-of OR within the field): repeat the param (`?source=CPSC&source=FDA`) **or** comma-separate (`?source=CPSC,FDA`) — equivalent.

| Param | Type | Multi | Notes |
|---|---|:--:|---|
| `source` | enum `CPSC\|FDA\|USDA\|NHTSA\|USCG` | ✓ | uppercase; unknown → 422 |
| `classification` | string (≤64) | ✓ | **source-native, exact** (FDA `1/2/3/NC`, USDA `Class I/II/III`+`Public Health Alert`, USCG `H/L/M/S`); meaningful only with `source` |
| `is_active` | bool | – | **tri-state**: CPSC/NHTSA are `null` and match **neither** `true` nor `false` |
| `lifecycle_status` | string (≤64) | ✓ | source-native; `null` for CPSC/NHTSA |
| `distribution_scope` | enum `Nationwide\|Regional\|Unspecified\|International` | ✓ | always present in data |
| `distribution_state` | USPS 2-letter | ✓ | array-overlap; **FDA/USDA only** |
| `distribution_country` | ISO alpha-2 | ✓ | foreign-only (`US` excluded); **FDA in practice** |
| `source_recall_id` | string | – | exact; unique only **with** `source` |
| `firm` | string (2–200) | – | **substring on `primary_firm_name` only** — NOT a firm id, NOT secondary firms |
| `published_after` / `published_before` | `YYYY-MM-DD` | – | whole-day inclusive |
| `announced_after` / `announced_before` | `YYYY-MM-DD` | – | nulls excluded (announced_at is nullable) |
| `limit` | int 1–100 (default 25) | – | page size |
| `cursor` | opaque string | – | from a prior `next_cursor` (§4) |
| `with_total` | bool (default false) | – | adds an extra `COUNT(*)` → `Page.total` |

### 3.2 `GET /recalls/search` — recall keyword search → `Page<RecallSearchHit>`

`RecallSummary` + a `rank: float`. **Requires `q`** (2–200 chars, Postgres `websearch_to_tsquery` — phrases `"…"`, negation `-…`; **no fuzzy/typo**). All `/recalls` filters apply. Ordered by `rank DESC`. (The website plan only used product search — this recall-grain search is available too.)

### 3.3 `GET /recalls/{source}/{recall_id}` — one recall → `RecallDetail`

The full wide row (summary fields + narrative + geo arrays + `firms`/`product_names`/`models`/`hins`/`product_upcs` rollups). `source` is **case-insensitive** in the path (`cpsc`/`CPSC` both work). `recall_id` is the agency-native id. 404 if not found.

### 3.4 `GET /products/search` — product search → `Page<ProductSearchHit>`

**At least one of `q` / `hin` / `model` / `upc` is required** (else 422). Precedence: `q` > (`hin` and/or `model`) > `upc`. `source` (multi) AND-s with the selector.
- `q` (2–200): FTS over product name/description/recall title/firm name; sorted by relevance.
- `hin` / `model` (exact, btree): sorted `published_at DESC`.
- `upc`: matched at the **recall level** via JSONB containment over `recall_product_upcs` (CPSC-sourced, sparse). There is **no per-product `upc` field** in the response (dropped — §13).

### 3.5 `GET /firms/{firm_id}` — firm profile → `FirmProfile`

`firm_id` is an opaque **32-hex md5** (`^[0-9a-f]{32}$`) — **a bad shape is 422 before the DB**, an unknown valid id is 404. Obtain it only from a `RecallDetail.firms[].firm_id`. Includes the three per-source sidecars (`firm_usda_attributes` / `firm_uscg_attributes` / `firm_fda_attributes`).

### 3.6 `GET /health` · 3.7 `GET /health/db`

Liveness (no DB) and readiness (`SELECT 1`; **503** when Neon is cold/unreachable). Both are `no-store` and rate-limit-exempt. Use `/health/db` to **pre-warm** before a burst (§11).

---

## 4. Pagination — keyset cursors (not page numbers)

The list/search endpoints return a `Page<T>` envelope:

```json
{ "items": [ … ], "next_cursor": "eyJ…", "limit": 25, "total": null }
```

- To get the next page, send `next_cursor` back as `?cursor=…`. `next_cursor` is **`null` on the last page**.
- The cursor is **opaque** (base64url) and **encodes the sort position** (published_at-or-rank + id). It is **not** a page number — there is no "jump to page 5". Deep-linking model: put the **filters** in the URL (shareable), and treat the cursor as ephemeral forward-paging state. Keep **all filter params identical** across a paging sequence; changing a filter with a live cursor is undefined.
- A cursor minted on one sort path (e.g. `/recalls/search` rank order) replayed on a different path (`/recalls` published order) returns **`400 bad_cursor`**, not a 5xx — handle 400 by resetting to page 1.
- `with_total=true` adds a `total` count (second COUNT query, slower) — request it only when the UI shows a total.

---

## 5. Filtering semantics

- **Same field, multiple values = OR (any-of)**; **different fields = AND**. Example: `?source=CPSC,FDA&classification=2` → `(source IN (CPSC,FDA)) AND (classification = '2')`.
- Comma form and repeat form are identical; pick one in your querystring serializer.
- `classification` and `lifecycle_status` are **source-native exact strings** — a `classification` filter is only meaningful AND-ed with `source` (see the per-source vocabularies in §3.1 and the matrix in §7). Build classification filter UIs **scoped to the selected source**, not as one global list.
- `is_active=true|false` silently **excludes CPSC/NHTSA** (their value is `null`). A "status" facet should offer **Active / Inactive / Any**, where "Any" omits the param (so CPSC/NHTSA reappear).

---

## 6. Response shapes

Don't hand-type these — the generated client (§12) gives you `components['schemas']['RecallSummary']` etc. Field-level meaning + **per-source population** is documented in two places you should surface in the UI:
- Each field's `description` in `openapi.json` (the machine-readable data dictionary, with a trailing `Sources: …` provenance tag).
- The **per-source provenance matrix** in `documentation/data_contract.md` (the at-a-glance human table).

Models: `RecallSummary` (list), `RecallSearchHit` (= summary + `rank`), `RecallDetail` (full), `ProductSearchHit`, `FirmProfile` (+ `UsdaEstablishment`/`UscgManufacturer`/`FdaAttributes` sidecars), `FirmRef` (element of `firms[]`), `Page<T>`.

---

## 7. Data honesty — what the UI MUST caption

The API is deliberately honest about cross-source non-comparability; the site must carry these into badges/captions (source: `documentation/data_contract.md` → "Per-source field provenance"). Don't restate the matrix — link it from the `/api/caveats` page and key it off the field `Sources:` tags.

1. **`classification` is source-native, not unified.** FDA = `1/2/3/NC` (numeric; `NC` = Not Yet Classified), USDA = `Class I/II/III` + `Public Health Alert`, USCG = `H/L/M/S`, CPSC/NHTSA = none. **Never** render a single global "Class I/II/III" legend; label/scope by source. (The website plan's "FDA Class I/II/III" is wrong.)
2. **`is_active` is tri-state** — CPSC/NHTSA carry no lifecycle (`null`). A green/red active dot must have a third "unknown/n.a." state for them.
3. **UPC is recall-level only.** There is no per-product UPC. The `upc=` search matches the recall-wide `recall_product_upcs` array (CPSC-only, ~5% of CPSC recalls). Empty-state copy: "No match ≠ not recalled." Surface HIN/model for product identity, not a UPC column.
4. **Geography has two distinct lenses** (per the pipeline's gold notes): `distribution_state_codes`/`distribution_country_codes` = *where the product was distributed* (FDA/USDA only); firm-registration geography (from the firm sidecars / `fct_recalls_by_geography` `basis=firm_registration`) = *where the firm is registered* — **registration ≠ where harm occurred**. Two separate captioned charts, never one toggle.
5. **Units recalled** (NHTSA/USCG) are recall-magnitude, not unique vehicles, and not cross-source comparable.
6. **Edit/observability fields were pruned.** The only edit signal the API exposes is **`has_been_edited`** (boolean — "the pipeline detected an editorially-meaningful change since first ingest"; **not** an official agency-amendment count, and **no date**). The §5.3 lifecycle timeline can show `announced_at → published_at`, `lifecycle_status`, and a `(revised)` badge from `has_been_edited` — but **not** a dated edit history (those fields were removed; a dated "last revised" is a future cross-repo item).

---

## 8. CORS — open, GET-only

`main.py` adds `CORSMiddleware` outermost: `allow_origins=["*"]`, `allow_methods=["GET"]`, `allow_headers=["*"]`, `expose_headers=["Retry-After","ETag","X-Request-ID"]` (ADR 0014). Consequences for the site:
- Browser `fetch()` from **any** origin (incl. `*.pages.dev`, the custom domain, the Scalar docs island) works directly — **no proxy needed**, and **no CORS change** is needed when the custom domains come online.
- The API is **credential-free**: do **not** set `credentials: "include"` — with an `*` origin the browser would reject the response, and there are no cookies anyway.
- Because CORS is outermost, error/429/503 bodies and the exposed headers (`Retry-After`, `ETag`, `X-Request-ID`) are readable cross-origin — use `Retry-After` to back off, `X-Request-ID` to correlate a bug report with API logs.
- Only `GET` is allowed; there are no mutating calls to make.

---

## 9. Caching

Successful GETs carry:
- `Cache-Control: public, max-age=300` (5 min — reflects the nightly ~03:00 UTC rebuild cadence).
- `ETag: W/"<version>-<startup_id>"` — **changes on every deploy, NOT per data rebuild.** Don't treat the ETag as a data-version. It's usable for conditional GETs (`If-None-Match` → 304) within a deploy.
- `Last-Modified` = server **startup** time (not data rebuild time).

Implications: build-time aggregate pulls can rely on data being stable for ~a day; runtime fetches can be cached ~5 min by the browser/CDN. If you put **Cloudflare proxy** in front of the API (orange-cloud, §14C), CF will honor `Cache-Control` and serve repeats from edge — beneficial, but see the rate-limit/IP caveat there.

---

## 10. Rate limiting

- **60 requests / minute / IP**, returned as `429 rate_limited` + `Retry-After: 60`. `/health` and `/health/db` are exempt.
- It's an **in-process (per-machine) MemoryStorage** limit: it **resets on cold start** and each Fly machine counts separately, so it's effectively per-machine, not a true global. Fine at portfolio scale; not a guarantee.
- Frontend obligations: **debounce** the search box (≥300 ms) and the recalls-filter refetch; don't fire a request per keystroke; back off on `429` using `Retry-After`. A typical user never hits 60/min, but an un-debounced search will.

---

## 11. Cold start & resilience (design for this)

Fly runs **scale-to-zero** (`min_machines_running=0`) over **Neon serverless** (auto-suspend). After idle, the **first** request triggers a machine wake **and** a Neon wake:
- The machine auto-starts on the incoming request; Neon may take a few seconds to resume. While Neon is cold, data endpoints can return **`503 upstream_unavailable` + `Retry-After: 5`** (the API caps the DB connect at 5 s and fails fast rather than hanging).
- **Runtime islands:** show a friendly "waking up…" state, then **retry with backoff** on `503` (respect `Retry-After`). Optionally fire a `GET /health/db` first to pre-warm, then load data once it returns 200.
- **Build-time pulls (if/when `/stats/*` or a gold export exists):** retry with backoff and **fail the build loudly** if the API never wakes — better a stale-but-good deploy than a blank dashboard.
- To remove cold starts entirely you can set `min_machines_running = 1` in `fly.toml` (within free allowance) — a backend toggle, not a frontend concern.

---

## 12. OpenAPI & API-docs integration

**Two separate integrations — don't conflate them:**

**(a) The typed API client (data fetching).** Generate, never hand-write:
- `openapi-typescript <API_URL>/openapi.json -o src/lib/api/schema.d.ts` (types) + `openapi-fetch` (tiny typed `fetch`). Wrap the endpoints in named functions (`listRecalls`, `getRecall`, `searchProducts`, `getFirm`, …); pages/islands call those.
- Commit the generated `schema.d.ts`; regenerate it in CI from the **deployed** spec and **fail the build on drift** — a backend contract change then shows up as a red check, not a silent runtime break.
- The API single-sources its version from `pyproject.toml`; `openapi.json info.version` tracks it, and an `export_openapi --check` gate in this repo guarantees the committed spec matches the code. So the committed `openapi.json` is a safe pin.

**(b) The public API-docs *page* (rendering the reference).** Fully specified in this repo's `documentation/frontend-api-docs-handoff.md` — **Starlight + `starlight-openapi`** (static, build-time, crawlable) as the primary path, optional **Scalar** island for an interactive "try it". That doc has the `astro.config` wiring, the page structure (`/api/`, `/api/pagination/`, `/api/caveats/`, `/api/changelog/`, …), and the rule: **never hand-maintain endpoint tables — render them from `openapi.json`; author only the prose caveats/pagination pages from `documentation/api-reference.md`.** Follow it as-is.

---

## 13. Reconciliation with `website-frontend-plan.md` (what's stale / blocked)

The plan's **strategy is sound and current** (Astro + Cloudflare Pages + hybrid + OpenAPI-generated client — it matches your Cloudflare infra). Its **API specifics are not.** Fix these before/while building:

| Plan says | Reality | Action |
|---|---|---|
| `/stats/*` + `fct_*` dashboard endpoints (§5.1, §5.5: 8 panels, leaderboard, overview KPIs) | **Do not exist.** The API has only the 7 endpoints in §3. | **Blocker for the dashboards + landing charts.** Either (a) build a `/stats/*` API phase over `fct_*` (pipeline ADR 0024), or (b) have the *pipeline* export `fct_*` → static JSON for a build-time bake. Sequence dashboards **after** that decision; the entity/search pages don't depend on it. |
| `GET /recalls?...&date_from=&date_to=&firm_id=&status=&page=` | Params are `published_after`/`published_before`, **no `firm_id`**, `is_active` (not `status`), `cursor` (not `page`) | Use §3.1 names. Keyset, not offset (§4). |
| Firm page "this firm's recalls" via `?firm_id={id}` (§5.4) | **No `firm_id` filter on `/recalls`.** Only `firm=` substring on the *primary* firm name (imprecise; misses co-recalled). | Small API gap — recommend adding `?firm_id=` (filters the `firms` rollup). Until then, the firm page can't list a firm's recalls precisely. **Flag to backend.** |
| "FDA Class I/II/III" by-classification chart (§5.1) | FDA emits `1/2/3/NC` | Source-native legends (§7.1). |
| Lifecycle timeline "announced → amended → terminated + edit-history flags" (§5.3) | Edit counts/timestamps/presence flags were **pruned**; only `has_been_edited` (bool, no date) remains | Timeline = `announced_at → published_at` + `lifecycle_status` + a `(revised)` badge. No dated edit history. |
| Per-product `upc` column (§5.3/§5.6) | **Dropped** from the response; `upc=` search still works (recall-level) | Don't expect a `upc` field; keep the UPC honesty caveat (§7.3). |
| Recall keyword search not mentioned | `GET /recalls/search?q=` exists (§3.2) | Opportunity for a recall-level search, distinct from product search. |

**Net:** buildable **now** against the live API — recalls browser (§5.2), recall detail (§5.3, minus the rich timeline), firm profile (§5.4, minus the per-firm recalls list until `?firm_id=`), product search (§5.6). **Blocked on backend work** — landing charts + dashboards (§5.1/§5.5) until `/stats/*`-or-export; precise firm-recalls list until `?firm_id=`.

---

## 14. Custom-domain runbook (Cloudflare + Fly.io)

Goal: site at **`consumer-product-recalls.info`** (Cloudflare Pages) and API at **`api.consumer-product-recalls.info`** (Fly.io), both on the Cloudflare-registered domain. No API code change is required to add the domain.

### 14A. Register the domain (Cloudflare Registrar)
1. Cloudflare dashboard → **Domain Registration → Register Domains**.
2. Search `consumer-product-recalls.info` → add → checkout. (Cloudflare Registrar charges **at-cost** — wholesale + ICANN fee, no markup; WHOIS redaction is on by default.)
3. On purchase, Cloudflare **auto-creates the DNS zone** and assigns its nameservers — because the domain is registered *at* Cloudflare, there's **no nameserver change to make**. DNS is managed under that zone.

### 14B. Host the site on Cloudflare Pages + apex domain
1. Dashboard → **Workers & Pages → Create → Pages → Connect to Git** → pick the website repo.
2. Build settings: framework **Astro** (or build command `npm run build`, output dir `dist`). Add env vars — at minimum `PUBLIC_API_URL=https://api.consumer-product-recalls.info` (or the `.fly.dev` URL until 14C is done). Deploy → you get a `*.pages.dev` URL.
3. Pages project → **Custom domains → Set up a custom domain** → add `consumer-product-recalls.info` (apex) and `www.consumer-product-recalls.info`. Because the zone is in the same account, Pages **auto-creates the DNS records and provisions TLS** (apex uses CNAME flattening). Pick one canonical host (apex recommended) and redirect the other (Pages → custom domain redirect, or a Bulk Redirect rule).

### 14C. Point `api.` at the Fly.io app
**Recommended: DNS-only (grey-cloud), let Fly terminate TLS with its own Let's Encrypt cert** — simplest, and it preserves real client IPs for the API's rate limiter.

1. In the **API repo**, add the cert and read the exact records Fly wants:
   ```bash
   fly certs add api.consumer-product-recalls.info
   fly certs show api.consumer-product-recalls.info   # shows required DNS + validation status
   ```
2. In **Cloudflare DNS** (the `consumer-product-recalls.info` zone), add a record per what `fly certs show` reports — for a subdomain this is typically:
   - `CNAME  api  →  consumer-product-recalls-api.fly.dev`, **Proxy status = DNS only (grey cloud).**
   - If Fly asks for DNS-01 validation, also add the `_acme-challenge.api` `CNAME` it prints (also DNS-only).
   (Apex would need `A`/`AAAA` to Fly's IPs from `fly ips list`; a subdomain CNAME is cleaner, which is why the API lives at `api.`.)
3. Re-run `fly certs show api.consumer-product-recalls.info` until it reports the cert **issued** (DNS propagation + ACME, usually minutes). Then `https://api.consumer-product-recalls.info` serves the API.
4. Set the website's `PUBLIC_API_URL=https://api.consumer-product-recalls.info` and redeploy Pages.

> **Why grey-cloud:** if you orange-cloud (proxy) the `api` record, Cloudflare terminates TLS and you must (a) set **SSL/TLS mode = Full (strict)** so CF→Fly stays encrypted against a valid cert, and (b) make the API read the real client IP from **`CF-Connecting-IP`** — otherwise the per-IP rate limiter (and logs) see Cloudflare's edge IPs, not users. Proxying buys you CF edge caching/WAF in front of the API, but adds those two concerns. At portfolio scale, **DNS-only is the low-friction choice**; revisit orange-cloud only if you want CF caching/WAF on the API and are ready to honor `CF-Connecting-IP` in the backend.

> **CORS is unaffected** by any of this — it's `*`, so the Pages site calls the `api.` host (or `.fly.dev`) with no extra config. If you later tighten CORS to specific origins, add `https://consumer-product-recalls.info` to the allow-list (a backend change).

### 14D. Optional — remove API cold starts
Set `min_machines_running = 1` in the API's `fly.toml` (within the free machine allowance) so the first visitor doesn't wait on a wake. Frontend doesn't change.

---

## 15. Change management / contract drift

- The **committed `openapi.json`** is the pinned contract; regenerate the TS client from it (or the live `/openapi.json`) and gate on drift in website CI (§12a).
- A breaking API change bumps `pyproject.toml` version → `openapi.json info.version` → your `gen:api` drift check goes red. Treat that as the signal to review the `/api/changelog` page and any affected fetch code.
- This handoff + `documentation/frontend-api-docs-handoff.md` + `documentation/data_contract.md` are the three docs to re-read when the spec version changes.

---

## 16. Quick-start checklist (website Claude Code instance)

1. Pull `openapi.json` from the live API at build time; `gen:api` → `schema.d.ts` (commit it). Wire `openapi-fetch` + named endpoint wrappers (§12a).
2. Build the **entity/search** pages against §3 (recalls browser, recall detail, firm profile, product search) — these work today. Use the §3.1 param names + keyset cursors (§4), not the website plan's stale ones.
3. Render the **API-docs page** per `documentation/frontend-api-docs-handoff.md` (Starlight + `starlight-openapi`, optional Scalar).
4. Surface the **data-honesty captions** (§7) from `documentation/data_contract.md` — source-native classification, tri-state active, recall-level UPC, two geography lenses, `has_been_edited`-only.
5. Handle **cold start (503 + retry)**, **rate limit (debounce + 429 backoff)**, and **keyset paging (opaque cursor, 400→reset)**.
6. **Defer the dashboards** until the `/stats/*` API surface (or a pipeline gold export) lands; flag the missing `?firm_id=` recalls filter to the backend (§13).
7. Stand up the domains per §14 (Pages apex + Fly `api.` subdomain, grey-cloud).
