# GitHub Actions Patterns

## Workflow Triggers

GitHub Actions supports a wide range of event triggers. Combine them to cover all entry points.

### Push and Pull Request with Path Filters

```yaml
on:
  push:
    branches: [main, release/*]
    paths:
      - 'src/**'
      - 'package.json'
      - '.github/workflows/ci.yml'
  pull_request:
    branches: [main]
    paths-ignore:
      - 'docs/**'
      - '*.md'
```

### Scheduled and Manual Triggers

```yaml
on:
  schedule:
    - cron: '0 2 * * *'  # Nightly at 2 AM UTC
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        type: choice
        options: [staging, production]
      dry_run:
        type: boolean
        default: false
```

### Cross-Workflow Triggers

```yaml
on:
  workflow_run:
    workflows: ["CI Pipeline"]
    types: [completed]
    branches: [main]

jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
      - run: echo "CI passed, starting deployment"
```

## Matrix Builds

### Multi-Dimensional Matrix

```yaml
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        node-version: [18, 20, 22]
        exclude:
          - os: windows-latest
            node-version: 18
        include:
          - os: ubuntu-latest
            node-version: 22
            coverage: true
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
      - run: npm ci && npm test
      - if: matrix.coverage
        run: npm run test:coverage
```

### Dynamic Matrix from JSON

```yaml
jobs:
  prepare:
    runs-on: ubuntu-latest
    outputs:
      services: ${{ steps.detect.outputs.services }}
    steps:
      - uses: actions/checkout@v4
      - id: detect
        run: |
          SERVICES=$(find services/ -name "Dockerfile" -exec dirname {} \; \
            | jq -R -s -c 'split("\n") | map(select(. != ""))')
          echo "services=$SERVICES" >> "$GITHUB_OUTPUT"

  build:
    needs: prepare
    if: needs.prepare.outputs.services != '[]'
    strategy:
      matrix:
        service: ${{ fromJson(needs.prepare.outputs.services) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t ${{ matrix.service }}:${{ github.sha }} ${{ matrix.service }}
```

## Reusable Workflows

Define a workflow with `workflow_call` trigger and call it from other workflows.

### Defining a Reusable Workflow

```yaml
# .github/workflows/reusable-docker-build.yml
on:
  workflow_call:
    inputs:
      image_name:
        required: true
        type: string
      context:
        required: false
        type: string
        default: '.'
    secrets:
      REGISTRY_PASSWORD:
        required: true
    outputs:
      image_tag:
        value: ${{ jobs.build.outputs.tag }}

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      tag: ${{ steps.meta.outputs.tags }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          username: ${{ github.actor }}
          password: ${{ secrets.REGISTRY_PASSWORD }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ inputs.image_name }}
          tags: |
            type=sha
            type=ref,event=branch
      - uses: docker/build-push-action@v5
        with:
          context: ${{ inputs.context }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### Calling a Reusable Workflow

```yaml
jobs:
  build-api:
    uses: my-org/shared-workflows/.github/workflows/reusable-docker-build.yml@v2
    with:
      image_name: ghcr.io/my-org/api
      context: ./services/api
    secrets:
      REGISTRY_PASSWORD: ${{ secrets.GHCR_TOKEN }}

  deploy:
    needs: build-api
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying ${{ needs.build-api.outputs.image_tag }}"
```

## Composite Actions

Bundle multiple steps into a single reusable action.

```yaml
# .github/actions/setup-project/action.yml
name: Setup Project
inputs:
  node-version:
    required: false
    default: '20'
runs:
  using: composite
  steps:
    - uses: actions/setup-node@v4
      with:
        node-version: ${{ inputs.node-version }}
        cache: npm
    - shell: bash
      run: npm ci --prefer-offline
    - uses: actions/cache@v4
      with:
        path: .next/cache
        key: nextjs-${{ runner.os }}-${{ hashFiles('package-lock.json') }}-${{ hashFiles('src/**') }}
        restore-keys: |
          nextjs-${{ runner.os }}-${{ hashFiles('package-lock.json') }}-
```

### Using the Composite Action

```yaml
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-project
        with:
          node-version: '22'
      - run: npm run lint && npm test && npm run build
```

## Edge Cases and Tips

### Concurrency Control

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

### Conditional Job Execution

```yaml
jobs:
  deploy:
    if: |
      github.event_name == 'push' &&
      github.ref == 'refs/heads/main' &&
      !contains(github.event.head_commit.message, '[skip deploy]')
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying to production"
```

### Passing Data Between Jobs

```yaml
jobs:
  version:
    runs-on: ubuntu-latest
    outputs:
      semver: ${{ steps.bump.outputs.new_version }}
    steps:
      - id: bump
        run: echo "new_version=1.2.3" >> "$GITHUB_OUTPUT"

  publish:
    needs: version
    runs-on: ubuntu-latest
    steps:
      - run: echo "Publishing version ${{ needs.version.outputs.semver }}"
```

### Timeout and Retry

```yaml
jobs:
  flaky-integration:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: nick-fields/retry@v3
        with:
          max_attempts: 3
          timeout_minutes: 5
          command: npm run test:e2e
```
