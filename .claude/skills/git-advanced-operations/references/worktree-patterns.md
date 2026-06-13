# Worktree Patterns

## What Are Worktrees?

Git worktrees let you check out multiple branches simultaneously in separate
directories, all sharing the same `.git` repository. No need to stash, clone,
or juggle uncommitted changes.

## Creating Worktrees

```bash
# Basic: check out an existing branch in a new directory
git worktree add ../feature-auth feature/auth

# Create a new branch and check it out in one step
git worktree add -b hotfix/login-crash ../hotfix-login main

# Create from a specific commit or tag
git worktree add ../release-v2 v2.0.0

# Create a detached HEAD worktree (for inspecting a commit)
git worktree add --detach ../inspect-commit abc1234
```

## Listing and Inspecting Worktrees

```bash
# List all worktrees
git worktree list
# /Users/dev/project          abc1234 [main]
# /Users/dev/feature-auth     def5678 [feature/auth]
# /Users/dev/hotfix-login     ghi9012 [hotfix/login-crash]

# Verbose output with prunable info
git worktree list --porcelain
```

## PR Review Workflow

Review a pull request without leaving your current work.

```bash
# You are on main, working on something. A PR comes in for review.

# Step 1: Fetch the PR branch
git fetch origin pull/42/head:pr-42

# Step 2: Create a worktree for the review
git worktree add ../review-pr-42 pr-42

# Step 3: Navigate to the worktree and review
cd ../review-pr-42
# Run tests, inspect code, etc.
pytest tests/
ruff check src/

# Step 4: Go back to your main working directory
cd ../project

# Step 5: Clean up when done
git worktree remove ../review-pr-42
git branch -D pr-42
```

## Parallel Feature Development

Work on two features simultaneously.

```bash
# Main worktree: feature A (your primary work)
# /Users/dev/project  [feature/user-profiles]

# Create worktree for feature B
git worktree add ../project-notifications feature/notifications

# Now you can:
# - Edit feature A in /Users/dev/project
# - Edit feature B in /Users/dev/project-notifications
# - Run tests independently in each directory
# - Commit to each branch from its worktree

# Switch between them in your terminal or open two IDE windows
```

## Hotfix While Mid-Feature

```bash
# You are mid-work on a feature with uncommitted changes.
# A critical bug needs fixing on main.

# No need to stash! Create a worktree from main:
git worktree add -b hotfix/critical-bug ../hotfix main

# Fix the bug in the hotfix worktree
cd ../hotfix
vim src/critical-module.py
git add src/critical-module.py
git commit -m "fix: resolve null pointer in payment processing"
git push origin hotfix/critical-bug

# Go back to your feature work exactly as you left it
cd ../project
# All your uncommitted changes are still here
```

## Long-Running Branches

Maintain persistent worktrees for branches you switch between often.

```bash
# Set up worktrees for your common branches
git worktree add ../project-staging staging
git worktree add ../project-develop develop

# Directory layout:
# ~/repos/project/            [main]
# ~/repos/project-staging/    [staging]
# ~/repos/project-develop/    [develop]

# Each directory can have its own:
# - IDE workspace settings
# - Local environment files
# - Running dev server on different ports
```

## Bare Repository with Worktrees

Use a bare repo as the central point with worktrees for every branch.

```bash
# Clone as bare (no working directory)
git clone --bare https://github.com/org/project.git project.git

cd project.git

# Create worktrees for branches you need
git worktree add ../project-main main
git worktree add ../project-develop develop
git worktree add -b feature/new-api ../project-api develop

# Directory layout:
# ~/repos/project.git/         (bare repo, no working files)
# ~/repos/project-main/        [main]
# ~/repos/project-develop/     [develop]
# ~/repos/project-api/         [feature/new-api]

# Fetch updates from the bare repo
cd ~/repos/project.git
git fetch origin

# Update each worktree
cd ~/repos/project-main && git pull
cd ~/repos/project-develop && git pull
```

## Worktree with Different Configurations

Each worktree can have independent local configurations.

```bash
# Create worktree
git worktree add ../project-test test-branch

# Set worktree-specific config
cd ../project-test
git config --local user.email "test-account@company.com"

# Each worktree has its own:
# - Index (staging area)
# - HEAD
# - Working directory
# But they share:
# - Object database
# - Refs
# - Hooks
# - Config (except --local overrides)
```

## Cleanup and Maintenance

```bash
# Remove a worktree (deletes the directory)
git worktree remove ../review-pr-42

# Force remove if there are uncommitted changes
git worktree remove --force ../abandoned-experiment

# Prune stale worktree metadata (if directory was deleted manually)
git worktree prune

# Dry-run prune to see what would be cleaned
git worktree prune --dry-run

# Check for locked worktrees
git worktree list --porcelain | grep -A2 "locked"
```

## Locking Worktrees

Prevent accidental pruning of worktrees on removable media.

```bash
# Lock a worktree (e.g., on an external drive)
git worktree lock ../external-drive-worktree --reason "On USB drive"

# Unlock when the drive is reconnected
git worktree unlock ../external-drive-worktree
```

## Worktree Limitations

Things to keep in mind:

```bash
# A branch can only be checked out in ONE worktree at a time
git worktree add ../second-main main
# fatal: 'main' is already checked out at '/Users/dev/project'

# Workaround: use a detached HEAD
git worktree add --detach ../inspect-main main

# Submodules require manual initialization in each worktree
cd ../new-worktree
git submodule update --init --recursive

# Worktree paths should be outside the main repo directory
# GOOD: ../review-pr-42
# BAD:  ./worktrees/review-pr-42  (inside the repo)
```

## Scripting with Worktrees

```bash
# Script: run tests on a branch without disrupting current work
run_tests_on_branch() {
    local branch="$1"
    local worktree_dir="/tmp/test-worktree-$$"

    git worktree add "$worktree_dir" "$branch" 2>/dev/null
    (
        cd "$worktree_dir"
        pip install -r requirements.txt -q
        pytest tests/ --tb=short
    )
    local exit_code=$?
    git worktree remove "$worktree_dir" 2>/dev/null
    return $exit_code
}

# Usage:
run_tests_on_branch feature/auth
```

## IDE Integration Tips

```bash
# VS Code: open a worktree as a separate window
code ../review-pr-42

# JetBrains: open as a new project (shares the same VCS root)

# Tip: use a consistent naming convention
# ~/repos/project/              (main worktree)
# ~/repos/project--feature-x/   (double dash separates repo from branch)
# ~/repos/project--hotfix-y/
```
