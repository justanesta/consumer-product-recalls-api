# Pipeline Design Patterns

## Fan-Out / Fan-In

Fan-out runs independent tasks in parallel. Fan-in waits for all parallel tasks before proceeding.

### GitHub Actions Fan-Out / Fan-In

```yaml
name: CI/CD Pipeline
on:
  push:
    branches: [main]
  pull_request:

jobs:
  # --- Fan-out: parallel validation ---
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run lint

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run type-check

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm audit --audit-level=high

  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm test -- --shard=${{ matrix.shard }}/4

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: testdb
          POSTGRES_PASSWORD: testpass
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run test:integration

  # --- Fan-in: build after all checks pass ---
  build:
    needs: [lint, typecheck, security, unit-tests, integration-tests]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t app:${{ github.sha }} .
      - run: docker push app:${{ github.sha }}

  # --- Sequential deployment ---
  deploy-staging:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: ./deploy.sh staging ${{ github.sha }}

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: ./deploy.sh production ${{ github.sha }}
```

### GitLab CI Fan-Out with DAG

```yaml
stages:
  - validate
  - test
  - build

lint:
  stage: validate
  script: npm run lint

security-scan:
  stage: validate
  script: trivy fs --exit-code 1 .

unit-tests:
  stage: test
  needs: [lint]
  parallel: 4
  script:
    - npm test -- --shard=$CI_NODE_INDEX/$CI_NODE_TOTAL

integration-tests:
  stage: test
  needs: [lint]
  services:
    - postgres:16
  script:
    - npm run test:integration

build:
  stage: build
  needs: [unit-tests, integration-tests, security-scan]
  script:
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA
```

## Conditional Stages

Run different pipeline paths based on what changed, who triggered it, or which branch it runs on.

### Path-Based Conditional Execution

```yaml
name: Monorepo CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      frontend: ${{ steps.filter.outputs.frontend }}
      backend: ${{ steps.filter.outputs.backend }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            frontend:
              - 'frontend/**'
              - 'shared/**'
            backend:
              - 'backend/**'
              - 'shared/**'

  frontend-ci:
    needs: detect-changes
    if: needs.detect-changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npm ci && npm test && npm run build

  backend-ci:
    needs: detect-changes
    if: needs.detect-changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd backend && go test ./... && go build ./cmd/server
```

## Manual Gates

Manual approval gates prevent automated deployments to sensitive environments.

### GitHub Actions Environment Protection

```yaml
jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: ./deploy.sh staging

  smoke-test:
    needs: deploy-staging
    runs-on: ubuntu-latest
    steps:
      - run: ./smoke-test.sh https://staging.example.com

  deploy-production:
    needs: smoke-test
    runs-on: ubuntu-latest
    environment:
      name: production  # Configured with required reviewers
      url: https://example.com
    steps:
      - run: ./deploy.sh production
```

### GitLab CI Manual Gates

```yaml
deploy-staging:
  stage: deploy
  script: ./deploy.sh staging
  environment:
    name: staging

verify-staging:
  stage: deploy
  needs: [deploy-staging]
  script:
    - ./run-smoke-tests.sh $STAGING_URL

deploy-production:
  stage: deploy
  needs: [verify-staging]
  script: ./deploy.sh production
  environment:
    name: production
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      when: manual
  allow_failure: false
```

## Notifications

### Slack Notification on Failure

```yaml
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm test
      - name: Notify Slack on failure
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "*CI Failed* | ${{ github.repository }} | ${{ github.ref_name }}\n<${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}|View Run>"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
          SLACK_WEBHOOK_TYPE: INCOMING_WEBHOOK
```

## Pipeline Optimization

### Test Impact Analysis

```yaml
jobs:
  affected-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: npm ci
      - run: |
          CHANGED_FILES=$(git diff --name-only origin/main...HEAD)
          npx jest --findRelatedTests $CHANGED_FILES --passWithNoTests
```

### Artifact Passing vs Rebuild

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: build-output
          path: dist/
          retention-days: 1

  e2e-tests:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: build-output
          path: dist/
      - run: npm ci && npm run test:e2e
```
