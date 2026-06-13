# Branching Strategies

## Trunk-Based Development

The simplest and most CI/CD-friendly strategy. All developers commit to `main` directly or via very short-lived branches (hours to 1-2 days).

### Core Workflow

```bash
# Start from latest main
git checkout main
git pull origin main

# Create a short-lived branch
git checkout -b feat/add-search

# Make atomic commits as you work
git add src/search.py
git commit -m "feat(search): add full-text search query builder"
git add tests/test_search.py
git commit -m "test(search): add query builder unit tests"

# Stay current with main (daily or more)
git fetch origin main
git rebase origin/main

# Push and create PR
git push -u origin feat/add-search
gh pr create --title "feat(search): add full-text search" --body "Closes #98"
```

### Feature Flags for Incomplete Work

```bash
# Commit incomplete features behind a flag
git commit -m "feat(search): add search UI (behind ENABLE_SEARCH flag)

The search UI is functional but not yet styled.
Hidden behind ENABLE_SEARCH environment variable
until design review is complete."
```

### When to Use Trunk-Based

- Teams with strong CI/CD pipelines
- Teams practicing continuous deployment
- Small to mid-size teams (2-15 developers)
- Microservice architectures where each service has its own repo

## GitHub Flow

A branch-based workflow centered on pull requests. Simpler than GitFlow but more structured than pure trunk-based.

### Step-by-Step Workflow

```bash
# 1. Create a descriptive branch from main
git checkout main
git pull origin main
git checkout -b feat/user-notifications

# 2. Commit incrementally with clear messages
git add src/notifications/
git commit -m "feat(notify): add email notification service"
git add src/notifications/templates/
git commit -m "feat(notify): add notification email templates"
git add tests/notifications/
git commit -m "test(notify): add notification service tests"

# 3. Push branch and open PR
git push -u origin feat/user-notifications
gh pr create --title "feat(notify): add email notification system" \
  --body "## Summary
- Email notification service with template support
- Async sending via task queue
- Retry logic for failed deliveries

Closes #203"

# 4. Address review feedback
git add src/notifications/retry.py
git commit -m "fix(notify): add exponential backoff to retry logic"
git push origin feat/user-notifications

# 5. After approval, merge and clean up
gh pr merge --squash
git checkout main
git pull origin main
git branch -d feat/user-notifications
```

### Branch Naming Conventions

```bash
# Feature branches
feat/add-user-auth
feat/search-api
feat/JIRA-1234-user-dashboard

# Bug fix branches
fix/login-timeout
fix/null-pointer-search
fix/GH-567-memory-leak

# Other branch types
docs/api-reference-update
refactor/extract-auth-module
chore/upgrade-dependencies
perf/optimize-query-cache
```

### When to Use GitHub Flow

- Open source projects
- Teams of any size that use pull request reviews
- Projects with continuous delivery to staging/production
- When you need code review gates before merging

## GitFlow

A structured branching model with dedicated branches for features, releases, and hotfixes. Best for projects with scheduled release cycles.

### Branch Structure

```bash
# Permanent branches
main        # Production-ready code, tagged with versions
develop     # Integration branch for features

# Temporary branches
feature/*   # New features, branched from develop
release/*   # Release preparation, branched from develop
hotfix/*    # Emergency fixes, branched from main
```

### Feature Branch Workflow

```bash
# Start a feature from develop
git checkout develop
git pull origin develop
git checkout -b feature/payment-gateway

# Work on the feature
git commit -m "feat(payment): add Stripe integration"
git commit -m "feat(payment): add payment confirmation flow"

# Merge back to develop (no fast-forward to preserve context)
git checkout develop
git merge --no-ff feature/payment-gateway
git push origin develop
git branch -d feature/payment-gateway
```

### Release Branch Workflow

```bash
# Create release branch from develop
git checkout develop
git checkout -b release/2.0.0

# Only bug fixes allowed on release branch
git commit -m "fix(payment): correct currency formatting"
git commit -m "docs: update changelog for v2.0.0"

# Finalize the release
git checkout main
git merge --no-ff release/2.0.0
git tag -a v2.0.0 -m "Release v2.0.0"
git push origin main --tags

# Merge release fixes back to develop
git checkout develop
git merge --no-ff release/2.0.0
git push origin develop

# Clean up
git branch -d release/2.0.0
```

### Hotfix Workflow

```bash
# Create hotfix from main (production)
git checkout main
git checkout -b hotfix/2.0.1

# Apply the fix
git commit -m "fix(payment): patch XSS vulnerability in payment form"

# Merge to both main and develop
git checkout main
git merge --no-ff hotfix/2.0.1
git tag -a v2.0.1 -m "Hotfix v2.0.1"
git push origin main --tags

git checkout develop
git merge --no-ff hotfix/2.0.1
git push origin develop

git branch -d hotfix/2.0.1
```

### When to Use GitFlow

- Projects with scheduled releases (monthly, quarterly)
- Multiple versions in production simultaneously
- Teams that need strict release processes
- Enterprise projects with compliance requirements

## Release Branches

Release branches apply across strategies. They isolate release stabilization from ongoing development.

### Release Branch Patterns

```bash
# Create a release branch when feature-complete
git checkout -b release/3.1.0 develop

# Cherry-pick specific fixes if needed
git cherry-pick abc1234
git cherry-pick def5678

# Stabilize the release (only fixes, no new features)
git commit -m "fix(api): handle null response in edge case"
git commit -m "fix(ui): correct alignment on mobile"

# Tag and merge when ready
git tag -a v3.1.0 -m "Release v3.1.0"
git checkout main
git merge --no-ff release/3.1.0
git push origin main --tags
```

### Support Branches for Older Versions

```bash
# Maintain older versions when customers need them
git checkout -b support/2.x v2.5.0

# Apply critical fixes
git cherry-pick <security-fix-hash>
git commit -m "fix(security): backport auth vulnerability patch"
git tag -a v2.5.1 -m "Security patch v2.5.1"
git push origin support/2.x --tags
```

## Choosing a Strategy

| Factor | Trunk-Based | GitHub Flow | GitFlow |
|--------|-------------|-------------|---------|
| Team size | 2-15 | Any | 5+ |
| Release cadence | Continuous | Continuous | Scheduled |
| Complexity | Low | Medium | High |
| CI/CD maturity | Must be strong | Recommended | Optional |
| Multiple versions | No | No | Yes |
| Code review gate | Optional | Always | Optional |

## Edge Cases

### Monorepo with Multiple Teams

```bash
# Use path-based ownership with CODEOWNERS
# .github/CODEOWNERS
# /services/auth/    @auth-team
# /services/billing/ @billing-team
# /shared/lib/       @platform-team

# Teams use trunk-based with path scoping
git checkout -b feat/auth/add-mfa
# Only touch files in services/auth/
```

### Migrating from GitFlow to Trunk-Based

```bash
# 1. Merge develop into main
git checkout main
git merge develop

# 2. Delete the develop branch
git branch -d develop
git push origin --delete develop

# 3. Set up branch protection on main
gh api repos/{owner}/{repo}/branches/main/protection -X PUT \
  -f required_status_checks='{"strict":true,"contexts":["ci"]}' \
  -f enforce_admins=true \
  -f required_pull_request_reviews='{"required_approving_review_count":1}'

# 4. Adopt feature flags for incomplete work
# 5. Shorten branch lifetimes to 1-2 days
```