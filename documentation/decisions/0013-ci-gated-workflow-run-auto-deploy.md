# 0013 - CI-gated auto-deploy: workflow_run trigger on CI success; scale-to-zero on Fly.io

**Status:** Accepted (2026-06-15)  /  **Date:** 2026-06-15

> Upstream framing: pipeline ADR 0025 (`0025-api-deployment-target.md`) chose Fly.io as the primary deploy target and Render as the documented fallback. This ADR records how the CD pipeline is wired to that target.

## Context

Every push to `main` should reach production automatically, but only after the full quality gate passes. The naive approach — a single workflow with CI steps followed by a deploy step — does not prevent deploy on a failing test unless an explicit `if:` guard is added to every downstream step. A separate `workflow_run` trigger gives a hard structural gate: the deploy job cannot start until the CI workflow completes with `conclusion == 'success'`.

A second concern is the two-cold-start stack. Fly.io scale-to-zero (`min_machines_running=0`) eliminates fixed compute cost on the free tier, but it means a deploy readiness check may land while both the Fly machine and the Neon auto-suspend compute are waking. A single-attempt smoke will spuriously fail; a retry loop is required.

A third concern is secrets hygiene. `NEON_DATABASE_URL_RO` must never appear in `fly.toml`, in CI env blocks, or in build args — only the Fly runtime should inject it.

## Decision

1. **Two workflows.** `ci.yml` triggers on `push` and `pull_request` to `main`; `deploy.yml` triggers on `workflow_run: CI completed` restricted to `main`. The deploy job carries `if: github.event.workflow_run.conclusion == 'success'`, making a red CI a structural — not a conditional — deploy block. (`.github/workflows/ci.yml:3-7`, `.github/workflows/deploy.yml:4-15`)

2. **CI gate steps:** the full six-step quality gate documented in [development.md](../development.md#quality-gate) must pass. (`.github/workflows/ci.yml:44-63`)

3. **Exact-SHA deploy.** `deploy.yml` checks out `github.event.workflow_run.head_sha` — the commit CI actually passed — not the current `HEAD`. This prevents a race where a new push lands between CI completion and deploy start. (`.github/workflows/deploy.yml:24`)

4. **Remote build with `GIT_SHA` injection.** `flyctl deploy --remote-only --build-arg GIT_SHA=<sha>` builds the image on Fly's builder and bakes the SHA into the `GIT_SHA` env var (used as the ETag `startup_id` component; it is not written to an OCI image label). (`.github/workflows/deploy.yml:27`)

5. **Secrets posture.** `FLY_API_TOKEN` is a GitHub secret scoped to the `production` environment, passed via `env:`, never inlined in a `run:` string. `NEON_DATABASE_URL_RO` is a Fly runtime secret set out-of-band via `flyctl secrets set` and is never present in `fly.toml`, CI env blocks, or build args. (`.github/workflows/deploy.yml:17-30`)

6. **Post-deploy readiness smoke.** A retry loop hits `GET /health/db` (not `/health`) up to 5 times with 10 s gaps, then exits 1 on failure. `/health/db` is used because it exercises the Neon connection; `/health` is process-only and would pass before Neon wakes. (`.github/workflows/deploy.yml:31-40`)

7. **No parallel deploys.** `concurrency: group: deploy-production, cancel-in-progress: false` ensures in-flight deploys are never cancelled by a newer push. (`.github/workflows/deploy.yml:18-20`)

8. **Render fallback is documented, not wired.** `render.yaml` exists as a documented fallback stub (`runtime: docker`, `healthCheckPath: /health`, `NEON_DATABASE_URL_RO sync: false`) but is not connected to CI; activating it requires only pointing the Render dashboard at the repo.

## Consequences

**Accepted tradeoffs:**

- The `workflow_run` trigger introduces a small delay (CI must fully complete before deploy starts) — acceptable for a non-latency-sensitive deploy cadence.
- The post-deploy smoke retry loop (5 × 10 s = up to 50 s) does not auto-rollback on failure in v1; a failed smoke is surfaced as a failed workflow step requiring manual `flyctl releases rollback`.
- `min_machines_running=0` (scale-to-zero) means the first request after an idle period pays both cold starts. Raising to `min_machines_running=1` is the documented lever when a website SLO is committed; it is a `fly.toml` change, not a code change.
- The spec in `project_scope/build/06-deployment-and-ops.md:870-872` shows an `on: push: branches: [main]` trigger; the shipped `deploy.yml` uses `on: workflow_run` instead. The shipped version is strictly safer and supersedes the spec.

**Benefits:**

- A broken test produces zero deploys with no conditional guard needed in the deploy job.
- `NEON_DATABASE_URL_RO` is never visible to any CI worker; only the Fly runtime injects it.
- `GIT_SHA` in the image enables stable ETags across restarts of the same deploy, matching clients' conditional-GET expectations.
