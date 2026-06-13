---
name: git-workflow-patterns
description: |
  Git workflow patterns for team collaboration and release management. Use this skill when
  setting up branching strategies, writing commit messages, managing pull requests, resolving
  merge conflicts, or automating releases. Covers trunk-based development, Conventional Commits,
  rebasing strategies, and semantic versioning.
---

# Git Workflow Patterns

Practical git workflow patterns for teams emphasizing clean history, safe collaboration, and reliable releases.

## Core Principles

1. **Atomic commits** - Each commit represents one logical change that compiles and passes tests
2. **Clear history** - Commit messages explain why, not what; diffs explain what
3. **Branch hygiene** - Short-lived feature branches, deleted after merge
4. **Linear history where possible** - Rebase feature branches before merging to main
5. **Automate the boring parts** - CI checks, changelog generation, version bumps

## Branching Strategies

**Use trunk-based development for most teams**

```bash
# Create a short-lived feature branch from main
git checkout main
git pull origin main
git checkout -b feat/add-user-auth

# Work on the feature (keep branch lifetime under 2 days)
git add src/auth.py src/middleware.py
git commit -m "feat(auth): add JWT-based user authentication"

# Update from main before pushing
git fetch origin main
git rebase origin/main
git push -u origin feat/add-user-auth
```

Key strategy comparison:
- **Trunk-based**: Everyone commits to main (or short branches). Best for CI/CD and small teams.
- **GitHub Flow**: Feature branches + pull requests into main. Best for open source and mid-size teams.
- **GitFlow**: develop/release/hotfix branches. Best for scheduled releases with strict versioning.

See [branching-strategies.md](references/branching-strategies.md) for:
- Detailed trunk-based development workflow
- GitHub Flow step-by-step
- GitFlow branch naming and lifecycle
- Release branch management

## Commit Message Conventions

**Follow Conventional Commits format**

```bash
# Format: <type>(<scope>): <description>
#
# Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore
# Breaking changes: add ! after type or BREAKING CHANGE in footer

git commit -m "feat(api): add pagination to /users endpoint"
git commit -m "fix(auth): prevent token refresh race condition"
git commit -m "docs(readme): update installation instructions"

# Breaking change
git commit -m "feat(api)!: change response format to JSON:API spec

BREAKING CHANGE: All API responses now follow JSON:API format.
Clients must update their parsers accordingly."
```

Rules:
- Subject line under 72 characters
- Use imperative mood ("add" not "added" or "adds")
- No period at the end of the subject
- Blank line between subject and body
- Body explains why, not what

See [commit-conventions.md](references/commit-conventions.md) for:
- Full Conventional Commits specification
- Semantic commit messages and changelog generation
- Squashing and fixup commit workflows
- Commit message templates

## Pull Request Best Practices

**Keep PRs small and focused on a single concern**

```bash
# Create a PR with a structured description
gh pr create --title "feat(auth): add JWT authentication" --body "$(cat <<'EOF'
## Summary
- Add JWT token generation and validation
- Add authentication middleware for protected routes
- Add refresh token rotation

## Test Plan
- [ ] Unit tests for token generation/validation
- [ ] Integration tests for middleware
- [ ] Manual test: login flow end-to-end

## Related
Closes #142
EOF
)"

# Request specific reviewers
gh pr edit 155 --add-reviewer alice,bob

# Enable auto-merge after CI passes
gh pr merge 155 --auto --squash
```

Guidelines:
- Target under 400 lines changed per PR
- One PR per feature or fix
- Use draft PRs for work-in-progress
- Require at least one approval before merge
- Run CI checks before review

See [pr-best-practices.md](references/pr-best-practices.md) for:
- PR description templates
- Review checklists and guidelines
- Draft PR workflows
- Auto-merge and CI integration

## Rebasing vs Merging

**Rebase feature branches, merge to main**

```bash
# Rebase your feature branch onto latest main
git checkout feat/new-feature
git fetch origin main
git rebase origin/main

# If conflicts arise during rebase
# Fix each conflict, then continue
git add <resolved-files>
git rebase --continue

# Force-push rebased branch (only your own feature branch)
git push --force-with-lease origin feat/new-feature

# Merge to main with a merge commit (preserves branch context)
git checkout main
git merge --no-ff feat/new-feature
```

When to use each:
- **Rebase**: Updating feature branch from main, cleaning up local commits
- **Merge --no-ff**: Integrating feature branch into main (preserves branch history)
- **Squash merge**: When feature branch has messy WIP commits
- **Fast-forward**: Only for trivial single-commit changes

See [rebase-merge-patterns.md](references/rebase-merge-patterns.md) for:
- Interactive rebase for history cleanup
- Merge strategies and when to use each
- Handling rebase conflicts safely
- Squash merge workflows

## Release Management

**Use semantic versioning with automated changelogs**

```bash
# Tag a release following semver
git tag -a v1.2.0 -m "Release v1.2.0: Add user authentication"
git push origin v1.2.0

# Create a GitHub release with auto-generated notes
gh release create v1.2.0 --generate-notes --title "v1.2.0"

# Hotfix workflow
git checkout -b hotfix/v1.2.1 v1.2.0
# ... apply fix ...
git commit -m "fix(auth): patch token expiry vulnerability"
git tag -a v1.2.1 -m "Hotfix v1.2.1: Patch token expiry"
git push origin hotfix/v1.2.1 --tags
```

Versioning rules (MAJOR.MINOR.PATCH):
- **MAJOR**: Breaking changes that require client updates
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

See [release-management.md](references/release-management.md) for:
- Semantic versioning deep dive
- Automated changelog generation
- GitHub Releases and CI/CD automation
- Release branch strategies

## Merge Conflict Resolution

**Resolve conflicts methodically, not hastily**

```bash
# See which files have conflicts
git status

# Use a merge tool for complex conflicts
git mergetool

# For simple conflicts, edit manually
# Look for conflict markers:
#   <<<<<<< HEAD
#   (your changes)
#   =======
#   (incoming changes)
#   >>>>>>> feat/other-branch

# After resolving all conflicts
git add <resolved-files>
git rebase --continue   # if rebasing
git merge --continue    # if merging

# Abort if things go wrong
git rebase --abort
git merge --abort
```

Prevention strategies:
- Keep branches short-lived (under 2 days)
- Rebase frequently from main
- Communicate with teammates about shared files
- Break large changes into smaller PRs

## Anti-Patterns

| Avoid | Use Instead |
|-------|-------------|
| `git push --force` on shared branches | `git push --force-with-lease` on your own branch |
| Long-lived feature branches (weeks) | Short-lived branches merged within 1-2 days |
| Merge commits from main into feature branch | `git rebase origin/main` |
| Vague commit messages ("fix stuff") | Conventional Commits ("fix(auth): resolve token expiry") |
| Giant PRs with 1000+ lines | Small focused PRs under 400 lines |
| Committing directly to main | Feature branches with PR review |
| Manual version bumps | Automated versioning from commit history |
| Resolving conflicts by accepting all theirs/ours | Reviewing each conflict individually |

## Performance

- **Shallow clones for CI**: `git clone --depth 1` speeds up CI pipelines
- **Sparse checkout**: `git sparse-checkout set src/ tests/` for monorepos
- **Git LFS**: Track large binaries with `git lfs track "*.psd"` to keep repo small
- **Commit signing**: Use `git config commit.gpgsign true` without impacting speed
- **Ref cleanup**: Run `git remote prune origin` to remove stale remote branches
- **Garbage collection**: `git gc --aggressive` reclaims space in bloated repos
- **Partial clone**: `git clone --filter=blob:none` for faster initial clone of large repos
- **Fsmonitor**: Enable `git config core.fsmonitor true` for faster status on large worktrees

source: Git workflow best practices for team collaboration