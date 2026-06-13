---
name: git-advanced-operations
description: |
  Advanced Git operations for daily development workflows. Use this skill when performing
  interactive rebases, recovering lost commits, configuring hooks, managing worktrees,
  working with stashes, or setting up Git LFS. Covers reflog recovery, autosquash,
  hook automation, parallel development with worktrees, and large file storage.
---

# Git Advanced Operations

Power-user Git workflows for rewriting history, recovery, automation, and large repo management.

## Core Principles

1. **Understand the object model** - Commits are immutable snapshots; branches are movable pointers; HEAD tracks your current position
2. **Reflog is your safety net** - Every HEAD movement is recorded for 90 days; almost nothing in Git is truly lost
3. **Non-destructive by default** - Prefer operations that create new commits over those that destroy history
4. **Never rewrite shared history** - Only rebase or amend commits that have not been pushed to a shared branch
5. **Automate repetitive checks** - Use hooks to enforce standards before code leaves your machine

## Interactive Rebase

**Rewrite, reorder, squash, and clean up commit history before sharing**

```bash
# Rebase last 5 commits interactively
git rebase -i HEAD~5

# In the editor, change pick to the desired action:
# pick   abc1234 Add user model
# squash abc1235 Fix typo in user model
# reword abc1236 Add auth middleware
# edit   abc1237 Add login endpoint
# drop   abc1238 WIP debugging

# Autosquash: auto-arrange fixup/squash commits
git commit --fixup=abc1234
git rebase -i --autosquash HEAD~5

# Rebase onto a different base branch
git rebase --onto main feature-base feature-branch
```

See [interactive-rebase.md](references/interactive-rebase.md) for:
- Squash vs fixup vs reword workflows
- Edit mode for splitting commits
- Autosquash with `--fixup` and `--squash` commits
- Rebase onto for transplanting branches
- Handling rebase conflicts

## Reflog and Recovery

**Recover lost commits and undo destructive operations**

```bash
# View recent HEAD movements
git reflog --date=relative

# Recover a commit after accidental reset
git reflog
# abc1234 HEAD@{2}: commit: important work
git checkout -b recovery-branch abc1234

# Undo a rebase by resetting to pre-rebase state
git reflog
# abc1234 HEAD@{5}: rebase (start): checkout main
git reset --hard HEAD@{5}

# Recover a deleted branch
git reflog | grep "checkout: moving from deleted-branch"
git checkout -b restored-branch abc1234
```

See [reflog-recovery.md](references/reflog-recovery.md) for:
- Reflog navigation and time-based references
- Recovering commits after reset, rebase, or amend
- Restoring deleted branches and stashes
- Using `git fsck` for dangling objects

## Git Hooks

**Automate checks and enforce standards at key Git events**

```bash
# Pre-commit hook: lint and format before committing
cat > .git/hooks/pre-commit << 'HOOK'
#!/bin/sh
# Run linter on staged files only
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$')
if [ -n "$STAGED_FILES" ]; then
    ruff check $STAGED_FILES || exit 1
    ruff format --check $STAGED_FILES || exit 1
fi
HOOK
chmod +x .git/hooks/pre-commit

# Commit-msg hook: enforce conventional commit format
cat > .git/hooks/commit-msg << 'HOOK'
#!/bin/sh
PATTERN='^(feat|fix|docs|style|refactor|test|chore)(\(.+\))?: .{1,72}$'
if ! head -1 "$1" | grep -qE "$PATTERN"; then
    echo "ERROR: Commit message must follow Conventional Commits format"
    echo "Example: feat(auth): add OAuth2 login flow"
    exit 1
fi
HOOK
chmod +x .git/hooks/commit-msg
```

See [git-hooks.md](references/git-hooks.md) for:
- Pre-push hooks for test enforcement
- Husky and lint-staged setup for team projects
- Sharing hooks via a committed `.githooks/` directory
- All available hook types and their arguments

## Worktrees

**Work on multiple branches simultaneously without stashing or cloning**

```bash
# Create a worktree for reviewing a PR
git worktree add ../review-pr-42 pr-42-feature

# Create a worktree with a new branch
git worktree add -b hotfix/login-bug ../hotfix main

# List active worktrees
git worktree list

# Remove a worktree when done
git worktree remove ../review-pr-42

# Prune stale worktree references
git worktree prune
```

See [worktree-patterns.md](references/worktree-patterns.md) for:
- PR review workflow with worktrees
- Parallel development across features
- Worktree cleanup and maintenance
- Bare repo with worktree-only workflow

## Stash Management

**Save and restore work-in-progress without committing**

```bash
# Stash with a descriptive message
git stash push -m "WIP: refactoring auth middleware"

# Stash only specific files
git stash push -m "partial save" -- src/auth.py src/config.py

# Stash including untracked files
git stash push --include-untracked -m "with new files"

# List stashes and inspect contents
git stash list
git stash show -p stash@{0}

# Apply without removing from stash stack
git stash apply stash@{1}

# Create a branch from a stash
git stash branch new-feature stash@{0}
```

See [stash-lfs-patterns.md](references/stash-lfs-patterns.md) for:
- Partial stash with `--patch`
- Recovering dropped stashes from reflog
- Stash-based workflow patterns

## Git LFS

**Track large binary files without bloating the repository**

```bash
# Install and initialize LFS
git lfs install

# Track file patterns
git lfs track "*.psd" "*.zip" "datasets/*.parquet"

# Verify tracked patterns
cat .gitattributes

# Check LFS status
git lfs status
git lfs ls-files

# Migrate existing large files to LFS
git lfs migrate import --include="*.bin" --everything
```

See [stash-lfs-patterns.md](references/stash-lfs-patterns.md) for:
- LFS setup and migration workflow
- Handling LFS in CI/CD
- Storage and bandwidth considerations

## Anti-Patterns

| Avoid | Use Instead |
|-------|-------------|
| `git push --force` on shared branches | `git push --force-with-lease` to prevent overwriting others' work |
| Rebasing commits already pushed to shared branches | Merge or revert to preserve shared history |
| Giant squash of entire feature branch | Squash related commits into logical units |
| Stashing without messages | `git stash push -m "description"` for identifiable stashes |
| Committing large binaries directly | Git LFS for files over 1 MB |
| Copy-pasting hook scripts between repos | Husky + lint-staged or a shared `.githooks/` directory |
| `git checkout` for everything | `git switch` for branches, `git restore` for files |
| `git reset --hard` without checking reflog | Note the current HEAD hash first, then reset |

## Performance

**Optimizations for large repositories**

```bash
# Partial clone: skip downloading all blobs upfront
git clone --filter=blob:none https://github.com/org/large-repo.git

# Sparse checkout: only materialize needed directories
git sparse-checkout init --cone
git sparse-checkout set src/my-module tests/my-module

# Shallow clone: limit history depth
git clone --depth=1 --single-branch https://github.com/org/repo.git

# Speed up status in large repos
git config core.fsmonitor true
git config core.untrackedCache true

# Maintenance: schedule background optimization
git maintenance start

# Commit graph: speed up log and merge-base operations
git commit-graph write --reachable
```

source: Git documentation, Pro Git book, Git LFS documentation
