# 0014 — Open CORS for the public, read-only API

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

## Context

The consumer-facing website (Astro; pipeline ADR 0039) will make some API calls from the **browser** — a live search box, client-side pagination, the "is my product recalled?" lookup, and the Scalar "try it" panel on the API-docs page. Browsers enforce the same-origin policy: JavaScript on `https://<website>` may not *read* a response from `https://consumer-product-recalls-api.fly.dev` unless that response carries an `Access-Control-Allow-Origin` (ACAO) header naming the origin (or `*`). Without CORS, every browser-side call either fails or must be routed through a server-side proxy on the website (an extra hop, latency, and per-endpoint proxy code).

This API is **public, read-only (GET only), and credential-free** — no auth, no cookies, no `Authorization` header. The data it serves is already fully public; an unauthenticated `curl` returns everything.

## Decision

Add Starlette's `CORSMiddleware` in `create_app()` (`src/recalls_api/main.py`) as the **outermost** middleware (added last):

```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
```

1. **`allow_origins=["*"]`, not an origin allowlist.** The obvious alternative — restrict to the known website domain — buys nothing here: the data is public, so `*` exposes only what `curl` already exposes. An allowlist would add a config surface and a deploy-time coupling between this repo and the website's domain for no security gain, and it would misrepresent a genuinely public open-data API.
2. **Outermost placement** so the `Access-Control-*` headers are applied to every handled response — including 4xx/5xx error envelopes and 429 rate-limit responses — so browser clients can read those bodies too.
3. **No credentials.** `allow_credentials` is left at its `False` default. `*`-origin combined with credentials is the one combination browsers reject; since the API has no cookies/auth, credentials never apply.

## Consequences

- The website calls the API directly from the browser (live search, the Scalar island) with no proxy layer.
- `*` means any site's browser JS may read the API — the intent of a public open-data API, adding no exposure beyond what `curl` already provides. If the API ever gains auth or per-origin policy, this ADR is superseded.
- No OpenAPI change: middleware is not part of the schema, so the committed `openapi.json` snapshot and its drift contract (ADR 0010) are unaffected.
- Per-IP rate limiting (ADR 0006) is unchanged and still applies to browser-originated calls.
- Clients must not send `credentials: "include"` — with an `*` origin the browser would reject the response, and the credential-free API has no use for it.
- Covered by integration tests asserting ACAO on a GET and on an `OPTIONS` preflight (`tests/integration/test_ops.py`).
