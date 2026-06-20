# Data-side → API handover: time-series now buckets on the ANNOUNCE date (2026-06-20)

**Branch (data repo):** `fix/announced-at-date-join` (consumer-product-recalls). Companion to
`data-side-provenance-handover-2026-06-19.md` (same workstream). New untracked file — place/commit on
whatever branch you prefer.

## TL;DR

The five date-grained gold facts now bucket on `coalesce(announced_at, published_at)` instead of
`published_at`. **No schema/wire change. No required API code change.** The served *values* shift: the
FDA "Sept-2018 spike" disappears and FDA history spreads across years. Read this so the website/stats
copy describes the trend basis correctly and so `published_at` is described precisely.

## What changed (data side)

- `fct_recalls_by_month` / `_by_week` / `_by_year`, `fct_recalls_monthly_trend`, `fct_units_recalled`
  join `dim_date` on `coalesce(announced_at, published_at)::date` (was `published_at::date`).
- `mart_firm_profile.first_recall_at` / `last_recall_at` move to the same coalesced basis.
- **Why:** `published_at` is a publish / last-modified watermark; FDA's (`event_lmd`) is bulk-stamped
  ~2018-09 for the openFDA archive migration, which collapsed all pre-2018 FDA history (~29k events)
  into one month. `announced_at` is the true, backfill-immune initiation date. It is nullable (~20
  FDA), so the coalesce floors to the non-null `published_at` → the inner join stays lossless (guarded
  by `assert_fct_recalls_by_{month,week,year}_reconciles`).
- **Schema unchanged:** the fct views expose `period`, not a raw date. `gold_meta.schema_version` is
  NOT bumped. The change takes effect on the next `dbt build` (values only).

## What the API SHOULD do

1. **Stats endpoints (`/stats/recalls-by-period`, `/stats/monthly-trend`, units):** no code change —
   they pass through the fct `period` / `event_count`. The numbers change after the next gold rebuild.
   Update any UI/marketing copy that explains the trend ("recalls by month") to say it is by when the
   recall was **announced / initiated**, not when it was last published.
2. **Describe `published_at` precisely.** `_D_PUBLISHED_AT` currently reads "Last-published/modified
   date, coalesced per source to always be present." Accurate for CPSC/FDA/USDA/USCG but it
   **overstates NHTSA**: NHTSA's `published_at` is `coalesce(DATEA, RCDATE)` where `DATEA` = "Record
   Creation Date" — a creation date, not last-modified (the NHTSA flat file has no last-modified
   field). Suggested tweak: "…always be present (NHTSA's underlying field is a record-creation date,
   not a last-modified)." `_D_ANNOUNCED_AT` is already accurate.

## What the API should NOT do

- **Do NOT change pagination/sort.** The `GET /recalls` keyset + R2 index stay on `published_at DESC`
  (the non-null freshness key). Keyset pagination requires a non-null sort column; `announced_at` is
  nullable. The separation is deliberate — `published_at` = "what's new/updated" (sort), `announced_at`
  = "when did it happen" (analytics). Both stay exposed as fields; the `published_after` /
  `announced_after` filters are unchanged.
- A future *announce-recency* feed (if product wants it) is logged in the data repo's `TODO.md`
  §Performance: paginate on a materialized `event_date = coalesce(announced_at, published_at)` — NOT by
  quarantining the ~20 FDA nulls. That would be a coordinated cross-repo change (new mart column +
  index + API cursor semantics); not needed now.

## Verify

Data-side decision: `consumer-product-recalls` ADR 0038 §2026-W25 amendment; `gold_design_notes.md`
(`dim_date` section); reconcile guards `dbt/tests/assert_fct_recalls_by_{month,week,year}_reconciles.sql`.
