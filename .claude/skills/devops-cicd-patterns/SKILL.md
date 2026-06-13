---
name: DevOps CI/CD Patterns
description: Production-ready patterns for continuous integration and continuous deployment pipelines across GitHub Actions, GitLab CI, and general pipeline design principles.
---

# DevOps CI/CD Patterns

## Core Principles

1. **Automate Everything** — Every step from linting to deployment should be codified in pipeline configuration. Manual steps introduce drift and human error.
2. **Fast Feedback Loops** — Developers should know within minutes whether their change broke something. Prioritize quick checks early in the pipeline.
3. **Reproducibility** — Builds must produce identical artifacts given the same inputs. Pin dependency versions, use immutable base images, and avoid relying on ambient state.
4. **Fail Fast, Fail Loud** — Place the cheapest and most likely-to-fail checks first. Notify the right people immediately on failure.
5. **Security as a First-Class Concern** — Secrets must never appear in logs, artifacts, or version control. Scope credentials to the narrowest permission set possible.

## GitHub Actions Fundamentals

Workflows live in `.github/workflows/` and are triggered by repository events. Structure jobs to maximize parallelism while respecting dependency ordering.

```yaml
# .github/workflows/ci.yml
name: CI Pipeline
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run lint

  test:
    runs-on: ubuntu-latest
    needs: lint
    strategy:
      matrix:
        node-version: [18, 20, 22]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: npm
      - run: npm ci
      - run: npm test
```

See [github-actions-patterns](references/github-actions-patterns.md) for: workflow triggers, matrix builds, reusable workflows, and composite actions.

## GitLab CI Patterns

GitLab CI uses a `.gitlab-ci.yml` file at the repository root. Stages define the execution order, and jobs within the same stage run in parallel by default.

```yaml
# .gitlab-ci.yml
stages:
  - validate
  - test
  - build
  - deploy

variables:
  DOCKER_IMAGE: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA

lint:
  stage: validate
  image: node:20-alpine
  cache:
    key: ${CI_COMMIT_REF_SLUG}-npm
    paths:
      - node_modules/
  script:
    - npm ci --prefer-offline
    - npm run lint
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
```

See [gitlab-ci-patterns](references/gitlab-ci-patterns.md) for: stages, rules, artifacts, caching, environments, and include templates.

## Pipeline Design

A well-designed pipeline follows the principle of progressive confidence: each stage increases certainty that the change is safe to deploy.

```yaml
# Conceptual pipeline flow
# Stage 1: Validate (parallel) ─┬─ lint
#                                ├─ type-check
#                                └─ security-scan
# Stage 2: Test (parallel)    ─┬─ unit-tests
#                               └─ integration-tests
# Stage 3: Build              ── docker-build
# Stage 4: Deploy (sequential)─┬─ staging (auto)
#                               └─ production (manual gate)

# GitHub Actions fan-out / fan-in example
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make test-unit

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - run: make test-integration

  build:
    needs: [unit-tests, integration-tests]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t app:${{ github.sha }} .
```

See [pipeline-design-patterns](references/pipeline-design-patterns.md) for: fan-out/fan-in, conditional stages, manual gates, and notifications.

## Secrets Management

Never hardcode credentials. Use your platform's secrets store and scope access to the environments and branches that need them.

```yaml
# GitHub Actions — environment-scoped secrets
jobs:
  deploy-production:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
      - run: |
          aws ecs update-service \
            --cluster prod \
            --service api \
            --force-new-deployment
```

See [secrets-management](references/secrets-management.md) for: GitHub secrets, Vault integration, OIDC federation, and environment-scoped credentials.

## Deployment Strategies

Choose a deployment strategy based on risk tolerance, rollback speed, and infrastructure capabilities.

```yaml
# Kubernetes rolling update configuration
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      containers:
        - name: api
          image: registry.example.com/api:v2.3.1
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
```

See [deployment-strategies](references/deployment-strategies.md) for: blue-green, canary, rolling updates, feature flags, and rollback patterns.

## Build Caching and Optimization

Caching transforms slow pipelines into fast ones. Cache dependency downloads, build artifacts, and Docker layers aggressively.

```yaml
# GitHub Actions — multi-layer caching
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - uses: actions/cache@v4
        with:
          path: ~/.cache/Cypress
          key: cypress-${{ runner.os }}-${{ hashFiles('package-lock.json') }}

      - run: npm ci --prefer-offline
      - run: npm run build

      - uses: docker/build-push-action@v5
        with:
          context: .
          cache-from: type=gha
          cache-to: type=gha,mode=max
          push: true
          tags: app:${{ github.sha }}
```

## Anti-Patterns

| Avoid | Use Instead |
|---|---|
| Hardcoded secrets in pipeline YAML | Platform secret stores or external vaults |
| Single monolithic job that runs all steps | Parallel jobs with explicit dependency graph |
| Running full test suite on every file change | Path-filtered triggers and affected-test detection |
| Building Docker images without layer caching | `cache-from` / `cache-to` with registry or GHA cache |
| Manual SSH deployments triggered from CI | Declarative deployment tools (Helm, Terraform, ArgoCD) |
| Deploying directly to production without gates | Staged rollouts with environment approvals |
| Using `latest` tag for base images | Pinned image digests or specific version tags |
| Storing build artifacts only in CI runner filesystem | Uploading artifacts to registries or object storage |
| Ignoring flaky tests by re-running pipelines | Quarantining flaky tests and fixing root causes |
| Granting admin-level CI tokens to all jobs | Least-privilege OIDC roles scoped per environment |

## Performance

- **Parallelize independent jobs** — Lint, type-check, and security scans have no dependencies on each other. Run them simultaneously.
- **Cache aggressively** — Dependency installation is often the slowest step. Cache `node_modules`, `.m2`, `pip` wheels, and Docker layers.
- **Use path filters** — Only trigger backend pipelines when backend files change. GitHub Actions `paths:` and GitLab `changes:` rules both support this.
- **Choose right-sized runners** — Larger runners cost more per minute but finish faster. Measure total cost (runner-minutes times price) to find the optimum.
- **Minimize Docker context** — Use `.dockerignore` to exclude test files, docs, and `.git`. Smaller contexts mean faster builds.
- **Split test suites** — Use test sharding or parallel test runners (Jest `--shard`, pytest-xdist) to distribute work across multiple jobs.
- **Avoid redundant checkouts** — Pass artifacts between jobs instead of checking out and rebuilding in every job.

source: DevOps CI/CD best practices — GitHub Actions docs, GitLab CI docs, Kubernetes deployment strategies, OWASP CI/CD security guidelines.
