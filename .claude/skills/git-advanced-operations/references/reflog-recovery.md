# Reflog and Recovery

## Understanding the Reflog

The reflog records every time HEAD or a branch tip moves. It is a local-only
safety net -- it is not shared via push/pull. Entries expire after 90 days by
default (30 days for unreachable commits).

```bash
# View HEAD reflog (all HEAD movements)
git reflog

# Output format:
# abc1234 HEAD@{0}: commit: add login feature
# def5678 HEAD@{1}: checkout: moving from main to feature
# ghi9012 HEAD@{2}: pull: Fast-forward

# View reflog for a specific branch
git reflog show main

# View with timestamps
git reflog --date=relative
git reflog --date=iso

# View with full commit details
git reflog --format='%C(auto)%h %gd %gs (%cr) %s'
```

## Time-Based Reflog References

```bash
# Reference by position
git show HEAD@{3}          # 3 moves ago
git show main@{5}          # Branch 5 moves ago

# Reference by time
git show HEAD@{yesterday}
git show HEAD@{2.hours.ago}
git show HEAD@{2024-01-15}
git show main@{one.week.ago}

# Diff against a previous state
git diff HEAD@{1}
git diff main@{yesterday}..main

# Log of what branch pointed to over time
git log -g main --oneline
```

## Recovering Commits After Hard Reset

```bash
# Scenario: you accidentally ran git reset --hard HEAD~3

# Step 1: Find the lost commit in the reflog
git reflog
# abc1234 HEAD@{0}: reset: moving to HEAD~3
# def5678 HEAD@{1}: commit: important work C
# ghi9012 HEAD@{2}: commit: important work B
# jkl3456 HEAD@{3}: commit: important work A

# Step 2: Recover by creating a branch at the lost commit
git checkout -b recovery def5678

# Or restore the branch to where it was:
git reset --hard def5678
```

## Undoing a Bad Rebase

```bash
# Scenario: rebase went wrong and you want to undo it

# Step 1: Find the pre-rebase HEAD in the reflog
git reflog
# abc1234 HEAD@{0}: rebase (finish): returning to refs/heads/feature
# def5678 HEAD@{1}: rebase (pick): add tests
# ghi9012 HEAD@{2}: rebase (squash): add feature
# jkl3456 HEAD@{3}: rebase (start): checkout main
# mno7890 HEAD@{4}: commit: latest commit before rebase  <-- this one

# Step 2: Reset to pre-rebase state
git reset --hard HEAD@{4}
# Or use the commit hash directly:
git reset --hard mno7890
```

## Recovering After Amend

```bash
# Scenario: you amended a commit but want the pre-amend version back

git reflog
# abc1234 HEAD@{0}: commit (amend): updated message
# def5678 HEAD@{1}: commit: original message  <-- pre-amend commit

# The pre-amend commit still exists
git show def5678

# Create a branch from the pre-amend state
git branch pre-amend def5678

# Or cherry-pick the original commit somewhere else
git cherry-pick def5678
```

## Recovering a Deleted Branch

```bash
# Scenario: you deleted a branch by accident
git branch -D feature-important
# Deleted branch feature-important (was abc1234).

# Option 1: Use the hash printed during deletion
git checkout -b feature-important abc1234

# Option 2: Search the reflog
git reflog | grep "feature-important"
# Or search for checkout events:
git reflog | grep "checkout: moving from feature-important"

# Option 3: Search all reflogs
git reflog --all | grep "feature-important"
```

## Recovering a Dropped Stash

```bash
# Scenario: you dropped a stash by accident
git stash drop stash@{0}

# Stashes are commits. Find dangling stash commits:
git fsck --no-reflogs | grep "dangling commit"
# dangling commit abc1234
# dangling commit def5678

# Inspect each to find your stash
git show abc1234

# Apply the recovered stash
git stash apply abc1234
# Or create a branch from it
git checkout -b recovered-stash abc1234
```

## Using git fsck for Deep Recovery

```bash
# Find all unreachable objects (commits, trees, blobs)
git fsck --unreachable

# Find only dangling commits (not referenced by any other object)
git fsck --no-reflogs --dangling

# Show details of dangling commits to identify what you need
git fsck --no-reflogs | grep "dangling commit" | while read _ _ hash; do
    echo "=== $hash ==="
    git log --oneline -1 "$hash"
done

# Once you find the commit you want:
git checkout -b recovery $COMMIT_HASH
```

## Recovering Files from Specific Commits

```bash
# Restore a single file from a previous commit
git checkout abc1234 -- path/to/file.py

# Using the modern command (preferred)
git restore --source=abc1234 path/to/file.py

# Restore a file from reflog reference
git restore --source=HEAD@{5} path/to/file.py

# View a file without checking it out
git show abc1234:path/to/file.py

# Restore an entire directory
git restore --source=abc1234 -- src/
```

## Preventing Accidental Data Loss

```bash
# Create safety aliases
git config --global alias.undo 'reset --soft HEAD~1'
git config --global alias.unstage 'restore --staged'

# Always use --force-with-lease instead of --force
git config --global alias.pushf 'push --force-with-lease'

# Before destructive operations, tag the current state
git tag BEFORE-DANGEROUS-OPERATION

# After confirming everything is fine:
git tag -d BEFORE-DANGEROUS-OPERATION
```

## Reflog Configuration

```bash
# Change expiration for reachable reflog entries (default: 90 days)
git config --global gc.reflogExpire 180.days

# Change expiration for unreachable entries (default: 30 days)
git config --global gc.reflogExpireUnreachable 90.days

# Disable reflog expiration entirely (not recommended for large repos)
git config --global gc.reflogExpire never

# Manually expire old reflog entries
git reflog expire --expire=90.days --all

# Run garbage collection (respects reflog expiry)
git gc --prune=now
```

## Recovery Decision Tree

```
Lost a commit?
  |-- Do you know the hash? --> git checkout -b recovery <hash>
  |-- Was it recent? --> git reflog, find the hash
  |-- Was it on a deleted branch? --> git reflog --all | grep branch-name
  |-- None of the above? --> git fsck --no-reflogs | grep dangling

Lost staged changes (never committed)?
  |-- git fsck --dangling | grep blob
  |-- git show <blob-hash>  (recovers file content, not filename)

Lost stash?
  |-- git fsck --no-reflogs | grep "dangling commit"
  |-- Inspect each, then git stash apply <hash>
```

## Audit Trail with Reflog

```bash
# Trace how a file changed over recent history
git log --follow -p -- path/to/file.py

# See when a branch was last at a particular commit
git reflog show feature-branch | grep abc1234

# Compare current branch to its state at a specific time
git diff main@{1.week.ago}..main --stat
```
