Purpose: tell the website team how to build and maintain the public API-docs page, and hand off what they need to start.

---

## Source Artifacts

Two inputs drive the docs page. Neither should be replicated by hand on the site — link or render from them directly.

| Artifact | Location | What it provides |
|---|---|---|
| `openapi.json` | `/openapi.json` in this repo; live at `https://consumer-product-recalls-api.fly.dev/openapi.json` | Machine-readable endpoint contract: paths, params, response schemas, status codes, error envelopes. This is the single source of truth for every endpoint signature. |
| `documentation/api-reference.md` | This repo | Prose layer: pagination behavior, error envelope conventions, honest caveats (tri-state `is_active`, source-native `classification`, recall-level UPCs, no fuzzy search), and task-framed examples. Do not restate caveats or examples from this file on the site — link to it or quote the relevant section. |

---

## Format Options

| Renderer | Astro fit | Strengths | Weaknesses |
|---|---|---|---|
| **Starlight + `starlight-openapi`** | Native | Pure Astro/MDX, same build pipeline, Starlight's navigation sidebar integrates endpoint pages automatically, no iframe, zero extra runtime | Younger plugin; generated pages are less polished than dedicated tools; customizing response-example layout requires MDX overrides |
| **Scalar** | Island embed | Best-in-class interactive UX, dark-mode-ready, lightweight bundle, actively maintained, one `<script>` or React/Vue component | Requires a client island (`client:load`); no static pre-render of the reference (search engines see a blank island on first paint unless you SSR) |
| **Redoc / Redocly** | Island embed | Battle-tested, three-panel layout familiar to API consumers, strong OpenAPI 3.1 support | Heavier bundle than Scalar; three-panel layout does not adapt well to narrow viewports; same SSR caveat as Scalar |
| **Swagger UI** | Island embed | Universal name recognition | Dated UX; heavy; not recommended unless existing consumer tooling requires it |
| **Stoplight Elements** | Island embed | Clean web-component API, good code-sample generation | Bundle size; paid Stoplight Platform features bleed into docs UX if you are not careful |

---

## Recommendation

Use **Starlight + `starlight-openapi`** as the primary rendering path.

Rationale: the frontend is Astro (pipeline [ADR 0039](../../consumer-product-recalls/documentation/decisions/0039-frontend-framework.md)). Starlight is the canonical Astro documentation layer. The `starlight-openapi` plugin consumes `openapi.json` at build time and generates one static page per endpoint group, fully crawlable, no client island required for the reference pages themselves. The spec is the single source of truth — endpoint tables are never hand-maintained on the site.

Pair it with a thin authored narrative layer sourced from [`documentation/api-reference.md`](api-reference.md): pull the caveats section and the pagination/error conventions into MDX pages that sit alongside the generated reference. These are the only pages hand-authored; everything endpoint-specific comes from the spec.

If the interactive "try it" panel is a priority at launch, embed **Scalar** as a single client island (`client:load`) on a dedicated `/api-reference/interactive` page alongside the static Starlight reference. This preserves static crawlability of the main reference while offering the interactive surface for developer exploration.

---

## Handoff Brief for the Website Claude Code Instance

### Inputs

- **Live OpenAPI spec:** `GET https://consumer-product-recalls-api.fly.dev/openapi.json` — pull this at build time, not at runtime. Commit the fetched copy to the website repo under `public/openapi.json` or import it directly in the Starlight config.
- **Prose reference:** [`documentation/api-reference.md`](api-reference.md) in this repo — the honest caveats and convention preamble live here. Mirror or excerpt; do not re-author.

### Recommended Page Structure

```
/api/                          — Overview (purpose, base URL, open API / no auth)
/api/authentication/           — Authentication: none. API is open GET, no key required.
/api/endpoints/                — Endpoint reference (spec-driven via starlight-openapi)
/api/pagination/               — Keyset pagination explanation + next_cursor usage
/api/errors/                   — Error envelope shape + status code table
/api/caveats/                  — Honest data caveats (sourced from api-reference.md)
/api/changelog/                — Breaking changes + schema_version bumps
```

### Starlight + starlight-openapi Wiring (Astro)

```bash
npx astro add starlight
npm install starlight-openapi
```

In `astro.config.mjs`:

```js
import starlightOpenAPI, { openAPISidebarGroups } from 'starlight-openapi'

export default defineConfig({
  integrations: [
    starlight({
      plugins: [
        starlightOpenAPI([
          {
            base: 'api/endpoints',
            label: 'Endpoints',
            schema: './public/openapi.json',   // fetched from live URL at build time
          },
        ]),
      ],
      sidebar: [
        { label: 'Overview', link: '/api/' },
        { label: 'Authentication', link: '/api/authentication/' },
        ...openAPISidebarGroups,
        { label: 'Pagination', link: '/api/pagination/' },
        { label: 'Errors', link: '/api/errors/' },
        { label: 'Caveats', link: '/api/caveats/' },
        { label: 'Changelog', link: '/api/changelog/' },
      ],
    }),
  ],
})
```

Fetch the spec at build time in a pre-build script or CI step:

```bash
curl -sSf https://consumer-product-recalls-api.fly.dev/openapi.json -o public/openapi.json
```

### Authentication and CORS

The API is **open, no authentication required**. All endpoints are `GET`. No API key, no `Authorization` header.

**CORS — open (`Access-Control-Allow-Origin: *`).** `src/recalls_api/main.py` adds `CORSMiddleware` as the outermost layer with `allow_origins=["*"]`, `allow_methods=["GET"]`, so any browser origin may read responses. This is intentional for a public, read-only, credential-free API — see [ADR 0014](decisions/0014-open-cors-public-read-only-api.md). Browser `fetch()`/`XMLHttpRequest` from the website, including the Scalar interactive island, works directly against `https://consumer-product-recalls-api.fly.dev` with no proxy.

Because the middleware is outermost, the headers land on every response, so error and rate-limit (429) bodies are readable cross-origin too. The response also exposes `Retry-After`, `ETag`, and `X-Request-ID` (via `Access-Control-Expose-Headers`) so client JS can read them — use `Retry-After` to back off on a 429/503 and `X-Request-ID` to correlate an error with the API's logs. The API is credential-free: do **not** set `credentials: "include"` on the client — with an `*` origin the browser rejects the response, and there are no cookies to send.

### Theming

The Starlight default theme adapts cleanly to dark/light. Match the website's color tokens via [Starlight CSS custom properties](https://starlight.astro.build/guides/css-and-tailwind/). No special theming is required for the spec-generated pages.

### Code Examples

`starlight-openapi` generates curl examples from the spec's `x-codeSamples` or its own template. Supplement with the concrete examples in [`documentation/api-reference.md`](api-reference.md) (the `curl` + URL blocks in that file are the canonical authored examples). Copy them into MDX frontmatter or a `<CodeBlock>` component on the relevant authored pages — do not duplicate them in the Starlight plugin config.

### Keeping the Spec in Sync

- **On each API deploy:** the deploy pipeline (`deploy.yml`) runs after CI passes on `main`. Add a website repo dispatch or a scheduled build that re-fetches `openapi.json` from the live URL after the smoke check passes.
- **On a `gold_meta.schema_version` bump:** the API's `documentation/api-reference.md` will be updated to reflect the change. Review the Caveats and Changelog pages and update the authored MDX accordingly.
- **Never hand-edit endpoint tables on the site.** If a param is wrong in the rendered docs, the fix goes to `openapi.json` (or the source code that generates it) — not to the website repo.

### What to Render from the Spec vs. the Prose

| Content | Source |
|---|---|
| Endpoint paths, methods, params, response schemas, status codes | `openapi.json` via starlight-openapi — rendered automatically |
| Error envelope shape | `openapi.json` (every error response uses `ErrorEnvelope` schema) — rendered automatically |
| Pagination mechanics (`next_cursor`, `limit`, `with_total`) | Authored MDX on `/api/pagination/`, sourced from [`api-reference.md`](api-reference.md) §Pagination |
| Honest caveats (`is_active` tri-state, source-native classification, recall-level UPCs, no fuzzy search) | Authored MDX on `/api/caveats/`, sourced from [`api-reference.md`](api-reference.md) §Caveats |
| Base URL, open-API note, CORS status (open `*` — see Authentication and CORS above) | Authored MDX on `/api/` overview page |
| Changelog | Authored MDX on `/api/changelog/` — updated manually on breaking changes |

---

## Cross-References

- Endpoint specifications: [`documentation/api-reference.md`](api-reference.md)
- Machine contract: [`openapi.json`](../openapi.json)
- Frontend framework decision: [pipeline ADR 0039](../../consumer-product-recalls/documentation/decisions/0039-frontend-framework.md)
- Data caveats root causes: [`documentation/data_contract.md`](data_contract.md)
