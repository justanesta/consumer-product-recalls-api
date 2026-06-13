# GitLab CI Patterns

## Stages and Job Structure

GitLab CI pipelines are defined in `.gitlab-ci.yml`. Stages execute sequentially; jobs within the same stage run in parallel.

```yaml
stages:
  - validate
  - test
  - build
  - deploy

default:
  image: node:20-alpine
  before_script:
    - npm ci --prefer-offline

lint:
  stage: validate
  script:
    - npm run lint

unit-tests:
  stage: test
  script:
    - npm test -- --coverage
  artifacts:
    reports:
      junit: test-results/junit.xml

build:
  stage: build
  script:
    - npm run build
  artifacts:
    paths:
      - dist/
    expire_in: 1 hour
```

## Rules and Conditional Execution

Rules provide fine-grained control over when jobs run, replacing the older `only/except` syntax.

### Common Rule Patterns

```yaml
# Merge requests and default branch
lint:
  stage: validate
  script: npm run lint
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH

# Run only when specific files change
backend-tests:
  stage: test
  script: cd backend && make test
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
      changes:
        - backend/**/*
        - shared/proto/**/*
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH

# Manual deployment with blocking gate
deploy-production:
  stage: deploy
  script: ./deploy.sh production
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      when: manual
  allow_failure: false

# Variables in rules
deploy:
  stage: deploy
  script: ./deploy.sh $DEPLOY_ENV
  rules:
    - if: $DEPLOY_ENV == "production" && $CI_COMMIT_TAG
      when: manual
    - if: $DEPLOY_ENV == "staging" && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
    - when: never
```

## Artifacts

Artifacts pass data between jobs and stages.

```yaml
build-app:
  stage: build
  script:
    - npm run build
    - tar czf app-$CI_COMMIT_SHORT_SHA.tar.gz dist/
  artifacts:
    paths:
      - dist/
      - app-$CI_COMMIT_SHORT_SHA.tar.gz
    reports:
      junit: test-results/*.xml
      dotenv: build.env
    expire_in: 7 days

# Pass variables between jobs via dotenv
prepare-deploy:
  stage: build
  script:
    - echo "IMAGE_TAG=$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA" >> build.env
  artifacts:
    reports:
      dotenv: build.env

deploy:
  stage: deploy
  needs: [prepare-deploy]
  script:
    - echo "Deploying $IMAGE_TAG"
    - kubectl set image deployment/api api=$IMAGE_TAG
```

## Caching

Caching persists files between pipeline runs to speed up dependency installation.

```yaml
variables:
  NPM_CONFIG_CACHE: $CI_PROJECT_DIR/.npm-cache

default:
  cache:
    key:
      files:
        - package-lock.json
    paths:
      - .npm-cache/
    policy: pull

install-deps:
  stage: validate
  cache:
    key:
      files:
        - package-lock.json
    paths:
      - .npm-cache/
      - node_modules/
    policy: pull-push  # This job populates the cache
  script:
    - npm ci --prefer-offline

# Cache vs Artifacts:
# CACHE: dependencies that rarely change (node_modules, pip packages)
# ARTIFACTS: outputs that downstream jobs need (build files, test reports)
```

## Environments

Environments track deployments and provide history, rollback, and scoped variables.

```yaml
deploy-staging:
  stage: deploy
  script:
    - helm upgrade --install api ./charts/api
      --set image.tag=$CI_COMMIT_SHORT_SHA --namespace staging
  environment:
    name: staging
    url: https://staging.example.com
    on_stop: stop-staging
    auto_stop_in: 1 week
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH

stop-staging:
  stage: deploy
  script: helm uninstall api --namespace staging
  environment:
    name: staging
    action: stop
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      when: manual

deploy-production:
  stage: deploy
  script:
    - helm upgrade --install api ./charts/api
      --set image.tag=$CI_COMMIT_SHORT_SHA --namespace production
  environment:
    name: production
    url: https://example.com
  rules:
    - if: $CI_COMMIT_TAG =~ /^v\d+\.\d+\.\d+$/
      when: manual
  allow_failure: false
```

## Include and Templates

### Include Patterns

```yaml
include:
  - local: .gitlab/ci/test.yml
  - local: .gitlab/ci/deploy.yml
  - project: devops/ci-templates
    ref: v2.1.0
    file:
      - /templates/docker-build.yml
      - /templates/helm-deploy.yml
  - template: Security/SAST.gitlab-ci.yml
```

### Extends for Job Templates

```yaml
.deploy-template:
  image: bitnami/kubectl:latest
  before_script:
    - kubectl config use-context $KUBE_CONTEXT
  script:
    - kubectl set image deployment/$SERVICE $SERVICE=$IMAGE_TAG
    - kubectl rollout status deployment/$SERVICE --timeout=300s
  retry:
    max: 2
    when: [runner_system_failure, stuck_or_timeout_failure]

deploy-api-staging:
  extends: .deploy-template
  stage: deploy
  variables:
    KUBE_CONTEXT: staging
    SERVICE: api
    IMAGE_TAG: $CI_REGISTRY_IMAGE/api:$CI_COMMIT_SHORT_SHA
  environment:
    name: staging
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH

deploy-api-production:
  extends: .deploy-template
  stage: deploy
  variables:
    KUBE_CONTEXT: production
    SERVICE: api
    IMAGE_TAG: $CI_REGISTRY_IMAGE/api:$CI_COMMIT_TAG
  environment:
    name: production
  rules:
    - if: $CI_COMMIT_TAG =~ /^v\d+/
      when: manual
```

## DAG Mode with Needs

```yaml
stages:
  - build
  - test
  - deploy

build-frontend:
  stage: build
  script: make build-frontend

build-backend:
  stage: build
  script: make build-backend

test-frontend:
  stage: test
  needs: [build-frontend]
  script: make test-frontend

test-backend:
  stage: test
  needs: [build-backend]
  script: make test-backend

deploy:
  stage: deploy
  needs: [test-frontend, test-backend]
  script: make deploy
```

## Retry and Timeout

```yaml
flaky-e2e:
  stage: test
  timeout: 20 minutes
  retry:
    max: 2
    when: [script_failure, runner_system_failure]
  script:
    - npm run test:e2e
```
