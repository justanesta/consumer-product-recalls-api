# Release Management

## Semantic Versioning (SemVer)

Semantic versioning provides a clear contract for version numbers: `MAJOR.MINOR.PATCH`.

### Version Components

```bash
# MAJOR: Breaking changes that require consumer updates
# v1.0.0 -> v2.0.0
# Examples: removed API endpoints, changed response format, renamed config keys

# MINOR: New features, backward compatible
# v1.0.0 -> v1.1.0
# Examples: new API endpoint, new optional parameter, new configuration option

# PATCH: Bug fixes, backward compatible
# v1.0.0 -> v1.0.1
# Examples: fix calculation error, fix null pointer, fix typo in output

# Pre-release versions
v2.0.0-alpha.1    # Early testing, unstable
v2.0.0-beta.1     # Feature complete, testing
v2.0.0-rc.1       # Release candidate, final testing

# Build metadata (ignored in version precedence)
v1.0.0+build.123
```

## Git Tags

### Creating Tags

```bash
# Annotated tag (recommended for releases)
git tag -a v1.2.0 -m "Release v1.2.0: Add user authentication"

# Annotated tag with detailed message
git tag -a v2.0.0 -m "$(cat <<'EOF'
Release v2.0.0: API v2 with breaking changes

Breaking Changes:
- Response format changed to JSON:API
- Authentication switched to Bearer tokens
- Removed deprecated /v1/* endpoints
EOF
)"

# Lightweight tag (for temporary or local use)
git tag v1.2.0-dev

# Tag a specific commit (not HEAD)
git tag -a v1.1.0 abc1234 -m "Release v1.1.0"

# Push tags to remote
git push origin v1.2.0           # Push specific tag
git push origin --tags           # Push all tags
```

### Managing Tags

```bash
# List tags
git tag --list                   # All tags
git tag --list "v1.*"            # Tags matching pattern
git tag --list --sort=-v:refname # Sort by version descending

# View tag details
git show v1.2.0

# Delete a tag
git tag -d v1.2.0                # Delete local
git push origin --delete v1.2.0  # Delete remote

# Find which tag contains a commit
git tag --contains abc1234

# Find the latest tag
git describe --tags --abbrev=0
```

## Changelogs

### Manual Changelog Format

```markdown
<!-- CHANGELOG.md -->
# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]
### Added
- Search API with fuzzy matching (#567)

## [1.2.0] - 2025-01-15
### Added
- JWT-based user authentication (#142)
- Rate limiting on API endpoints (#156)
### Fixed
- Token refresh race condition (#163)
### Security
- Patch XSS vulnerability in user input (#172)

[Unreleased]: https://github.com/owner/repo/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/owner/repo/compare/v1.1.0...v1.2.0
```

### Automated Changelog from Commits

```bash
# Generate changelog from Conventional Commits
npx standard-version

# Generate for a specific version
npx standard-version --release-as 2.0.0

# Using git log as a quick changelog
git log v1.1.0..v1.2.0 --pretty=format:"- %s (%h)" --no-merges
```

## GitHub Releases

### Creating Releases

```bash
# Create a release with auto-generated notes
gh release create v1.2.0 --generate-notes --title "v1.2.0"

# Create a release with custom notes
gh release create v1.2.0 --title "v1.2.0 - User Authentication" --notes "$(cat <<'EOF'
## What's New
### Features
- **JWT Authentication**: Token-based auth with refresh rotation (#142)
- **Rate Limiting**: Configurable rate limits on API endpoints (#156)
### Bug Fixes
- Fix token refresh race condition (#163)
### Security
- Patch XSS vulnerability in user profile input (#172)
EOF
)"

# Create a pre-release
gh release create v2.0.0-beta.1 --prerelease --title "v2.0.0 Beta 1" \
  --notes "Beta release for API v2. Not recommended for production."

# Create a draft release
gh release create v1.3.0 --draft --title "v1.3.0" --generate-notes

# Upload release assets
gh release create v1.2.0 --title "v1.2.0" --generate-notes \
  dist/app-linux-amd64 dist/app-darwin-amd64
```

### Managing Releases

```bash
# List, view, edit, delete releases
gh release list
gh release view v1.2.0
gh release edit v1.2.0 --title "v1.2.0 - Updated Title"
gh release delete v1.2.0 --yes
gh release download v1.2.0 --pattern "*.tar.gz"
```

## Release Automation with CI/CD

### GitHub Actions Release Workflow

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Build and Test
        run: |
          npm ci
          npm test
          npm run build

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: dist/*
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Automated Version Bumping

```bash
# Using standard-version (reads Conventional Commits)
npx standard-version
# Automatically determines: feat -> minor, fix -> patch, BREAKING -> major

# Specify the release type manually
npx standard-version --release-as major   # 1.2.3 -> 2.0.0
npx standard-version --release-as minor   # 1.2.3 -> 1.3.0
npx standard-version --release-as patch   # 1.2.3 -> 1.2.4

# Dry run to preview
npx standard-version --dry-run
```

## Hotfix Releases

```bash
# Create hotfix from the release tag
git checkout -b hotfix/1.2.1 v1.2.0

# Apply the fix
git commit -m "fix(auth): patch token validation bypass

A crafted JWT token could bypass signature validation
when the algorithm field was set to 'none'.

CVE-2025-12345"

# Tag the hotfix
git tag -a v1.2.1 -m "Hotfix v1.2.1: Patch token validation bypass"
git push origin hotfix/1.2.1 --tags

# Create a GitHub release
gh release create v1.2.1 --title "v1.2.1 - Security Patch" \
  --notes "**Security**: Patch token validation bypass (CVE-2025-12345)"

# Merge hotfix back to main and clean up
git checkout main
git merge --no-ff hotfix/1.2.1
git push origin main
git branch -d hotfix/1.2.1
```

## Edge Cases

### Releasing from a Monorepo

```bash
# Tag with package prefix for monorepo versioning
git tag -a "api/v1.2.0" -m "API Release v1.2.0"
git tag -a "web/v2.3.0" -m "Web Release v2.3.0"

# List tags for a specific package
git tag --list "api/v*"

# Use path-scoped changelog generation
git log api/v1.1.0..api/v1.2.0 --oneline -- packages/api/
```

### Yanking a Bad Release

```bash
# Do NOT delete the tag. Instead, create a new patch release.

# Mark the GitHub release as not latest
gh release edit v1.2.0 --latest=false

# Create the fix release
git checkout -b hotfix/1.2.1 v1.2.0
# ... apply fix ...
git tag -a v1.2.1 -m "Hotfix v1.2.1"
git push origin --tags
gh release create v1.2.1 --title "v1.2.1 - Critical Fix" \
  --notes "Fixes critical bug in v1.2.0. All users should upgrade."
```

### Release Candidates

```bash
# Create release candidates for testing
git tag -a v2.0.0-rc.1 -m "Release Candidate 1 for v2.0.0"
git push origin v2.0.0-rc.1
gh release create v2.0.0-rc.1 --prerelease \
  --title "v2.0.0 Release Candidate 1" \
  --notes "Please test and report issues before final release."

# When RC is stable, create the final release
git tag -a v2.0.0 v2.0.0-rc.2 -m "Release v2.0.0"
git push origin v2.0.0
gh release create v2.0.0 --title "v2.0.0" --generate-notes
```