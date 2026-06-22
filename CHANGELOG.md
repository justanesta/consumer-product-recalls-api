# Changelog

All notable changes to the Consumer Product Recalls API. Versioning is [SemVer](https://semver.org/);
the wire contract (response models + `openapi.json`) is what the version tracks. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## [0.2.0] — 2026-W26

### Changed
- **Default `GET /recalls` feed now sorts by announce-recency, not last-published.** The list is ordered
  `event_date DESC, recall_event_id ASC`, where `event_date = coalesce(announced_at, published_at)` (a new
  gold mart column, ADR 0038 §2026-W26). Previously the feed sorted on `published_at DESC`, which surfaced
  long-dormant recalls that received one minor agency edit at the top of the feed. The opaque pagination
  cursor for `/recalls` now encodes `event_date` and is tagged `e` (was `p`); cursors are ephemeral, so any
  in-flight `p` cursor on `/recalls` simply returns `400 bad_cursor` and the client restarts from page 1.
  `/products/search` keeps its `published_at` (`p`) ordering — unchanged.

### Added
- **`event_date`** field on `RecallSummary` and `RecallDetail` (non-null) — the announce-recency value the
  feed is sorted/paginated on. Equals `announced_at` whenever that is set; falls back to `published_at` for
  the ~20 FDA recalls with no announcement date.

### Notes
- `announced_at` and `published_at` remain exposed, and **both** filter pairs are retained:
  `announced_after`/`announced_before` (by announcement date — feed axis) and
  `published_after`/`published_before` (by last-published date).
- Requires gold `schema_version >= 2` (the `event_date` column + sort-semantics change). Regenerate and
  re-freeze `openapi.json` (`python -m recalls_api.export_openapi`) when deploying this version.

## [0.1.1]

- Pre-changelog baseline: open, read-only FastAPI serving layer over the gold marts (recalls list/detail,
  recalls FTS search, products search, firms, stats), keyset pagination, `published_at`-sorted feed.
