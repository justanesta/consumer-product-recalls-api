# Git Hooks

## Available Hook Types

| Hook | Trigger | Common Use |
|------|---------|------------|
| `pre-commit` | Before commit is created | Lint, format, check secrets |
| `prepare-commit-msg` | After default message generated | Auto-fill templates |
| `commit-msg` | After user writes message | Enforce message format |
| `post-commit` | After commit is created | Notifications |
| `pre-push` | Before push to remote | Run tests, check branch |
| `pre-rebase` | Before rebase starts | Prevent rebasing shared branches |
| `post-checkout` | After checkout/switch | Install dependencies |
| `post-merge` | After merge completes | Rebuild, install deps |

## Pre-Commit Hook

Runs before a commit is created. Exit non-zero to abort the commit.

```bash
#!/bin/sh
# .git/hooks/pre-commit

# Prevent commits to main/master
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
    echo "ERROR: Direct commits to $BRANCH are not allowed."
    echo "Create a feature branch instead."
    exit 1
fi

# Check for debug statements in staged files
if git diff --cached --name-only | xargs grep -l 'debugger\|console\.log\|breakpoint()' 2>/dev/null; then
    echo "ERROR: Debug statements found in staged files."
    echo "Remove them before committing."
    exit 1
fi

# Check for secrets or credentials
PATTERNS='(password|secret|api_key|token)\s*=\s*["\x27][^"\x27]+'
if git diff --cached -U0 | grep -iE "$PATTERNS" 2>/dev/null; then
    echo "WARNING: Possible credentials detected in staged changes."
    echo "Review before committing."
    exit 1
fi

# Run formatter on staged Python files
STAGED_PY=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$')
if [ -n "$STAGED_PY" ]; then
    ruff format --check $STAGED_PY
    if [ $? -ne 0 ]; then
        echo "Run 'ruff format' to fix formatting."
        exit 1
    fi
fi
```

## Commit-Msg Hook

Validates the commit message. Receives the temp file path as argument.

```bash
#!/bin/sh
# .git/hooks/commit-msg

MSG_FILE="$1"
MSG=$(cat "$MSG_FILE")

# Enforce Conventional Commits format
PATTERN='^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\(.+\))?(!)?: .{1,72}$'
FIRST_LINE=$(head -1 "$MSG_FILE")

if ! echo "$FIRST_LINE" | grep -qE "$PATTERN"; then
    echo "ERROR: Invalid commit message format."
    echo ""
    echo "Expected: <type>(<scope>): <description>"
    echo "Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert"
    echo ""
    echo "Examples:"
    echo "  feat(auth): add OAuth2 login flow"
    echo "  fix: resolve race condition in queue processor"
    echo "  docs(api): update endpoint documentation"
    exit 1
fi

# Enforce maximum line length for body
LINE_NUM=0
while IFS= read -r line; do
    LINE_NUM=$((LINE_NUM + 1))
    if [ $LINE_NUM -gt 1 ] && [ ${#line} -gt 100 ]; then
        echo "ERROR: Line $LINE_NUM exceeds 100 characters."
        exit 1
    fi
done < "$MSG_FILE"
```

## Pre-Push Hook

Runs before pushing. Receives remote name and URL as arguments.

```bash
#!/bin/sh
# .git/hooks/pre-push

REMOTE="$1"
URL="$2"

# Prevent force-push to main
while read local_ref local_sha remote_ref remote_sha; do
    if echo "$remote_ref" | grep -qE 'refs/heads/(main|master|production)'; then
        # Check if this is a force push (non-fast-forward)
        if [ "$remote_sha" != "0000000000000000000000000000000000000000" ]; then
            MERGE_BASE=$(git merge-base "$local_sha" "$remote_sha" 2>/dev/null)
            if [ "$MERGE_BASE" != "$remote_sha" ]; then
                echo "ERROR: Force-pushing to $remote_ref is not allowed."
                exit 1
            fi
        fi
    fi
done

# Run tests before pushing
echo "Running tests before push..."
pytest tests/ --tb=short -q
if [ $? -ne 0 ]; then
    echo "ERROR: Tests failed. Fix them before pushing."
    exit 1
fi
```

## Prepare-Commit-Msg Hook

Auto-populate the commit message template.

```bash
#!/bin/sh
# .git/hooks/prepare-commit-msg

COMMIT_MSG_FILE="$1"
COMMIT_SOURCE="$2"

# Only modify for regular commits (not merge, squash, etc.)
if [ -z "$COMMIT_SOURCE" ]; then
    # Prepend branch name as scope
    BRANCH=$(git rev-parse --abbrev-ref HEAD)
    TICKET=$(echo "$BRANCH" | grep -oE '[A-Z]+-[0-9]+' | head -1)

    if [ -n "$TICKET" ]; then
        # Prepend ticket reference
        sed -i.bak "1s/^/[$TICKET] /" "$COMMIT_MSG_FILE"
        rm -f "${COMMIT_MSG_FILE}.bak"
    fi
fi
```

## Post-Checkout Hook

Runs after `git checkout` or `git switch`.

```bash
#!/bin/sh
# .git/hooks/post-checkout

PREV_HEAD="$1"
NEW_HEAD="$2"
BRANCH_CHECKOUT="$3"  # 1 if branch checkout, 0 if file checkout

if [ "$BRANCH_CHECKOUT" = "1" ]; then
    # Check if dependencies changed
    if git diff "$PREV_HEAD" "$NEW_HEAD" --name-only | grep -q 'requirements.txt\|pyproject.toml'; then
        echo "Dependencies changed. Running pip install..."
        pip install -r requirements.txt
    fi

    if git diff "$PREV_HEAD" "$NEW_HEAD" --name-only | grep -q 'package.json'; then
        echo "Node dependencies changed. Running npm install..."
        npm install
    fi
fi
```

## Husky Setup (Node.js Projects)

Husky manages Git hooks via package.json so the team shares them.

```bash
# Install husky
npm install --save-dev husky

# Initialize husky (creates .husky/ directory)
npx husky init

# The init command creates .husky/pre-commit with "npm test"
# Customize it:
echo "npx lint-staged" > .husky/pre-commit
```

## lint-staged Configuration

Run linters only on staged files for fast feedback.

```json
// package.json
{
  "lint-staged": {
    "*.{js,jsx,ts,tsx}": [
      "eslint --fix",
      "prettier --write"
    ],
    "*.{css,scss}": [
      "prettier --write"
    ],
    "*.py": [
      "ruff check --fix",
      "ruff format"
    ],
    "*.md": [
      "prettier --write"
    ]
  }
}
```

```bash
# Install lint-staged
npm install --save-dev lint-staged

# .husky/pre-commit
npx lint-staged
```

## Sharing Hooks via .githooks Directory

For non-Node projects, commit hooks to the repo.

```bash
# Create a hooks directory in the repo
mkdir -p .githooks

# Move or create hooks there
cp .git/hooks/pre-commit .githooks/pre-commit
cp .git/hooks/commit-msg .githooks/commit-msg

# Configure Git to use the shared directory
git config core.hooksPath .githooks

# Add to the repo so teammates get them automatically
git add .githooks/
git commit -m "chore: add shared Git hooks"

# Teammates configure their local repo:
git config core.hooksPath .githooks
```

## Bypassing Hooks

```bash
# Skip pre-commit and commit-msg hooks (use sparingly)
git commit --no-verify -m "hotfix: emergency patch"

# Skip pre-push hook
git push --no-verify
```

## Debugging Hooks

```bash
# Test a hook manually
bash .git/hooks/pre-commit

# Add debug output: put set -x at the top of the hook script

# Check which hooks are installed
ls -la .git/hooks/ | grep -v '\.sample$'

# Check if custom hooksPath is configured
git config core.hooksPath
```

## Hook Arguments Reference

```
pre-commit:           (no arguments)
prepare-commit-msg:   <msg-file> [<source>] [<sha>]
commit-msg:           <msg-file>
post-commit:          (no arguments)
pre-push:             <remote-name> <remote-url>  (stdin: local/remote ref/sha)
pre-rebase:           <upstream> [<branch>]
post-checkout:        <prev-HEAD> <new-HEAD> <branch-flag>
post-merge:           <squash-flag>
```
