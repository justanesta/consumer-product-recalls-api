# Pull Request Best Practices

## PR Size Guidelines

Keep pull requests small, focused, and reviewable. Large PRs lead to superficial reviews and missed bugs.

```bash
# Check the size of your PR before opening
git diff --stat main..HEAD

# Ideal PR metrics
# - Under 400 lines changed
# - Under 10 files changed
# - One logical change per PR
# - Can be reviewed in under 30 minutes

# If your PR is too large, split it
# Example: Split a "user auth" feature into:
#   PR 1: Add user model and database migration
#   PR 2: Add authentication service and JWT logic
#   PR 3: Add login/logout API endpoints
#   PR 4: Add auth middleware and route protection
```

## PR Description Templates

### GitHub PR Template

```markdown
<!-- .github/pull_request_template.md -->
## Summary
<!-- Describe what this PR does and why -->

## Changes
<!-- List the key changes -->
-

## Test Plan
<!-- How was this tested? -->
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Screenshots
<!-- If applicable, add screenshots -->

## Related Issues
<!-- Link related issues: Closes #123, Refs #456 -->
```

### Creating PRs with Structured Descriptions

```bash
# Create PR with full description
gh pr create --title "feat(auth): add JWT authentication" --body "$(cat <<'EOF'
## Summary
Add JWT-based authentication with refresh token rotation.

## Changes
- Add JWT token generation with RS256 signing
- Add refresh token rotation (single-use tokens)
- Add authentication middleware for protected routes

## Test Plan
- [x] Unit tests for token generation and validation
- [x] Integration tests for auth middleware
- [ ] Manual test: full login/refresh/logout flow

## Related Issues
Closes #142
EOF
)"
```

## Review Checklists

### For PR Authors

```bash
# Self-review checklist before requesting review:

# 1. Tests pass
pytest tests/ -v
npm test

# 2. Linting passes
ruff check src/
eslint src/

# 3. No unintended changes
git diff --stat main..HEAD
git diff main..HEAD -- '*.lock'  # Check for lock file changes

# 4. Sensitive data check
git diff main..HEAD | grep -i "password\|secret\|api_key\|token"

# 5. Documentation updated if needed
git diff --name-only main..HEAD | grep -E '\.(md|rst|txt)$'
```

### For Reviewers

```bash
# Review the PR diff
gh pr diff 155

# Check the full file context (not just the diff)
gh pr diff 155 --patch

# Leave review comments
gh pr review 155 --comment --body "Looks good overall. A few suggestions inline."

# Approve or request changes
gh pr review 155 --approve
gh pr review 155 --request-changes --body "Please address the security concern in auth.py"
```

Review focus areas:
- **Correctness**: Does the code do what it claims?
- **Security**: SQL injection, XSS, auth bypass, secrets in code?
- **Performance**: N+1 queries, missing indexes, unbounded loops?
- **Error handling**: Are failures handled gracefully?
- **Tests**: Are edge cases covered? Are tests meaningful?

## Draft PRs

Use draft PRs for early feedback and visibility into work-in-progress.

```bash
# Create a draft PR
gh pr create --draft --title "WIP: feat(billing): add subscription management" \
  --body "$(cat <<'EOF'
## Status: Work in Progress

### Done
- [x] Subscription model and migrations
- [x] Stripe integration for payment processing

### In Progress
- [ ] Webhook handlers for subscription events

### Questions for Reviewers
1. Should we support annual billing from day one?
2. Preference on webhook retry strategy?
EOF
)"

# Convert draft to ready for review
gh pr ready 155

# Convert back to draft if needed
gh pr ready 155 --undo
```

## Auto-Merge and CI Integration

### Branch Protection Rules

```bash
# Configure branch protection via GitHub API
gh api repos/{owner}/{repo}/branches/main/protection -X PUT \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["ci/tests", "ci/lint", "ci/security-scan"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true
  },
  "required_linear_history": true,
  "allow_force_pushes": false
}
EOF
```

### Auto-Merge Setup

```bash
# Enable auto-merge on a PR (merges when all checks pass)
gh pr merge 155 --auto --squash

# Auto-merge with specific merge strategy
gh pr merge 155 --auto --merge      # Merge commit
gh pr merge 155 --auto --rebase     # Rebase and merge

# Disable auto-merge
gh pr merge 155 --disable-auto
```

## CODEOWNERS

Automatically assign reviewers based on file paths.

```bash
# .github/CODEOWNERS

# Global owners (fallback)
*                       @team-lead

# Frontend
/src/components/        @frontend-team
/src/styles/            @frontend-team

# Backend
/src/api/               @backend-team
/src/services/          @backend-team

# Infrastructure
/infra/                 @devops-team
Dockerfile              @devops-team
.github/workflows/      @devops-team

# Database
/migrations/            @dba-team @backend-team
```

## Edge Cases

### Dependent PRs (Stacked PRs)

```bash
# PR 1: Base feature (targets main)
git checkout -b feat/auth-model
git push -u origin feat/auth-model
gh pr create --base main --title "feat(auth): add user model"

# PR 2: Depends on PR 1 (targets PR 1 branch)
git checkout -b feat/auth-service feat/auth-model
git push -u origin feat/auth-service
gh pr create --base feat/auth-model --title "feat(auth): add auth service"

# After PR 1 merges, retarget PR 2 to main
gh pr edit 156 --base main
git checkout feat/auth-service
git rebase main
git push --force-with-lease origin feat/auth-service
```

### Reverting a Merged PR

```bash
# Create a revert PR for review
git checkout -b revert/pr-155
git revert -m 1 <merge-commit-hash>
git push -u origin revert/pr-155
gh pr create --title "revert: undo PR #155 (auth changes)" \
  --body "Reverting #155 due to production errors. See incident #42."
```

### Handling Stale PRs

```bash
# List PRs older than 14 days
gh pr list --state open --json number,title,createdAt \
  --jq '.[] | select(
    (now - (.createdAt | fromdateiso8601)) > (14 * 86400)
  ) | "\(.number): \(.title)"'

# Add a comment nudging the author
gh pr comment 123 --body "This PR has been open for 2+ weeks. Please update or close."

# Close stale PRs with explanation
gh pr close 123 --comment "Closing due to inactivity. Please reopen if still needed."
```