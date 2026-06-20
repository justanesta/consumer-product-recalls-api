# 0010 - Committed openapi.json snapshot as drift-detection contract; generator is the source of truth

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

> Upstream framing: pipeline ADR 0024 §4 — "FastAPI generator is source of truth; committed `openapi.json` snapshot = contract-test fixture; drift = fail."

## Context

FastAPI generates its OpenAPI schema at runtime from route declarations and Pydantic response models. Any field rename, optionality flip, added or removed parameter, or edited description silently changes what callers see — with no CI signal unless something explicitly compares the before and after.

Without a committed snapshot, a PR can change a response model (e.g., flip `announced_at` from `datetime | None` to `datetime`, rename `recall_event_id`, add a filter param) and merge without any contract gate. The API's three consumer paths — the frontend Astro app (pipeline ADR 0039), optional Schemathesis fuzzing, and any downstream integrator reading `openapi.json` — would see a silent break.

`create_app().openapi()` builds the full schema by introspecting routes and models. Critically, it does not connect to the database: the async pool is created in the lifespan context manager, not at import time, so the factory is safe to call with no real DSN present.

## Decision

1. **`src/recalls_api/export_openapi.py` is the generator.** It calls `create_app().openapi()`, injects a dummy DSN via `os.environ.setdefault` if none is present (so the settings validator does not fail), and serializes the result with `json.dumps(indent=2, ensure_ascii=False)` plus a trailing newline for clean diffs.

2. **`openapi.json` at repo root is the committed contract artifact.** Maintainers regenerate it with `python -m recalls_api.export_openapi` and commit the result as part of any intentional surface change.

3. **CI enforces byte-identical agreement** as a hard gate step (the OpenAPI drift check in `ci.yml`): `uv run python -m recalls_api.export_openapi --check` exits 1 if the generated output differs from the committed file, with a remediation instruction on stderr. No separate job spin-up is needed; `create_app().openapi()` requires no DB, so the step shares the synced environment inline.

4. **A pre-commit hook (`openapi-drift`) runs the same check** on every local commit touching `src/recalls_api/*.py` or `openapi.json` (hook `files:` pattern `^(src/recalls_api/.*\.py|openapi\.json)$`), catching drift before push.

5. **Intentional surface changes follow a fixed ceremony:** update models or routes → run `python -m recalls_api.export_openapi` → commit the updated `openapi.json` in the same PR. The snapshot diff in the PR is the human-readable record of the interface change.

## Consequences

**Positive:**
- Any unintentional schema change fails CI loudly at the `export_openapi --check` step, with a one-line remediation.
- `openapi.json` doubles as the input artifact for Schemathesis fuzzing and for the frontend handoff (see `documentation/frontend-api-docs-handoff.md`).
- No database is required to run the contract check — it is fast, runs early in CI, and is safe in pre-commit.

**Negative / tradeoffs:**
- `create_app()` must never connect to the database at import time or during `.openapi()`. This is an ongoing implementation constraint on `main.py`'s factory pattern; violating it (e.g., eager pool creation) silently breaks CI for anyone without a live DSN.
- The `json.dumps` output order is insertion-stable but not `sort_keys`-sorted, so a Python version upgrade that changes dict ordering in FastAPI's schema assembly could produce a spurious drift failure. Mitigated by pinning Python 3.12 in `pyproject.toml` and the Dockerfile.
- Every intentional surface change requires a two-step commit (change code, regenerate snapshot). Forgetting the second step is caught by the pre-commit hook, but adds a small ceremony cost.
