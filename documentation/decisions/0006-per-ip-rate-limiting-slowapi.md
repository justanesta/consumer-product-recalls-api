Purpose: ADR for the per-IP rate-limiting mechanism used by the consumer-product-recalls API.

# 0006 - Per-IP rate limiting via slowapi (in-process MemoryStorage; per-machine caveat documented)

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

## Context

The API is open and unauthenticated. Without a limit a single IP can issue rapid-fire requests that exhaust the Neon connection pool (pool_size=5, max_overflow=5 — 10 total slots, the `db_pool_size` / `db_max_overflow` fields in `settings.py`) and DoS the service for all users. The DB is the bottleneck: connections, not CPU.

Pipeline ADR 0024 §6 says only that "abuse control is platform/rate-limit level, not application auth." It does not name a library or a numeric limit (`project_scope/build/06-deployment-and-ops.md`).

A true global rate limit requires shared state across processes (Redis or similar). Running Redis as a required dependency is incompatible with the free-tier, zero-ops target established in pipeline ADR 0025. A per-process limit is sufficient at personal-project scale and can be upgraded without an API change.

## Decision

1. Use `slowapi` (a Starlette/FastAPI wrapper over the `limits` library) as the rate-limiting layer. Key by client IP via `get_remote_address`, where the limiter is created in `create_app()` (`main.py`).

2. Apply `SlowAPIMiddleware` globally (all routes) so no endpoint is accidentally left unprotected. Default limit: `60/minute` per IP. Both the enabled flag and the limit string are `Settings` fields (`rate_limit_enabled: bool = True`, `rate_limit_default: str = "60/minute"` in `settings.py`) so they are tunable without a code change.

3. Exempt `/health` and `/health/db` explicitly via `limiter.exempt()` in `create_app()` (`main.py`) so platform liveness probes, keep-warm crons, and operator readiness checks never consume rate-limit budget.

4. Bridge `RateLimitExceeded` to the uniform error envelope via `rate_limited_response()` in `errors.py`: `429 Too Many Requests` with `Retry-After: 60` and `{"error":{"type":"rate_limited","detail":"...","request_id":"..."}}`.

5. Set `--proxy-headers --forwarded-allow-ips '*'` in the Dockerfile `CMD` so uvicorn trusts Fly's edge proxy and `get_remote_address` reads the real client IP from `X-Forwarded-For` rather than the proxy IP (which would collapse all clients into one bucket).

## Consequences

**Accepted tradeoffs:**

- `slowapi`'s default `MemoryStorage` is in-process. Under Fly.io scale-to-zero: (a) the counter resets on every cold start; (b) if multiple Fly machines are running concurrently, each tracks its own counter — the effective limit per IP is `rate_limit_default × machine_count`, not a true global. This is documented in `create_app()` (`main.py`) and is acceptable at personal-project scale.
- The `60/minute` default is a judgment call, not a contractual SLA. It is tunable via `RATE_LIMIT_DEFAULT` without a code change or redeploy.

**Upgrade paths (not in v1):**

- Replace `MemoryStorage` with a Redis-backed store for a true global limit — no route or middleware changes required.
- Delegate to Fly.io or Cloudflare WAF rate limiting at the edge — the `SlowAPIMiddleware` can then be disabled via `rate_limit_enabled=false`.
- Add per-route decoration for endpoints needing different limits — `SlowAPIMiddleware` global default stays as the floor.
