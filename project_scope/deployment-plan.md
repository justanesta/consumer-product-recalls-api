# Deployment Plan — recalls-api → Fly.io

**Status: code complete (C1–C10 + hardening). What remains is operator wiring, not code.**
The 5 endpoints, tests (~97 / ~90% cov at last run), Dockerfile, `fly.toml`, `render.yaml`, and the
gated CI→deploy workflows all exist and are correct. Everything below is configuration that touches
credentials or external services — i.e. **yours to run**, not something the build can do for you.

> Convention reminder: this repo *reads* gold; it owns no schema/role. The read-only role itself is
> provisioned in the pipeline repo (`consumer-product-recalls`). See `recalls-search-gold-plan.md`
> and the pipeline's `serving-layer-gold-readiness-plan.md`.

## What's left (the path to a live URL)

| # | Step | Where | Status / Notes |
|---|------|-------|----------------|
| 1 | **Verify** the `recalls_readonly` role is truly read-only (you already have its DSN) | pipeline repo / Neon console | Role exists ✅ — what remains is *confirming the grant scope* and understanding `default_transaction_read_only` (next section). The original "hard blocker" (provisioning) is effectively done. |
| 2 | Put the real DSN in `.env` locally | this repo (`.env`, gitignored) | Likely done if you've been running it. `settings.py` reads `.env` directly via pydantic-settings, so the app works regardless of the direnv fix. |
| 3 | `git remote add origin …` + `git push -u origin main` | this repo | **No remote today**; `main` has no upstream. Nothing in CI/CD runs until this exists. |
| 4 | Create the Fly app + set the DB secret | Fly | `flyctl apps create recalls-api` (or edit `app`/`primary_region` in `fly.toml` to match an existing app near your Neon region). Then `flyctl secrets set NEON_DATABASE_URL_RO="postgresql+asyncpg://recalls_readonly:<pw>@<host>/<db>?ssl=require"`. The secret is **never** in `fly.toml` (`[env]` holds only `ENVIRONMENT`/`LOG_LEVEL`). |
| 5 | Wire GitHub → Fly | GitHub repo settings | Add `FLY_API_TOKEN` as an Actions secret, and create a `production` Environment (the `deploy.yml` job targets `environment: production`). |
| 6 | Point the post-deploy smoke at your hostname | this repo (`.github/workflows/deploy.yml:35`) | TODO currently hits `https://recalls-api.fly.dev/health/db`. Update if your app name differs. |
| 7 | (local nicety) `uv run pre-commit install` | this repo | The lint/type/gitleaks gate is currently bypassed on local commits — **only CI enforces it**. Installing closes that gap. The `.envrc` `dotenv_if_exists`→`dotenv` fix is already applied. |

### CI/CD flow (already wired — no action beyond steps 3–6)

`ci.yml` runs the gate on every push/PR to `main` (`uv sync → ruff check → ruff format --check →
pyright → pytest → openapi drift → pre-commit --all-files`). `deploy.yml` triggers on
`workflow_run: CI completed (success) on main`, checks out **the exact SHA CI passed**, runs
`flyctl deploy --remote-only`, then retries `/health/db` 5× (covers a cold-Neon wake). A red CI →
no deploy. This is correct; you don't touch it except step 6's hostname.

## Understanding the read-only role & `default_transaction_read_only`

You asked what `default_transaction_read_only=on` means and where it's applied. Short version:

**What it is.** A Postgres session setting (GUC). When `on`, every transaction *starts* in READ ONLY
mode, so any write (`INSERT`/`UPDATE`/`DELETE`/DDL/`nextval`) raises
`ERROR: cannot execute … in a read-only transaction`.

**What it is NOT.** It is *not* the security boundary. A client whose role **has** write privileges
can override it per-transaction (`BEGIN READ WRITE` / `SET TRANSACTION READ WRITE`). It's a
**safety net / belt**, not access control. The real boundary is the **role's GRANTs** — if
`recalls_readonly` only has `GRANT SELECT` (no INSERT/UPDATE/DELETE), it physically cannot write no
matter what the transaction mode says. So:

- **Suspenders (the real protection):** `recalls_readonly` has `SELECT`-only on the gold marts and is
  **not** a member of any writable/superuser role.
- **Belt (defense in depth):** `default_transaction_read_only = on`.

**Where the belt is applied — three levels (you don't need all three):**

1. **Session level — already done by this API.** `db.py` opens every asyncpg connection with
   `server_settings={"default_transaction_read_only": "on", "statement_timeout": …, "timezone": "UTC"}`
   (`db.py:57–64`). And `open_pool` runs `SHOW transaction_read_only` at boot and **refuses to start
   in production** if it isn't `on` (`db.py:80–92`). So the API enforces it on its own connections
   regardless of how the role is configured.
2. **Role level — optional extra belt (run once, as an admin):**
   ```sql
   ALTER ROLE recalls_readonly SET default_transaction_read_only = on;
   ```
   Now *any* session by that role inherits it, even a `psql` you open by hand.
3. **Database level — don't.** `ALTER DATABASE … SET …` would force it on *every* role (including the
   pipeline's writer). Too broad.

**Your action (run these yourself — they need DB creds; I won't touch the live DSN):**

```sql
-- (A) As an admin/owner: what can this role actually do? Expect ONLY 'SELECT'.
SELECT table_schema, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'recalls_readonly'
ORDER BY 1, 2, 3;
-- Any INSERT/UPDATE/DELETE/TRUNCATE here = misconfiguration to fix.

-- (B) Neon trap check: is the role a member of a writable/superuser role?
SELECT r.rolname AS member_of
FROM pg_auth_members m
JOIN pg_roles r ON r.oid = m.roleid
JOIN pg_roles u ON u.oid = m.member
WHERE u.rolname = 'recalls_readonly';
-- Expect zero rows (or only benign roles). Membership in neon_superuser / pg_write_all_data defeats SELECT-only.

-- (C) Connected AS recalls_readonly:
SHOW default_transaction_read_only;        -- 'on' if (1) the API or (2) ALTER ROLE applied it
SELECT current_setting('transaction_read_only');
-- (D) Smoke — this should ERROR (read-only txn) or be permission-denied. Either is a PASS:
CREATE TEMP TABLE _probe (x int);
```

If (A) shows only `SELECT` and (B) is clean, you're correctly configured even if the GUC weren't set —
the API sets it per-session anyway. Running the `ALTER ROLE` in (2) is a cheap belt; do it if you want
hand-opened `psql` sessions protected too.

## Environment & secrets

**Only two real secrets exist in this project.** Everything else is non-secret config with defaults
in `settings.py` (read via pydantic-settings; a few extras via `os.getenv`).

| Secret | What it is | Required? | Set where |
|---|---|---|---|
| **`NEON_DATABASE_URL_RO`** | read-only Neon DSN (`recalls_readonly`); app fails loud at boot without it | **yes, at runtime** | **local:** Proton Pass via `.env.pass` (preferred) or `.env`; **Fly:** secret; **Render:** dashboard. **Not in CI** (`conftest` injects a dummy; tests never hit real Neon). |
| **`FLY_API_TOKEN`** | Fly **deploy** token, consumed only by `deploy.yml` | only for auto-deploy | **GitHub Actions repo secret only.** NOT needed locally — `flyctl` uses your `flyctl auth login` session. |

**Non-secret config (all optional; defaults shown).** `ENVIRONMENT` (development) · `LOG_LEVEL` (INFO) ·
`LOG_FORMAT` (json; `console` for pretty local logs — also auto-detects a TTY) · `GIT_SHA` (startup/release
marker) · `PORT` (8080) · `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_RECYCLE_SECONDS`/`DB_CONNECT_TIMEOUT_SECONDS`/`DB_COMMAND_TIMEOUT_SECONDS`
· `CACHE_MAX_AGE_SECONDS` (300) · `RATE_LIMIT_ENABLED` (true)/`RATE_LIMIT_DEFAULT` (60/minute) ·
`PAGE_LIMIT_DEFAULT`/`PAGE_LIMIT_MAX` (25/100).

**Per environment:**
- **Local dev:** `NEON_DATABASE_URL_RO` only. Tests need *nothing* secret (local: testcontainers via
  `sg docker`; CI: a `postgres:16` service + plain `TEST_DATABASE_URL` + a dummy `NEON_DATABASE_URL_RO`).
- **Production (Fly):** `NEON_DATABASE_URL_RO` as a Fly secret; `ENVIRONMENT`/`LOG_LEVEL` plain in
  `fly.toml [env]`; `FLY_API_TOKEN` + a `production` environment in GitHub.

**Local secret-loading model (direnv + Proton Pass).** Two complementary channels:
- **`.envrc` → `dotenv` → `.env`** (direnv): on `cd` into the repo, direnv evaluates `.envrc`, whose
  `dotenv` helper loads `.env`'s `KEY=VALUE` lines into your **ambient shell** (and `PATH_add .venv/bin`
  puts the uv venv on PATH). Use `.env` for **non-secret config only**.
- **`.env.pass` → `pass-cli`** (Proton Pass): `.env.pass` holds only `pass://vault/item/field`
  references (no values — safe to commit). `pass-cli run --env-file .env.pass -- <cmd>` resolves them
  and injects the real values into the **child process only** — never the shell, never plaintext on
  disk. Run the app as:
  `pass-cli run --env-file .env.pass -- uv run uvicorn --factory recalls_api.main:create_app --reload`.
- pydantic-settings precedence is **process env > `.env` file > defaults**, so the pass-cli-injected
  DSN wins and the secret never needs to live in `.env`. (`Settings` uses `extra="ignore"`, so extra
  keys in `.env` won't error.)

**What you do NOT need:** any API-auth secret (open/no-auth API — no JWT/keys/OAuth/`SECRET_KEY`), any
third-party service key, Redis/cache backend (rate-limit is in-memory), write DB creds, cloud/object
storage creds, or TLS cert files (Neon TLS rides the DSN; Fly terminates HTTPS at its proxy).

## Go-live definition of done

- [ ] (A) shows SELECT-only; (B) clean → role is genuinely read-only.
- [ ] `.env` has the real DSN; `uv run uvicorn --factory recalls_api.main:create_app` boots and
      `/health/db` returns 200 against live Neon.
- [ ] Remote added; `main` pushed; CI green.
- [ ] Fly app created; `NEON_DATABASE_URL_RO` set as a Fly secret; `FLY_API_TOKEN` + `production`
      env set in GitHub; `deploy.yml` smoke hostname correct.
- [ ] A push to `main` → CI green → auto-deploy → post-deploy `/health/db` smoke passes.
- [ ] (optional) `pre-commit install` run locally.
