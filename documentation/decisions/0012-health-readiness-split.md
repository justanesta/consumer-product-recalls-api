Purpose: Record why liveness and readiness are separate endpoints and how each is used.

# 0012 - Health/readiness split: DB-free /health liveness vs SELECT-1 /health/db readiness

**Status:** Accepted (2026-06-15) / **Date:** 2026-06-15

Upstream framing: the Fly.io deployment target and scale-to-zero posture are governed by pipeline ADR 0025 (`consumer-product-recalls/documentation/decisions/0025-api-deployment-target.md`).

## Context

The deployment stack has two independent cold-start layers:

1. **Fly machine (scale-to-zero)** — the container stops when idle; `auto_stop_machines = "stop"`, `min_machines_running = 0` (`fly.toml:17-19`).
2. **Neon compute (auto-suspend)** — the Postgres compute suspends after ~5 minutes of DB idle, independent of whether the Fly machine is up.

Either or both may be cold on any given request. A Fly `[[http_service.checks]]` probe that touches the DB on every tick would wake Neon continuously — defeating scale-to-zero — and would flip the container unhealthy whenever Neon is legitimately cold, triggering restart loops.

At the same time, operators and CI need a way to verify actual DB connectivity after a deploy or on observing a 503. A completely DB-free health surface gives no readiness signal.

The boot sequence in `db.open_pool()` (`db.py:69-92`) deliberately tolerates a cold/unreachable Neon at startup (logs `db.boot_check_skipped` and continues) so the process and its DB-free liveness probe are available immediately even before Neon wakes.

## Decision

1. **`GET /health` — liveness only.** Returns `{"status":"ok","version":"<version>"}` from process memory with zero DB I/O (`routers/health.py:18-21`). Always 200 while the process is up; never touches the pool.

2. **`GET /health/db` — readiness only.** Issues `SELECT 1` via `db.healthcheck()` through the normal `deps.get_conn` dependency (`routers/health.py:24-33`, `db.py:102-104`). A cold or unreachable Neon propagates as `OperationalError` → 503 + `Retry-After: 5` via the registered DB error handler.

3. **Platform probes point at `/health` only.** Both `fly.toml` `[[http_service.checks]]` (`fly.toml:28-33`) and the Docker `HEALTHCHECK` (`Dockerfile:28-29`) target `/health`. The comment in `fly.toml:26-27` states this explicitly.

4. **Both endpoints are exempt from rate limiting** (`main.py:73-74`: `limiter.exempt(health.health)` and `limiter.exempt(health.health_db)`).

5. **`/health/db` is used by:** post-deploy readiness smoke in `deploy.yml` (5 retries, 10 s gaps, `deploy.yml:32-40`); operators doing manual DB connectivity checks; optional keep-warm crons (`GET /health/db` every ~4 min keeps both Fly machine and Neon compute warm).

## Consequences

**Accepted tradeoffs:**

- The platform never sees DB failures as a liveness signal. A dead Neon pool surfaces only as 503s on data endpoints, not as machine restarts — which is the correct behavior for a dependency failure.
- `/health` gives no DB connectivity guarantee. Operators must use `/health/db` or observe data-endpoint 503s to diagnose a DB outage.
- The post-deploy smoke (`deploy.yml`) retries `/health/db` specifically to cover a cold-Neon wake; the 5 × 10 s budget accommodates Neon wakes that take up to ~50 s in the worst case.
- A keep-warm cron targeting `/health/db` prevents both cold starts during its window, at the cost of disabling scale-to-zero for that period. This is an operator-controlled lever, not a default.
