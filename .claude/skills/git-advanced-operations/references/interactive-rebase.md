# Interactive Rebase

## Rebase Commands Overview

When you run `git rebase -i`, each commit gets a command prefix:

| Command | Short | Effect |
|---------|-------|--------|
| `pick` | `p` | Keep the commit as-is |
| `reword` | `r` | Keep the commit but edit its message |
| `edit` | `e` | Pause after applying to amend the commit |
| `squash` | `s` | Meld into previous commit, combine messages |
| `fixup` | `f` | Meld into previous commit, discard this message |
| `drop` | `d` | Remove the commit entirely |

## Squash Workflow

Combine multiple related commits into one clean commit.

```bash
# Start interactive rebase for last 4 commits
git rebase -i HEAD~4

# The editor shows (oldest first):
# pick abc1111 Add user registration endpoint
# pick abc2222 Fix validation bug in registration
# pick abc3333 Add tests for registration
# pick abc4444 Fix test assertion

# Change to squash related commits:
# pick abc1111 Add user registration endpoint
# squash abc2222 Fix validation bug in registration
# pick abc3333 Add tests for registration
# squash abc4444 Fix test assertion

# Save and close. Git opens a new editor for each squash group
# to let you write a combined commit message.
```

## Fixup Workflow

Like squash but automatically discards the fixup commit message.

```bash
# You realize the previous commit has a typo
echo "fixed content" > src/auth.py
git add src/auth.py

# Create a fixup commit targeting the original
git commit --fixup=abc1111

# Later, autosquash arranges fixups automatically
git rebase -i --autosquash HEAD~5

# The editor pre-arranges:
# pick abc1111 Add user registration endpoint
# fixup def1111 fixup! Add user registration endpoint
# pick abc3333 Add tests for registration
```

## Autosquash with Squash Commits

```bash
# Create a squash commit (combines messages, unlike fixup)
git commit --squash=abc1111

# Enable autosquash by default
git config --global rebase.autoSquash true

# Now every `git rebase -i` will auto-arrange fixup/squash commits
```

## Reword

Change a commit message without altering the content.

```bash
git rebase -i HEAD~3

# Change pick to reword:
# reword abc1111 Add user registration endpoint
# pick abc2222 Add tests
# pick abc3333 Update docs

# Save and close. Git pauses at the reword commit
# and opens your editor to modify the message.
```

## Edit Mode: Splitting a Commit

Break one commit into multiple smaller commits.

```bash
git rebase -i HEAD~3

# Mark the commit to split:
# edit abc1111 Add model and controller
# pick abc2222 Add tests

# Git pauses after applying abc1111. Now split it:
git reset HEAD~1

# Stage and commit in logical pieces
git add src/models/user.py
git commit -m "feat(models): add user model"

git add src/controllers/user.py
git commit -m "feat(controllers): add user controller"

# Continue the rebase
git rebase --continue
```

## Edit Mode: Amending a Commit Mid-History

```bash
git rebase -i HEAD~5

# Mark the commit to amend:
# edit abc1111 Add config module

# Git pauses. Make your changes:
vim src/config.py
git add src/config.py
git commit --amend --no-edit

# Continue
git rebase --continue
```

## Drop: Removing Commits

```bash
git rebase -i HEAD~4

# Remove a commit by changing pick to drop (or deleting the line):
# pick abc1111 Add feature
# drop abc2222 WIP debugging (remove this)
# pick abc3333 Add tests
```

## Rebase Onto

Transplant a branch from one base to another.

```bash
# Scenario: feature-b was branched from feature-a, but feature-a
# was merged to main. Now rebase feature-b onto main directly.

# Before:
# main: A---B---C---M (merge of feature-a)
# feature-a:    \-D---E
# feature-b:         \-F---G

git rebase --onto main feature-a feature-b

# After:
# main: A---B---C---M
# feature-b:         \-F'---G'

# General syntax:
# git rebase --onto <new-base> <old-base> <branch>
```

## Rebase Onto for Removing Commits

```bash
# Remove commits C and D from the middle of a branch:
# A---B---C---D---E---F  (feature)
#
# Keep A-B, skip C-D, reapply E-F:
git rebase --onto B D feature

# Result: A---B---E'---F'
```

## Handling Rebase Conflicts

```bash
# When a conflict occurs during rebase:
# 1. Fix the conflicting files
vim src/conflicted-file.py

# 2. Stage the resolved files
git add src/conflicted-file.py

# 3. Continue the rebase
git rebase --continue

# Or abort to return to the pre-rebase state
git rebase --abort

# Or skip the current commit (drops its changes)
git rebase --skip
```

## Rebase Conflict Prevention

```bash
# Enable rerere (reuse recorded resolution)
git config --global rerere.enabled true

# Git records conflict resolutions and auto-applies them
# if the same conflict appears again during future rebases.

# View recorded resolutions
git rerere diff
git rerere status
```

## Preserving Merge Commits

```bash
# By default, rebase linearizes history (drops merge commits).
# Use --rebase-merges to preserve the merge structure:
git rebase -i --rebase-merges main

# The todo list includes special label/merge commands:
# label onto
# reset abc1111
# pick abc2222 feature commit
# label feature-branch
# reset onto
# merge -C abc3333 feature-branch
```

## Safety Tips

```bash
# Always create a backup branch before rebasing
git branch backup/feature-before-rebase

# Check the reflog if something goes wrong
git reflog

# Dry-run: see what commits will be rebased
git log --oneline main..HEAD

# Never rebase commits that exist on a remote shared branch
# unless you coordinate with your team
```

## Common Rebase Scenarios

```bash
# Update feature branch with latest main (preferred over merge)
git fetch origin
git rebase origin/main

# Clean up before opening a PR
git rebase -i $(git merge-base HEAD main)

# Rebase and force-push your own feature branch
git push --force-with-lease origin feature-branch
```
