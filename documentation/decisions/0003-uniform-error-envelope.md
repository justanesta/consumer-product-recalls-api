Purpose: Record the decision to use a single error envelope shape, map cold-DB exceptions to 503, and return opaque 500s.

# 0003 - Uniform error envelope: {error:{type,detail,request_id}}, cold-DB -> 503, opaque 500

**Status:** Accepted (2026-06-15) / **Date:** 2026-06-15

## Context

FastAPI's built-in error responses differ in shape depending on how an error surfaces:

- Path/query/body validation failures (`RequestValidationError`) produce a `{"detail": [...]}` array at the top level.
- `HTTPException` produces `{"detail": "<string>"}`.
- Unhandled exceptions produce a plain 500 with no structured body.

A public, unauthenticated API over a Neon-backed gold mart has three additional constraints:

1. **Leakage.** asyncpg connection strings, SQLAlchemy exception messages, and internal tracebacks must never reach callers. Neon DSN fragments are particularly sensitive in a public GitHub repo.

2. **Cold-start DB errors are not bugs.** The app runs on Fly.io scale-to-zero (`min_machines_running = 0`) over a Neon serverless database that also auto-suspends. A cold-start request can trigger an asyncpg `TimeoutError` or bare `OSError` that SQLAlchemy does not always wrap in its own `OperationalError`. These must map to a retryable 503, not a 500.

3. **Machine-parseable errors.** A public API needs a stable, documented shape so frontend and downstream consumers can handle errors without inspecting human-readable strings.

## Decision

1. **Single wire envelope.** Every non-2xx response body is:
   ```json
   {"error": {"type": "<string>", "detail": "<string or array>", "request_id": "<uuid>"}}
   ```
   Implemented as `ErrorEnvelope { error: ErrorDetail }` at `errors.py:65–72`. The `request_id` is read from the per-request `ContextVar` bound by `RequestIdMiddleware` so callers can correlate errors with operator logs.

2. **`ApiError` hierarchy.** Five concrete subtypes carry `status_code` and `error_type` as class attributes: `ResourceNotFound` (404 / `not_found`), `InvalidParameter` (422 / `invalid_parameter`), `BadCursor` (400 / `bad_cursor`), `UpstreamUnavailable` (503 / `upstream_unavailable`), `RateLimited` (429 / `rate_limited`). A single `_api_error_handler` covers all subtypes via FastAPI's MRO-based dispatch (`errors.py:146`). `UpstreamUnavailable` and `RateLimited` emit `Retry-After: 5`.

3. **Dedicated DB error handler.** `_db_error_handler` (`errors.py:107`) is registered for `OperationalError`, `DBAPIError`, `SqlTimeoutError`, and `OSError`. It returns 503 + `Retry-After: 5` with the fixed message `"database temporarily unavailable"` and logs the raw exception via structlog. asyncpg's bare `OSError` path is explicitly covered because SQLAlchemy does not always wrap it.

4. **FastAPI `RequestValidationError` reshaping.** `_validation_error_handler` (`errors.py:128`) converts FastAPI's native validation errors into the same envelope, preserving the per-field `{"loc": [...], "msg": "..."}` array as `detail`.

5. **Opaque catch-all.** `_catch_all_handler` (`errors.py:118`) logs the full traceback via `structlog` and returns `{"error": {"type": "internal_error", "detail": "an unexpected error occurred"}}`. No SQL, DSN, or exception text ever reaches the caller regardless of future code paths.

6. **OpenAPI visibility.** Each route decorator passes `responses=LIST_ERRORS` or `responses=ITEM_ERRORS` (`errors.py:84–85`), both referencing `{"model": ErrorEnvelope}`, so every documented error code and its envelope shape appear in `/openapi.json`.

## Consequences

- **Good.** Callers parse one envelope shape for all errors; the `type` field is the stable switch key. `request_id` lets operators correlate a caller-reported error to a specific `flyctl logs` line.
- **Good.** Cold-Neon 503s carry `Retry-After: 5` and a client-friendly message; callers are not left guessing whether to retry.
- **Good.** The opaque catch-all eliminates a class of accidental credential leakage unconditionally.
- **Good.** `LIST_ERRORS` / `ITEM_ERRORS` differ by one slot (400 vs 404), keeping the pattern tidy: list endpoints never 404 (they return `items: []`); single-resource endpoints never 400 (no cursor).
- **Trade-off.** The catch-all 500 suppresses internal detail, which can slow down diagnosing novel failures — the full traceback is in logs only.
- **Trade-off.** `slowapi`'s `RateLimitExceeded` is wired separately via `_on_rate_limited` → `rate_limited_response()` (`main.py:90`), which emits `Retry-After: 60` (not 5). The two retry hints are intentionally different; this asymmetry must be documented in the API reference.
