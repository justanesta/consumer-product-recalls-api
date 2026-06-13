# Secrets Management

## GitHub Actions Secrets

GitHub provides three scopes: organization, repository, and environment secrets.

### Repository Secrets

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - run: ./deploy.sh
        env:
          API_KEY: ${{ secrets.DEPLOY_API_KEY }}
```

### Environment-Scoped Secrets

Environment secrets are only available to jobs referencing that environment, preventing staging credentials from being used in production.

```yaml
jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - run: ./deploy.sh staging

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production  # Different secret values, same names
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - run: ./deploy.sh production
```

### Secret Masking and Safety

```yaml
jobs:
  example:
    runs-on: ubuntu-latest
    steps:
      # SAFE — use env vars, never inline secrets in run commands
      - run: curl -H "Authorization: Bearer $API_TOKEN" https://api.example.com
        env:
          API_TOKEN: ${{ secrets.API_TOKEN }}

      # Register dynamic secrets for masking
      - run: |
          TOKEN=$(vault read -field=token secret/data/myapp)
          echo "::add-mask::$TOKEN"
          echo "APP_TOKEN=$TOKEN" >> "$GITHUB_ENV"
```

## OIDC Federation

OIDC eliminates long-lived credentials by letting CI platforms request short-lived tokens from cloud providers.

### AWS OIDC with GitHub Actions

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/github-actions-deploy
          aws-region: us-east-1
          # No access keys — uses OIDC token exchange
      - run: aws ecs update-service --cluster prod --service api --force-new-deployment
```

### GCP Workload Identity Federation

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: projects/123456/locations/global/workloadIdentityPools/github/providers/my-repo
          service_account: deploy@my-project.iam.gserviceaccount.com
      - uses: google-github-actions/setup-gcloud@v2
      - run: gcloud run deploy api --image gcr.io/my-project/api:${{ github.sha }} --region us-central1
```

### Azure OIDC Federation

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - run: az webapp deploy --resource-group myapp --name myapp-api --src-path dist/
```

## HashiCorp Vault Integration

### Vault with GitHub Actions

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: hashicorp/vault-action@v3
        with:
          url: https://vault.example.com
          method: jwt
          role: github-actions-deploy
          jwtGithubAudience: https://vault.example.com
          secrets: |
            secret/data/myapp/production db_password | DB_PASSWORD ;
            secret/data/myapp/production api_key | API_KEY ;
            aws/creds/deploy access_key | AWS_ACCESS_KEY_ID ;
            aws/creds/deploy secret_key | AWS_SECRET_ACCESS_KEY
      - run: ./deploy.sh
        env:
          DATABASE_URL: postgres://app:${{ env.DB_PASSWORD }}@db.example.com/myapp
```

### Vault with GitLab CI

```yaml
deploy:
  stage: deploy
  id_tokens:
    VAULT_ID_TOKEN:
      aud: https://vault.example.com
  secrets:
    DATABASE_PASSWORD:
      vault: myapp/production/db_password@secret
      token: $VAULT_ID_TOKEN
    API_KEY:
      vault: myapp/production/api_key@secret
      token: $VAULT_ID_TOKEN
  script:
    - ./deploy.sh
```

## Edge Cases and Best Practices

### Preventing Secret Leakage

```yaml
jobs:
  safe-deploy:
    runs-on: ubuntu-latest
    steps:
      - run: |
          # Redirect output that might contain secrets
          ./configure.sh > /dev/null 2>&1
          # Use set +x to prevent bash from echoing commands
          set +x
          export AUTH_HEADER="Bearer $API_TOKEN"
          curl -H "Authorization: $AUTH_HEADER" https://api.example.com/deploy
        env:
          API_TOKEN: ${{ secrets.API_TOKEN }}
```

### Rotating Secrets

```bash
#!/usr/bin/env bash
set -euo pipefail

NEW_SECRET=$(openssl rand -base64 32)

curl -X PUT "https://api.example.com/admin/rotate-key" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d "{\"new_key\": \"$NEW_SECRET\"}"

gh secret set API_KEY --body "$NEW_SECRET" --repo my-org/my-repo
echo "Secret rotated successfully"
```

### Least Privilege Token Scoping

```yaml
jobs:
  read-only-job:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: read
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm test

  publish-job:
    needs: read-only-job
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - run: npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```
