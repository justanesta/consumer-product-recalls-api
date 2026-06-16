# 0001 - Read-only by construction: dedicated recalls_readonly role + per-connection transaction_read_only guard

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

## Context

The API is open and unauthenticated — no API keys, no JWT. It issues only `SELECT`; it never needs to write.

The pipeline's existing `recalls_app` role (migration `0033_recalls_app_role_posture.py`) carries:

```sql
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO recalls_app;
GRANT TRUNCATE ON firm_crosswalk, quantity_crosswalk TO recalls_app;
```

Handing that role to a public, no-auth API creates a write-amplified attack surface for zero benefit.

A second hazard is Neon-specific: roles created via the Neon Console, API, or CLI are **automatically added to `neon_superuser`**, whose `pg_write_all_data` membership silently grants write privilege on every table. Even a role that looks restricted in the grants table may carry writes through that membership path. (`project_scope/build/06-deployment-and-ops.md §3c`)

Finally, a role-level grant alone is insufficient: a future accidental `GRANT INSERT … TO recalls_readonly` would immediately open a write path with no other layer blocking it.

## Decision

1. **Provision a dedicated `recalls_readonly` role via SQL** (not the Neon console) — `CREATE ROLE recalls_readonly NOLOGIN;` — so Neon does not auto-add it to `neon_superuser`. The role receives only `GRANT SELECT` on the three gold serving marts (`mart_recall_summary`, `mart_product_search`, `mart_firm_profile`). No INSERT, UPDATE, DELETE, TRUNCATE, sequence USAGE, or default-privileges grant. (`project_scope/build/06-deployment-and-ops.md §3b`)

2. **Set `default_transaction_read_only = on` at the role level** — `ALTER ROLE recalls_readonly SET default_transaction_read_only = on;` — so every session opened by this role refuses writes regardless of what grants exist. (`project_scope/build/06-deployment-and-ops.md §3b`)

3. **Set `default_transaction_read_only = on` per connection** in `db.py`'s `server_settings` connect arg. This is independent of the role setting: belt + suspenders. (`src/recalls_api/db.py:59`)

4. **Assert read-only at boot.** `open_pool()` opens one test connection and executes `SHOW transaction_read_only`. If the result is not `"on"` and `settings.is_production` is true, it raises `RuntimeError("DB connection is NOT read-only in production — refusing to start.")` — a hard boot failure. (`src/recalls_api/db.py:82–88`)

5. **Use a separate env var `NEON_DATABASE_URL_RO`** (distinct from the pipeline's `NEON_DATABASE_URL`) so the two repos can never be accidentally wired to the same DSN. The field is `SecretStr`; a missing value raises `ValidationError` at boot. (`src/recalls_api/settings.py:28`)

## Consequences

**Accepted tradeoffs:**

- A misconfigured writable DSN causes a loud boot failure in production rather than silently opening a write path. This is the intended behavior.
- Cold or asleep Neon at boot causes the boot check to be skipped with a logged warning (`db.boot_check_skipped`); `pool_pre_ping` validates connections lazily on first use. The check is best-effort for transient unreachability — it is not a crash gate for a temporarily sleeping database. A reachable-but-writable connection in production remains a hard refusal.
- New gold marts added in future milestones (e.g., `fct_*` views for `/stats/*`) require an explicit `GRANT SELECT … TO recalls_readonly` — they are not auto-granted. This is a feature: the scope of the read-only role is intentionally narrow.
- The separate `_RO` env var means developers must configure two DSNs locally if they also run the pipeline. That friction is acceptable given the credential-crossing risk it prevents.
