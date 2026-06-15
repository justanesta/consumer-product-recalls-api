# 0005 - pydantic-settings config with SecretStr DSN; single required secret; fail-loud at boot

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

## Context

The API has exactly one required secret: `NEON_DATABASE_URL_RO`. Every other config knob (pool sizes,
timeouts, cache TTL, rate-limit string, pagination limits, log level, environment name) has a safe
default and can be tuned via `fly.toml [env]` without a code change.

Two failure modes shaped this decision:

1. **Late discovery of a missing DSN.** If `Settings()` is constructed at module import, any module
   that imports `settings` requires the secret at import time — breaking unit tests of pure modules
   (`queries/`, `pagination.py`, `models/`). If the secret is checked lazily inside a request
   handler, a misconfigured deploy serves confusing 500s for every request instead of refusing to
   start.

2. **Credential bleed.** The pipeline's read+write DSN (`NEON_DATABASE_URL`) and the read-only DSN
   (`NEON_DATABASE_URL_RO`) share a Neon project but bind different roles. A `SecretStr` field
   prevents the value from appearing in `repr()`, logs, or tracebacks. A distinct env-var name makes
   it structurally impossible to hand the API the write-capable DSN by accident
   (`settings.py:26-27`).

See also: `project_scope/build/04-implementation-blueprint.md §settings.py` (design rationale) and
`project_scope/deployment-plan.md §step 4` (operator wiring — `flyctl secrets set
NEON_DATABASE_URL_RO=...`).

## Decision

1. `Settings` extends `pydantic_settings.BaseSettings` with
   `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`. Extra keys in
   `.env` or the process environment are silently ignored.

2. `neon_database_url_ro: SecretStr` is the **only field with no default**. Pydantic raises a
   `ValidationError` naming the missing field if it is absent — not a generic `KeyError`.

3. All other fields carry typed defaults with `pydantic.Field` constraints (e.g.
   `db_pool_size: int = Field(default=5, ge=1)`, `rate_limit_default: str = "60/minute"`,
   `page_limit_max: int = Field(default=100, ge=1, le=100)`), making every knob env-configurable
   without requiring an operator to supply it.

4. `get_settings()` is decorated `@lru_cache(maxsize=1)` — it constructs exactly once per process
   lifetime (`settings.py:57`). Importing the module never constructs `Settings`.

5. The **first call to `get_settings()` is inside the FastAPI `lifespan`** (`main.py:39`): a missing
   DSN causes an immediate boot crash with a clear `ValidationError` before the server accepts any
   traffic. `create_app()` also calls it at `main.py:52` (to read `log_level`), so a misconfigured
   environment surfaces before the lifespan even runs.

## Consequences

**Accepted tradeoffs:**

- A deploy with a missing `NEON_DATABASE_URL_RO` crashes at startup with a clear `ValidationError`
  naming the field — no cryptic mid-request 500s, no silent misconfiguration.
- `SecretStr` means `settings.neon_database_url_ro.get_secret_value()` is the only call that
  materializes the DSN string; it never leaks into logs, `repr()`, or error tracebacks.
- The `_RO` suffix on the env-var name is a structural guard: `fly.toml [env]` cannot hold it (not a
  secret), and `flyctl secrets set` must be run explicitly — so the pipeline's write DSN cannot land
  there by accident.
- All tunable knobs remain env-configurable: `fly.toml [env]` sets `ENVIRONMENT` and `LOG_LEVEL`;
  `flyctl secrets set` handles the DSN; pool sizes, rate limits, and cache TTL can be overridden per
  platform without a code change.
- The `lru_cache` means settings are immutable for the life of the process; changing config requires
  a restart (acceptable — all config changes are deploys on Fly.io).
- Unit tests of pure modules (`queries/`, `pagination.py`, `models/`, `errors.py`) can import freely
  without setting the DSN because no module-level `Settings()` instance exists.
