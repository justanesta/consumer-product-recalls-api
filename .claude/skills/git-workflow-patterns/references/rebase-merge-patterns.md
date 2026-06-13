# Rebase and Merge Patterns

## Interactive Rebase

Interactive rebase is the primary tool for cleaning up commit history before merging to main.

### Basic Interactive Rebase

```bash
# Rebase the last 5 commits interactively
git rebase -i HEAD~5

# Rebase all commits since branching from main
git rebase -i main

# The editor opens with a list of commits (oldest first):
# pick abc1234 feat(auth): add login form
# pick def5678 wip: trying something
# pick 789abcd fix typo
# pick aaa1111 wip: more fixes
# pick bbb2222 feat(auth): add validation

# Available commands:
# pick   (p) = use commit as-is
# reword (r) = use commit but edit the message
# edit   (e) = use commit but stop for amending
# squash (s) = meld into previous commit (keep message)
# fixup  (f) = meld into previous commit (discard message)
# drop   (d) = remove commit entirely
```

### Common Rebase Scenarios

```bash
# Scenario 1: Squash WIP commits into meaningful ones
# pick abc1234 feat(auth): add login form
# fixup def5678 wip: trying something
# fixup 789abcd fix typo
# fixup aaa1111 wip: more fixes
# pick bbb2222 feat(auth): add validation

# Scenario 2: Split a commit into two
# edit abc1234 feat(auth): add login form and validation
# When git stops at that commit:
git reset HEAD~1
git add src/login-form.py
git commit -m "feat(auth): add login form"
git add src/validation.py
git commit -m "feat(auth): add form validation"
git rebase --continue
```

### Autosquash with Fixup Commits

```bash
# Create fixup commits that reference a target
git add src/auth.py
git commit --fixup=abc1234  # Creates "fixup! feat(auth): add login form"

# When ready to clean up, autosquash reorders and marks fixups
git rebase -i --autosquash main

# The editor shows fixups already placed after their targets:
# pick abc1234 feat(auth): add login form
# fixup aaa1111 fixup! feat(auth): add login form
# pick ccc3333 feat(auth): add validation

# Enable autosquash by default
git config --global rebase.autosquash true
```

## Rebasing onto Main

```bash
# Fetch latest main and rebase your feature branch
git fetch origin main
git checkout feat/my-feature
git rebase origin/main

# If conflicts occur:
# 1. Fix the conflicts in each file
# 2. Stage the resolved files
git add src/conflicted-file.py
# 3. Continue the rebase
git rebase --continue

# If rebase goes wrong, abort and return to pre-rebase state
git rebase --abort

# After successful rebase, force-push your branch
git push --force-with-lease origin feat/my-feature
```

### Why --force-with-lease

```bash
# NEVER use --force on shared branches
# --force-with-lease is safer: it fails if someone else pushed

# Safe: force-push your own feature branch after rebase
git push --force-with-lease origin feat/my-feature

# If --force-with-lease fails, someone else pushed to your branch
# Fetch their changes first, then decide how to proceed
git fetch origin feat/my-feature
git log origin/feat/my-feature --oneline -5
```

## Merge Strategies

### Merge Commit (--no-ff)

```bash
# Merge feature branch with a merge commit
git checkout main
git merge --no-ff feat/user-auth

# Result:
#   *   Merge branch 'feat/user-auth'  (merge commit)
#   |\
#   | * feat(auth): add validation
#   | * feat(auth): add login form
#   |/
#   * previous main commit

# Easy to revert the whole feature:
git revert -m 1 <merge-commit>
```

### Squash Merge

```bash
# Squash merge: all branch commits become one
git checkout main
git merge --squash feat/user-auth
git commit -m "feat(auth): add complete user authentication

- Add JWT token generation and validation
- Add login/logout endpoints
- Add authentication middleware

Closes #142"

# Via GitHub CLI
gh pr merge 155 --squash --subject "feat(auth): add user authentication"
```

### Fast-Forward and Rebase Merge

```bash
# Fast-forward merge (only works if no divergence)
git checkout main
git merge --ff-only feat/typo-fix

# Rebase then fast-forward (linear history with individual commits)
git checkout feat/my-feature
git rebase main
git checkout main
git merge --ff-only feat/my-feature
```

## Choosing a Merge Strategy

| Strategy | History | Revert | Use Case |
|----------|---------|--------|----------|
| Merge --no-ff | Branch visible | Easy (revert merge) | Default for features |
| Fast-forward | Linear | Per-commit | Trivial changes |
| Squash | Linear, 1 commit | Very easy | Messy branch history |
| Rebase + merge | Linear, N commits | Per-commit | Clean branch history |

## Handling Rebase Conflicts

```bash
# Start rebase
git rebase origin/main

# Git stops at conflicting commits. Look for markers:
# <<<<<<< HEAD
# database_url = "postgresql://prod-server/mydb"
# =======
# database_url = os.environ["DATABASE_URL"]
# >>>>>>> feat/config-refactor

# Resolve, then stage and continue
git add src/config.py
git rebase --continue

# If a commit becomes empty after resolution, skip it
git rebase --skip
```

### Rerere (Reuse Recorded Resolution)

```bash
# Enable rerere to remember conflict resolutions
git config --global rerere.enabled true

# How it works:
# 1. First time you resolve a conflict, git records the resolution
# 2. Next time the same conflict occurs, git applies it automatically

# View recorded resolutions
git rerere status

# Forget a specific resolution
git rerere forget src/config.py
```

## Advanced Rebase Patterns

### Rebase onto a Different Base

```bash
# Move a branch from one base to another
git rebase --onto main feat/main-feature feat/sub-feature

# Before:
#   main --- A --- B (feat/main-feature)
#                   \
#                    C --- D (feat/sub-feature)
# After:
#   main --- A --- B (feat/main-feature)
#        \
#         C' --- D' (feat/sub-feature, rebased onto main)
```

### Exec During Rebase

```bash
# Run tests after each rebased commit to verify nothing breaks
git rebase -i main --exec "pytest tests/ -x"

# If a test fails, git stops so you can fix the issue
# Then: git rebase --continue
```

## Edge Cases

### Recovering from a Bad Rebase

```bash
# Use reflog to find the pre-rebase state
git reflog
# Look for the entry before the rebase started

# Reset to the pre-rebase state
git reset --hard HEAD@{6}

# Or use ORIG_HEAD (set before rebase)
git reset --hard ORIG_HEAD
```

### Preserving Merge Commits

```bash
# By default, rebase flattens merge commits
# Use --rebase-merges to preserve them
git rebase --rebase-merges main
```

### Merge vs Rebase Decision Tree

```bash
# Use REBASE when:
# - Updating your feature branch from main
# - Cleaning up commits before merge
# - You are the only person working on the branch

# Use MERGE when:
# - Integrating a feature branch into main (--no-ff)
# - Multiple people work on the same branch
# - You need to preserve exact branch history
# - The branch has been shared/reviewed already
```