# TODO

## Blog post: `origin/<branch>` (slash) vs `origin <branch>` (space) in git

**Action:** verify this against authoritative git documentation + other sources online, then write it
up as a blog post. The explanation below is a working draft — confirm specifics (esp. error strings,
which vary by git version) before publishing.

### The point (working explanation)

They are **not** synonymous — they're two different syntactic constructs, and which one a command
accepts depends on whether the command **talks to a remote** or **reads a local ref**.

- **`origin <branch>` (space) = two arguments:** `<remote> <refspec>`. Used by commands that open a
  connection to a remote — `git push`, `git fetch`, `git pull`. `origin` is the remote name; the branch
  is a separate refspec argument.
- **`origin/<branch>` (slash) = one argument:** a *remote-tracking ref*
  (`refs/remotes/origin/<branch>`) — your local pointer to where that branch was on origin as of the
  last fetch/push. Used by commands that take a single ref / commit-ish — `git branch -u`,
  `git switch -c <name>`, `git log`, `git merge`, `git diff`, `git reset`.

**Rule of thumb:**
- talks-to-a-remote (push / fetch / pull) → `origin <branch>` (space)
- reads-a-local-ref (branch -u, switch, log, merge, diff, reset) → `origin/<branch>` (slash)

**Why the wrong form errors (the "snag"):**
- `git push origin/feature/x` → git reads `origin/feature/x` as a *remote name* →
  *"does not appear to be a git repository."*
- `git branch -u origin feature/x` → reads upstream = `origin`, branch = `feature/x` →
  *"the requested upstream branch 'origin' does not exist."*

### Research checklist (cite real docs before publishing)

- [ ] `git help push` — the `<repository> <refspec>` argument model + `--set-upstream` (`-u`) semantics.
- [ ] `man gitglossary` — definitions of *refspec*, *remote-tracking branch*, *upstream branch*.
- [ ] `man gitrevisions` — how a `<refname>` like `origin/foo` resolves under `refs/remotes/...`.
- [ ] Pro Git book — "Remote Branches" (ch 3.5) and "Working with Remotes" (ch 2.5).
- [ ] `git config push.autoSetupRemote` + `branch.autoSetupMerge` — how upstream gets set automatically.
- [ ] Refspec deep-dive: `src:dst`, leading `+` (force), e.g. `git push origin local:remote`.
- [ ] Verify the exact error strings across a couple of git versions (wording drifts).

### Blog-post angle

- Hook: "I assumed `origin/feature` and `origin feature` were the same for years — until one errored."
- Core: space = `(remote, refspec)` for network verbs; slash = one remote-tracking ref for local verbs.
- Payoff: one rule + a table of which commands take which form, and the two classic error messages decoded.

## Features

### `/recalls` sort control — `sort` + `order` params

- [ ] Add a `sort=published_at|announced_at` + `order=asc|desc` pair to `GET /recalls`. Small, clean, and
low-risk: the R2 index `(published_at DESC, recall_event_id)` backs both directions (Postgres scans
it backward for ASC), so the change is just flipping the `ORDER BY` direction and the keyset
comparison direction (`<` for DESC → `>` for ASC). Fully keyset-compatible.

Deferred — recency sort on `/recalls/search`: it's intentionally relevance-ranked (`ts_rank_cd
DESC`), which fits that endpoint's use case. Adding a date sort there is a bigger change (needs a
mode-aware cursor toggling relevance vs recency), so not now.
