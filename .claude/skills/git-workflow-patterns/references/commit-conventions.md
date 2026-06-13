# Commit Conventions

## Conventional Commits Specification

The Conventional Commits format provides a structured commit message that enables automated tooling for changelogs, versioning, and release notes.

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

```bash
# Feature: A new feature (triggers MINOR version bump)
git commit -m "feat(auth): add OAuth2 login with Google"

# Fix: A bug fix (triggers PATCH version bump)
git commit -m "fix(api): return 404 instead of 500 for missing resources"

# Docs: Documentation only changes
git commit -m "docs(readme): add deployment instructions"

# Style: Code style changes (formatting, semicolons, etc.)
git commit -m "style(lint): apply prettier formatting to components"

# Refactor: Code change that neither fixes a bug nor adds a feature
git commit -m "refactor(auth): extract token validation into separate module"

# Perf: A code change that improves performance
git commit -m "perf(db): add index on users.email for faster lookups"

# Test: Adding or correcting tests
git commit -m "test(auth): add integration tests for OAuth2 flow"

# Build: Changes to build system or external dependencies
git commit -m "build(deps): upgrade express from 4.18 to 4.19"

# CI: Changes to CI configuration files and scripts
git commit -m "ci(github): add Node 20 to test matrix"

# Chore: Other changes that do not modify src or test files
git commit -m "chore(release): bump version to 2.1.0"
```

### Breaking Changes

```bash
# Using ! after type (short form)
git commit -m "feat(api)!: change authentication to use Bearer tokens"

# Using footer (long form with explanation)
git commit -m "feat(api): migrate to v2 response format

The response envelope has changed from {data, error} to
{result, errors, meta} to align with JSON:API specification.

BREAKING CHANGE: API responses now use JSON:API format.
All clients must update their response parsers.
See migration guide at docs/migration-v2.md"

# Both ! and BREAKING CHANGE footer
git commit -m "refactor(db)!: switch from MongoDB to PostgreSQL

BREAKING CHANGE: Database connection configuration has changed.
Update DB_URL environment variable from mongodb:// to postgresql://"
```

## Multi-Line Commit Messages

```bash
# Use git commit without -m for your editor
git commit
# Opens editor with template

# Or use heredoc for scripting
git commit -m "$(cat <<'EOF'
feat(search): add fuzzy matching to search API

Implement Levenshtein distance-based fuzzy matching for the
search endpoint. This allows users to find results even with
minor typos in their queries.

- Add fuzzy matching algorithm with configurable threshold
- Update search index to support trigram similarity
- Add query parameter `fuzzy=true` to enable fuzzy search

Closes #456
EOF
)"

# Multi-line with -m flags
git commit -m "feat(search): add fuzzy matching" \
  -m "Implement Levenshtein distance-based matching." \
  -m "Closes #456"
```

## Commit Message Templates

```gitconfig
# .gitmessage template file
# <type>(<scope>): <description>
#
# [body]
#
# [footer]
# ---
# Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore
# Scope: api, ui, db, auth, cli, etc.
# Footer: BREAKING CHANGE:, Closes #, Refs #, Co-authored-by:
```

```bash
# Configure the template
git config --local commit.template .gitmessage

# Configure default editor
git config --global core.editor "code --wait"   # VS Code
git config --global core.editor "vim"            # Vim
```

## Squashing Commits

Clean up messy work-in-progress commits before merging.

### Interactive Rebase Squash

```bash
# Squash the last 4 commits into one
git rebase -i HEAD~4

# Editor opens with:
# pick abc1234 feat(auth): add login form
# pick def5678 wip: fix typo
# pick 789abcd wip: add tests
# pick 012efgh fix(auth): handle edge case

# Change to:
# pick abc1234 feat(auth): add login form
# squash def5678 wip: fix typo
# squash 789abcd wip: add tests
# squash 012efgh fix(auth): handle edge case

# Then edit the combined commit message in the next editor screen
```

### Fixup Commits

```bash
# Make a fixup commit that will auto-squash into a target commit
git add src/auth.py
git commit --fixup=abc1234

# This creates a commit: "fixup! feat(auth): add login form"

# Later, autosquash during rebase
git rebase -i --autosquash main

# The fixup commits are automatically reordered and marked
# No need to manually edit the rebase todo list
```

### Squash on Merge

```bash
# Squash merge via CLI (all branch commits become one)
git checkout main
git merge --squash feat/user-auth
git commit -m "feat(auth): add complete user authentication system

- JWT token generation and validation
- Login/logout endpoints
- Password hashing with bcrypt
- Rate limiting on auth endpoints

Closes #142"

# Squash merge via GitHub PR
gh pr merge 155 --squash
```

## Automating Changelog Generation

### Using Conventional Commits for Changelogs

```bash
# Install standard-version (Node.js) or similar tool
npm install -g standard-version

# Generate changelog and bump version automatically
# Reads commit messages since last tag
standard-version

# Output in CHANGELOG.md:
# ## [1.3.0] - 2025-01-15
# ### Features
# * **auth:** add OAuth2 login with Google (abc1234)
# * **search:** add fuzzy matching to search API (def5678)
# ### Bug Fixes
# * **api:** return 404 instead of 500 for missing resources (789abcd)
```

### Commit Validation with Hooks

```bash
# Install commitlint
npm install -g @commitlint/cli @commitlint/config-conventional

# Create commitlint.config.js
# module.exports = {
#   extends: ['@commitlint/config-conventional'],
#   rules: {
#     'scope-enum': [2, 'always', ['api', 'ui', 'db', 'auth', 'cli']],
#     'subject-max-length': [2, 'always', 72],
#   }
# };

# Add as a git hook (using husky or pre-commit)
# .husky/commit-msg:
npx --no -- commitlint --edit "$1"
```

## Edge Cases and Gotchas

### Amending Commits

```bash
# Amend the last commit message (only if not pushed)
git commit --amend -m "fix(auth): correct token expiry calculation"

# Amend with additional files (only if not pushed)
git add forgotten-file.py
git commit --amend --no-edit

# DANGER: Never amend commits that have been pushed to shared branches
# Use a new commit instead
git commit -m "fix(auth): include missing validation check"
```

### Reverting Commits

```bash
# Revert a specific commit (creates a new commit)
git revert abc1234
# Editor opens with message: "Revert "feat(auth): add login form""

# Revert with a clear message
git revert abc1234 --no-edit
git commit --amend -m "revert: remove login form pending security review

Reverts feat(auth): add login form (abc1234)
The login form has an XSS vulnerability that needs
to be fixed before re-deploying."

# Revert a merge commit (specify which parent to keep)
git revert -m 1 <merge-commit-hash>
```

### Co-Authored Commits

```bash
git commit -m "feat(api): add rate limiting middleware

Co-authored-by: Alice Smith <alice@example.com>
Co-authored-by: Bob Jones <bob@example.com>"
```

### Signing Commits

```bash
# Configure GPG signing
git config --global user.signingkey YOUR_GPG_KEY_ID
git config --global commit.gpgsign true

# Sign a specific commit
git commit -S -m "feat(security): add input sanitization"

# Verify commit signatures
git log --show-signature -1
```