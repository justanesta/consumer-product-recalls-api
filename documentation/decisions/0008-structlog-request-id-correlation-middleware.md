# 0008 - structlog JSON logging + per-request request_id correlation via contextvars middleware

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

> Upstream framing: pipeline ADR [0021 — Structured logging with structlog](../../../../consumer-product-recalls/documentation/decisions/0021-structured-logging.md) made the `structlog` + stdlib-bridge + TTY-aware-renderer choice for the batch pipeline. This ADR adapts that shape for an async HTTP server where the correlation unit is a per-request `request_id`, not a batch `run_id`.

---

## Context

The v1 observability stance (inherited from pipeline ADRs 0021 and 0029) is structured JSON logs to stdout, read via `flyctl logs`. No Sentry, no OpenTelemetry, no Datadog at v1.

An HTTP server adds three requirements the batch pipeline does not have:

1. **Per-request correlation.** An operator who receives `request_id` from a caller's error envelope must be able to `grep` that ID across every log line produced during that request — including lines from SQLAlchemy, asyncpg, and uvicorn. The pipeline solves the analogous problem with a `run_id` contextvar bound at extractor entry; the API needs the same mechanism per HTTP request.
2. **Access log.** A single structured line per request (method, path, status, latency_ms) that carries the same `request_id` as any mid-request log lines.
3. **Error envelope traceability.** The uniform error envelope (ADR 0003) includes `request_id`; the error handler must read the currently-bound contextvar without coupling to the request object.

Plain `logging.basicConfig` can produce JSON (with a formatter), but contextvar propagation requires manual plumbing through every function signature and has no composable processor chain. `loguru` fights stdlib-logging integration. The pipeline already made the `structlog` call in ADR 0021; mirroring it here means one mental model across both repos.

---

## Decision

1. **`configure_logging(log_level)`** is called once at `create_app()` startup (`main.py:53`). It selects `ConsoleRenderer` when `sys.stderr.isatty()` or `LOG_FORMAT=console`; otherwise `JSONRenderer` to stdout. The shared processor chain is: `merge_contextvars` → `add_log_level` → `add_logger_name` → `TimeStamper(fmt="iso")` → `PositionalArgumentsFormatter` → `StackInfoRenderer` → (`format_exc_info` on the JSON path) → renderer. A single `StreamHandler(sys.stdout)` on the stdlib root logger bridges third-party loggers (SQLAlchemy, asyncpg, uvicorn) through the same chain. `sqlalchemy.engine`, `sqlalchemy.pool`, and `uvicorn.access` are silenced to `WARNING`.

2. **`RequestIdMiddleware`** (`logging.py:84`) is registered as the outermost middleware layer (added last in `main.py:87`; see middleware-stack ordering in [architecture.md](../architecture.md)). On each request:
   - Reads `X-Request-ID` from incoming headers; mints `uuid4().hex` if absent.
   - Sets `_request_id: ContextVar` and calls `structlog.contextvars.bind_contextvars(request_id=rid)` so every `log.*` call in the request scope inherits it automatically.
   - After the response: echoes `X-Request-ID` on response headers, emits one `log.info("request", method, path, status, latency_ms)`, clears structlog contextvars, and resets the ContextVar token (no leak across requests).

3. **`get_request_id()`** (`logging.py:30`) exposes the contextvar value. The error envelope builder (`errors.py:21`) imports and calls it to populate `error.request_id` without coupling to the request object. Outside a request the default is `"-"`.

---

## Consequences

**Good:**
- Every log line and every `{"error": {"request_id": ...}}` body carry the same ID. `flyctl logs | grep <id>` reconstructs a complete per-request trace across the API, SQLAlchemy, and asyncpg.
- Third-party log lines emitted during request handling inherit `request_id` via the stdlib bridge — no library needs to be structlog-aware.
- The ContextVar token reset in `finally` guarantees no cross-request contamination even if a handler raises.
- Mirrors the pipeline's `configure_logging` shape almost verbatim — one mental model for both repos.

**Accepted tradeoffs:**
- `MemoryStorage` (rate limiter, separate concern) and this contextvar store are both per-process; under scale-to-zero each cold start is independent. This is already documented in ADR 0006.
- The access log emits at `INFO`; a high-traffic future state would generate one line per request. At current personal-project scale this is fine; a sampling processor can be inserted later without changing the middleware interface.
- `X-Request-ID` on incoming requests is trusted as-is (no validation). A malicious client can inject an arbitrary string; it flows into logs but not into any DB write or security decision.
