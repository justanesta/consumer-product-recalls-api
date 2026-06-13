# Deployment Strategies

## Blue-Green Deployment

Blue-green maintains two identical production environments. One is live (blue), the other idle (green). Deploy to idle, verify, then switch traffic.

### Kubernetes Blue-Green with Service Swap

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-blue
  labels:
    app: api
    slot: blue
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
      slot: blue
  template:
    metadata:
      labels:
        app: api
        slot: blue
    spec:
      containers:
        - name: api
          image: registry.example.com/api:v1.0.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
---
# Switch between blue/green by changing selector
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector:
    app: api
    slot: blue  # Change to 'green' to switch traffic
  ports:
    - port: 80
      targetPort: 8080
```

### Blue-Green Swap Script

```bash
#!/usr/bin/env bash
set -euo pipefail

NEW_VERSION="$1"
CURRENT_SLOT=$(kubectl get svc api -o jsonpath='{.spec.selector.slot}')
TARGET_SLOT=$([[ "$CURRENT_SLOT" == "blue" ]] && echo "green" || echo "blue")

echo "Current: $CURRENT_SLOT | Deploying to: $TARGET_SLOT"

kubectl set image "deployment/api-${TARGET_SLOT}" "api=registry.example.com/api:${NEW_VERSION}"
kubectl rollout status "deployment/api-${TARGET_SLOT}" --timeout=300s

# Smoke test idle slot, then switch
kubectl run smoke-test --rm -i --restart=Never \
  --image=curlimages/curl -- \
  curl -sf "http://api-${TARGET_SLOT}.default.svc.cluster.local/healthz"

kubectl patch svc api -p "{\"spec\":{\"selector\":{\"slot\":\"${TARGET_SLOT}\"}}}"
echo "Rollback: kubectl patch svc api -p '{\"spec\":{\"selector\":{\"slot\":\"${CURRENT_SLOT}\"}}}'"
```

## Canary Deployment

Deploy the new version to a small subset of traffic. If metrics are healthy, progressively increase until fully rolled out.

### Istio Traffic Splitting

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: api
spec:
  hosts:
    - api.example.com
  http:
    - route:
        - destination:
            host: api
            subset: stable
          weight: 90
        - destination:
            host: api
            subset: canary
          weight: 10
---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: api
spec:
  host: api
  subsets:
    - name: stable
      labels:
        version: v1.0.0
    - name: canary
      labels:
        version: v1.1.0
```

### Automated Canary with Flagger

```yaml
apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: api
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  service:
    port: 8080
  analysis:
    interval: 1m
    threshold: 5
    maxWeight: 50
    stepWeight: 10
    metrics:
      - name: request-success-rate
        thresholdRange:
          min: 99
        interval: 1m
      - name: request-duration
        thresholdRange:
          max: 500
        interval: 1m
    webhooks:
      - name: smoke-test
        type: pre-rollout
        url: http://flagger-loadtester/
        metadata:
          cmd: curl -sf http://api-canary.default:8080/healthz
```

## Rolling Update

Incrementally replace old instances with new ones. Default Kubernetes strategy, ideal for stateless services.

### Kubernetes Rolling Update

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 6
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 1
  template:
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: api
          image: registry.example.com/api:v2.0.0
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 15"]
```

## Feature Flags

Decouple deployment from release. Deploy code to production but control visibility through configuration.

### Progressive Rollout Script

```bash
#!/usr/bin/env bash
set -euo pipefail

FLAG_KEY="$1"
PERCENTAGES=(1 5 10 25 50 100)

for pct in "${PERCENTAGES[@]}"; do
  echo "Setting $FLAG_KEY to ${pct}%"
  curl -s -X PATCH "https://flags.example.com/api/flags/$FLAG_KEY" \
    -H "Authorization: Bearer $FLAG_API_KEY" \
    -d "{\"rolloutPercentage\": $pct}"

  sleep 300  # Monitor for 5 minutes

  ERROR_RATE=$(curl -s "http://prometheus:9090/api/v1/query" \
    --data-urlencode "query=rate(http_errors_total{feature=\"$FLAG_KEY\"}[5m])" \
    | jq '.data.result[0].value[1] // "0"' -r)

  if (( $(echo "$ERROR_RATE > 0.01" | bc -l) )); then
    echo "Error rate too high. Rolling back flag."
    curl -s -X PATCH "https://flags.example.com/api/flags/$FLAG_KEY" \
      -H "Authorization: Bearer $FLAG_API_KEY" \
      -d '{"rolloutPercentage": 0}'
    exit 1
  fi
done
echo "Rollout complete."
```

## Rollback Patterns

Every deployment needs a rollback plan. Automate rollbacks so they execute in seconds.

### Automated Rollback in CI/CD

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Save current version
        id: current
        run: |
          CURRENT=$(kubectl get deployment/api -o jsonpath='{.spec.template.spec.containers[0].image}')
          echo "image=$CURRENT" >> "$GITHUB_OUTPUT"

      - name: Deploy new version
        run: |
          kubectl set image deployment/api api=app:${{ github.sha }}
          kubectl rollout status deployment/api --timeout=300s

      - name: Verify health
        id: verify
        continue-on-error: true
        run: |
          for i in $(seq 1 5); do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://api.example.com/healthz)
            [[ "$STATUS" != "200" ]] && exit 1
            sleep 10
          done

      - name: Rollback on failure
        if: steps.verify.outcome == 'failure'
        run: |
          kubectl set image deployment/api api=${{ steps.current.outputs.image }}
          kubectl rollout status deployment/api --timeout=300s
          exit 1
```

### Database Migration Safety

```bash
#!/usr/bin/env bash
# Always use expand/contract pattern for migrations
set -euo pipefail

VERSION="$1"

# Step 1: Forward-compatible migration (works with old AND new code)
kubectl run migrate --rm -i --restart=Never \
  --image="app:${VERSION}" -- npm run migrate

# Step 2: Deploy new code
kubectl set image deployment/api api="app:${VERSION}"
kubectl rollout status deployment/api --timeout=300s

# Step 3: Verify — rollback app only, migration stays
if ! curl -sf https://api.example.com/healthz; then
  echo "Rolling back application (migration is backward-compatible)."
  kubectl rollout undo deployment/api
  exit 1
fi
```
