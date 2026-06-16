Purpose: the slim operating model for this repo's documentation — what doc types exist, where each fact lives, and when to write an ADR.

# Documentation Operating Model

**Parent:** [`consumer-product-recalls` documentation_model.md](../../consumer-product-recalls/documentation/documentation_model.md) — the full six-type taxonomy (ADR / Vision / Master plan / Phase plan / Branch sequencing / Findings) and the TODO.md graduation rules. This file adapts that model for a smaller, narrower repo.

---

## The one rule

> **Every fact has exactly one home. Other docs point at that home; they never restate it.**

When the same fact lives in two places, one copy goes stale. If you find a fact already owned by another doc, add a link — do not restate it.

---

## Doc types in use here

This repo is a read-only API service. It has no per-source findings, no medallion layers, and no pipeline plans. The doc types that apply:

| Type | Responsibility | Belongs here | NOT here | Home |
|---|---|---|---|---|
| **Reference doc** | Permanent description of a system aspect | How the system works right now | Task lists, plans, data observations | `documentation/<name>.md` |
| **ADR** | One architectural decision + rejected alternatives | Context / Decision / Consequences; inline dated amendments | Task lists, migration logs, runbooks | `documentation/decisions/00NN-kebab-title.md` |
| **Plan** | How to execute one bounded chunk of work | Steps, checklist, "done" markers | Design rationale (→ ADR), per-source findings (none here) | `project_scope/<name>.md` or `project_scope/build/` |
| **TODO.md** | Project-wide loose ends too small for a plan | One-liner per item; `Done YYYY-MM-DD (PR #N)` when complete | Anything that belongs in a plan or ADR | `TODO.md` at repo root |

**What this repo does NOT have** (unlike the pipeline parent):
- Per-source findings directories (no `documentation/cpsc/`, etc.)
- Medallion-layer architecture docs (bronze / silver / gold are pipeline concerns)
- `project_scope/implementation_plan.md` (too small to need a master sequencing index)

---

## Documentation suite — directory index

| File | One-line job |
|---|---|
| [`documentation/documentation_model.md`](documentation_model.md) | This file — operating model for the doc suite |
| [`documentation/architecture.md`](architecture.md) | System shape: request lifecycle, module/layer responsibilities, middleware order, deploy topology; diagrams |
| [`documentation/development.md`](development.md) | Local dev setup, quality gate (ruff/pyright/pytest), test layout, branching strategy, how-to-add-an-endpoint recipe |
| [`documentation/operations.md`](operations.md) | Production runtime + runbook: CI→deploy pipeline, fly.toml config, secrets, health vs readiness, cold-start, rollback, logs |
| [`documentation/data_contract.md`](data_contract.md) | API-side view of the gold read contract: which mart columns the API reads, surrogate-key recipes, response-model↔mart-column mapping, load-bearing invariants, data caveats with root causes |
| [`documentation/api-reference.md`](api-reference.md) | Exhaustive endpoint-by-endpoint reference: every param, curl examples, response fields, status codes, pagination, error envelope, conventions preamble |
| [`documentation/frontend-api-docs-handoff.md`](frontend-api-docs-handoff.md) | How to publish API docs on the Astro website: recommended renderers, handoff brief/checklist for the website builder |
| [`documentation/decisions/README.md`](decisions/README.md) | ADR registry: topic index, numeric index, upstream pipeline ADRs, how to write a new ADR, next free number |
| `documentation/decisions/00NN-*.md` | Individual ADRs (Nygard template; immutable once Accepted) |
| `project_scope/` | Build plans, deployment plan, gold-audit charter, recalls-search plan (see `project_scope/build/00-README-build-guide.md`) |
| `TODO.md` | Project-wide loose ends |

---

## When to write an ADR

Write an ADR when someone reading the code six months later would ask "why did they do it this way and not the obvious alternative?" Trivial choices (variable naming, lint config) do not get ADRs; substantive tradeoffs do.

**Steps:**

1. Reserve the next free number in [`documentation/decisions/README.md`](decisions/README.md) — that file is the sole source of truth for the next number. Do not guess or reserve numbers in plan docs.
2. Create `documentation/decisions/00NN-kebab-case-title.md` using the Nygard template:

```markdown
# 00NN — Title

**Status:** Proposed | Accepted | Superseded by ADR 00MM
**Date:** YYYY-MM-DD

## Context
<!-- Why does this decision need to be made? What forces are in play? -->

## Decision
<!-- What we decided and why. Name the rejected alternatives. -->

## Consequences
<!-- What becomes easier or harder as a result. -->
```

3. Add an entry in the topic index and numeric index in `decisions/README.md`.
4. If the ADR supersedes a prior one, update the old ADR's Status line and add a link. If it amends (original decision stands, needs refinement), add a dated amendment section and update the Status line — do not file a new ADR.

ADRs are **immutable once Accepted**. A decision change means a new ADR that supersedes, not an edit to the old one.

**Upstream pipeline ADRs** that govern this repo (0024, 0025, 0039, 0042) are indexed in [`documentation/decisions/README.md`](decisions/README.md) for reference but live in the pipeline repo. Do not copy their text here — link.

---

## Ownership map (who owns which facts)

Each reference doc owns a named set of facts. If a fact already has an owner, link — do not restate.

| Doc | Owns |
|---|---|
| `architecture.md` | Request lifecycle, module/layer responsibilities, middleware add-order vs execution-order, deploy topology, diagrams |
| `development.md` | Local setup, quality gate, test layout, git branching strategy, how-to-add-an-endpoint recipe, code conventions |
| `operations.md` | CI→deploy pipeline, fly.toml config, secrets handling, health vs readiness, cold-start behavior, cost, rollback, logs/troubleshooting |
| `data_contract.md` | Gold mart columns the API reads, surrogate-key recipes, response-model↔mart-column mapping, load-bearing invariants, data caveat root causes |
| `api-reference.md` | Every endpoint: method+path, all params, curl examples, response fields, status codes, error envelope, pagination, conventions preamble |
| `frontend-api-docs-handoff.md` | How to publish API docs on the website: recommended renderers, handoff brief for the website builder |
| `decisions/README.md` | ADR registry, next free number, upstream pipeline ADR index |

---

## Related

- [`documentation/decisions/README.md`](decisions/README.md) — ADR registry and the sole authority on the next free ADR number
- [Pipeline `documentation/documentation_model.md`](../../consumer-product-recalls/documentation/documentation_model.md) — parent model; full six-type taxonomy, TODO.md rules, plan lifecycle states
