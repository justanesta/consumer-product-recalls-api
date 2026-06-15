# 0007 - HTTP Cache-Control keyed to nightly rebuild; weak ETag per startup; no server-side cache v1

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

## Context

Gold marts are fully rebuilt nightly at ~03:00 UTC (`transform.yml`). Between rebuilds the data is immutable — every response for the same query returns the same rows. This makes responses safe to cache for hours, and the natural cache invalidation boundary is "which nightly build produced this data."

Two constraints prevent a precise, data-keyed ETag today:

1. **No rebuild-timestamp surface exists in the gold layer.** `gold_meta.rebuilt_at` is a planned upstream deliverable (`project_scope/build/06-deployment-and-ops.md` §5c) but has not landed. `first_seen_at` / `last_seen_at` are per-recall pipeline-observation times, not a global build stamp.
2. **Health endpoints must never be cached.** Fly.io liveness probes hitting `/health` on a cached `200` after the process dies would suppress machine restarts — a hard operational requirement (`middleware.py:28–29`; `fly.toml` liveness check).

A server-side in-memory response cache (e.g. Redis, per-process dict) was considered. Given the Fly.io scale-to-zero topology — each cold start resets all process state — such a cache would be near-empty on most requests and would add stale-data risk and memory pressure with no real benefit.

## Decision

1. **`CacheControlMiddleware`** (`middleware.py`) sets `Cache-Control: public, max-age=<cache_max_age_seconds>` on all `GET 200` responses to data endpoints. The default is 300 s, configurable via `settings.cache_max_age_seconds` (`settings.py:42`). This is intentionally conservative relative to the ~24 h rebuild cadence; it can be raised once `gold_meta.rebuilt_at` is available.

2. **Weak ETag per startup:** `W/"<version>-<startup_id>"` (`main.py:83`), where `startup_id = GIT_SHA env var or uuid4().hex[:12]` (`main.py:77`). When `GIT_SHA` is injected by the deploy step the ETag is stable for the lifetime of that build; without it a random 12-hex-char ID is minted at cold start. The ETag is set via `setdefault` so a handler can override it (`middleware.py:32`).

3. **`Last-Modified`** is set to `formatdate(usegmt=True)` — the RFC 2822 process-start timestamp (`main.py:84`). Same per-startup anchor as the ETag.

4. **`/health*` paths get `Cache-Control: no-store`** regardless of status code (`middleware.py:28–29`). Liveness and readiness probes are always live responses.

5. **Conditional GET (`If-None-Match` / `If-Modified-Since`) is deferred.** The per-startup ETag changes on every cold wake, not on every data rebuild. Responding `304` on a same-build revalidation is correct, but honoring `If-Modified-Since` is over-aggressive (the `Last-Modified` moves on cold start, not on data change). Full conditional-GET support is deferred to the `gold_meta.rebuilt_at` milestone.

6. **No server-side cache.** The read-only Neon connection pool plus Neon's own buffer cache is the source of truth. No Redis, no in-process response dict.

## Consequences

**Accepted tradeoffs:**

- CDN and browser clients cache data responses for up to `cache_max_age_seconds` (default 5 min). This is safe — data does not change within a nightly rebuild window.
- The per-startup ETag is more conservative than the data boundary: it invalidates on every cold wake (which is more frequent than actual data changes). Clients revalidate unnecessarily after a scale-to-zero restart. This never serves stale data.
- `Last-Modified` tracks process start, not data freshness. Same consequence: over-revalidation, never staleness.
- When `gold_meta.rebuilt_at` lands upstream, the ETag and `Last-Modified` can be upgraded to the true rebuild timestamp without changing the middleware contract — `middleware.py` already uses `setdefault`, so a handler or lifespan hook can inject a data-keyed value.
- `cache_max_age_seconds` is tunable at deploy time with no code change, allowing the operator to raise it (e.g. toward 3600 s) as confidence in the rebuild cadence grows.
