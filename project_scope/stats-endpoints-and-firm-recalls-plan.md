# Plan — `/stats/*` read-through endpoints + `GET /recalls?firm_id=` filter

**Date:** 2026-06-19 · **Status:** ✅ **IMPLEMENTED 2026-06-19** on `feature/stats-and-firm-recalls` (180 tests green; `openapi.json` regenerated; docs updated). Originally a build-ready plan for a new branch — two independent features in one branch.

> **Confirm-before-build corrections (applied):** reading the `fct_*` SQL surfaced a few columns the plan had inferred — `fct_recalls_monthly_trend` has **two** rolling columns (`rolling_3mo_avg` + `rolling_12mo_avg`, not one); `fct_recall_status` outputs `source/status/event_count` only (**no** `is_active`); `fct_recalls_by_firm` carries `canonical_name` (+ `active_recalls`, `first/last_recall_at`), not a `firm_name`. The shipped models match the verified columns.

**Why now / what's already done (no gold work blocks this):**
- The **`fct_*` aggregate marts already exist** (`fct_recalls_by_month/_week/_year`, `_monthly_trend`, `_by_classification`, `_recall_status`, `_by_firm`, `_by_geography`, `_by_country`, `_units_recalled`) + `dim_date`, and the gold `grant_gold_readonly` post-hook **already grants `SELECT` on every gold object to `recalls_readonly`** — so the API's role can read them today. This is pure API-surface work.
- The firm↔recall edge already lives on `mart_recall_summary.firms` (jsonb `[{firm_id, name, role, match_confidence}]`); `mart_firm_profile` only carries aggregate firm stats (counts), not the recall list — so the firm's recalls must be read from the recall grain.

> **Confirm-before-build:** the response models below are drawn from the `fct_*` `select` aliases as of 2026-06-19. Before coding, re-confirm the exact output columns against each gold model's `_gold.yml` / final `select` (a few names were inferred — flagged inline). Treat `_gold.yml` as the column contract.

---

## Part A — `GET /recalls?firm_id={id}` (small; no gold dependency)

A firm's recalls = the `/recalls` list scoped to one firm, so it reuses all of `/recalls`' pagination + filters + the `RecallSummary` projection. The only new logic is **one jsonb containment predicate** over the `firms` rollup — the same primitive as UPC search. It matches the firm in **any** role (so co-recalled/secondary firms are included, unlike `firm=` substring on the primary name only).

### `deps.py`
- Add to `RecallFilters`: `firm_id: str | None = None`.
- Add the Query param to `recall_filters(...)`, validating the canonical 32-hex shape for a clean 422 (mirrors the `/firms/{firm_id}` path guard):
  ```python
  firm_id: Annotated[
      str | None,
      Query(
          pattern=r"^[0-9a-f]{32}$",
          description="Canonical firm cluster id; returns recalls where this firm appears in ANY "
          "role (incl. co-recalled). Obtain from RecallDetail.firms[].firm_id.",
      ),
  ] = None,
  ```
  and thread it into the returned `RecallFilters(...)`.

### `queries/recalls.py`
- `mart_recall_summary.firms` is declared `sa.JSON` in the table literal; cast to `JSONB` for `@>` (exactly like `_upc_where` in `products.py`). In `recalls_predicates`, append:
  ```python
  if filters.firm_id is not None:  # jsonb containment over the firms rollup; matches any role
      conds.append(
          sa.cast(c.firms, JSONB).op("@>")(
              sa.bindparam("firm_id_arr", [{"firm_id": filters.firm_id}], type_=JSONB)
          )
      )
  ```
  (add `from sqlalchemy.dialects.postgresql import JSONB` if not already imported in this module). It composes with every other filter + the keyset cursor automatically — no other change to `list_stmt` / `search_stmt`.

### Tests
- **Unit** (`test_queries_recalls.py`): predicate emits `@>` containment with the `[{"firm_id": …}]` bind.
- **Integration** (`test_recalls.py`): `?firm_id=<Acme id>` → `{F-1001, F-1006}`; `?firm_id=<Tyson id>` → `{U-2002}` (proves the **co-recalled / multi-firm** case via the seeded `U-2002` Tyson+Cold Storage rollup); a malformed id → 422. Compose with another filter (e.g. `?firm_id=…&source=FDA`) to prove AND.

### Docs
- `api-reference.md` `/recalls` filter table: add `firm_id` (32-hex; matches any role; contrast `firm=` which is primary-name substring only).
- `data_contract.md`: one line that `firm_id` filtering uses `firms @> [{"firm_id":…}]` containment.

### Perf
- Seq-scan unless gold adds a **GIN index on `mart_recall_summary.firms`** (the user's pipeline follow-up). Acceptable unindexed at ~93k rows; the GIN index is the clean perf win when firm pages get traffic.

---

## Part B — `/stats/*` read-through endpoints over `fct_*`

Small pre-aggregates → **no keyset, no cursor, no `with_total`**. Each endpoint returns the whole (optionally `source`-filtered) view as a typed list (a top-N for the leaderboard). Caching (`Cache-Control: max-age=300`), CORS, rate-limit, and the error envelope are inherited — **no middleware change**. New modules: `queries/stats.py`, `models/stats.py`, `routers/stats.py`; register `stats.router` in `main.py`.

### B.0 Cross-cutting design decisions
- **`source` filter incl. the `'ALL'` rollup.** The period/classification/status/geography facts carry an `'ALL'` all-source rollup row (GROUPING SETS — *not* double-counting). Add a `StatsSource` StrEnum = the 5 sources **+ `ALL`** (don't reuse the strict `Source` enum, which rejects `'ALL'`). An **optional** `source` param filters to one value; omitted → return every row (per-source **and** the `ALL` rollup) and let the client pick. Response models type `source` as `str` (or `StatsSource`).
- **Response shape:** bare `list[T]` per endpoint (`response_model=list[PeriodCount]`, etc.); `/stats/overview` returns a single object. (If you later want metadata like `generated_at`, wrap in a thin `{items, meta}` envelope — not needed for v1.)
- **Honesty caveats go in `Field(description=…)`** (and link the matrix): geography per-state counts **sum to more than the total** (multi-counting / "industry footprint", documented gold caveat); units are recall-magnitude, NHTSA/USCG only, **not cross-source comparable**; `'ALL'` is a synthesized rollup.

### B.1 Endpoint catalog (path ← `fct_*`; columns to confirm vs `_gold.yml`)

| Endpoint | Backing model | Output columns (→ Pydantic) |
|---|---|---|
| `GET /stats/overview` | *API-computed* (no new gold model) | `total_recalls` (count `mart_recall_summary`), `distinct_firms` (count `mart_firm_profile`), `sources` (the 5), `last_rebuilt_at` (`gold_meta.rebuilt_at`) |
| `GET /stats/recalls-by-period?grain=month\|week\|year&source=` | `fct_recalls_by_month` / `_by_week` / `_by_year` | `period` (date), `source`, `event_count` |
| `GET /stats/monthly-trend?source=` | `fct_recalls_monthly_trend` | `month`, `source`, `event_count`, `rolling_avg`*, `event_count_year_ago`, `yoy_pct_change` |
| `GET /stats/by-classification?source=` | `fct_recalls_by_classification` | `source`, `classification`, `risk_level`, `event_count` |
| `GET /stats/status?source=` | `fct_recall_status` | `source`, `status`, `is_active`, `event_count` |
| `GET /stats/firm-leaderboard?limit=` | `fct_recalls_by_firm` (top-N by `event_count_rank`) | `firm_id`, `firm_name`*, `event_count`, `product_count`, `event_count_rank` |
| `GET /stats/by-geography?basis=distribution\|firm_registration&source=` | `fct_recalls_by_geography` | `geography_basis`, `source`, `state_code`, `recall_count` |
| `GET /stats/by-country?source=` | `fct_recalls_by_country` | `source`, `country_code`, `recall_count` |
| `GET /stats/units?source=` | `fct_units_recalled` | `period`, `source`, `unit_category`*, `total_units`, `avg_units_per_recall`, `max_units`, `recalls_with_units` |

`*` = confirm the exact column name/presence against `_gold.yml` (`rolling_avg` window name; whether `fct_recalls_by_firm` projects a firm display name; the `fct_units_recalled` grain/columns).

> **`recalls-by-period`** is **one** endpoint with a `grain` enum switching among the three same-shaped tables (`period, source, event_count`) — cleaner than three near-identical routes. `monthly-trend` stays separate (different columns).

### B.2 `models/stats.py`
One small `BaseModel` per row shape (`from_attributes=True`), each field with a `Field(description=…)` carrying meaning + the honesty caveat where relevant. Sketch:
```python
class StatsOverview(BaseModel):
    total_recalls: int
    distinct_firms: int
    sources: list[str]
    last_rebuilt_at: datetime | None = Field(
        default=None, description="gold_meta.rebuilt_at — when the gold marts were last rebuilt.")

class PeriodCount(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    period: date
    source: str  # incl. the 'ALL' rollup
    event_count: int

class GeographyCount(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    geography_basis: str  # 'distribution' | 'firm_registration'
    source: str
    state_code: str
    recall_count: int = Field(
        description="Per-state recall count. NOTE: a recall is counted in every state it touches, so "
        "per-state counts SUM TO MORE than the total (industry-footprint reading), and the two "
        "geography_basis lenses are different questions — not interchangeable.")
# … ClassificationCount, StatusCount, MonthlyTrendPoint, FirmLeaderRow, CountryCount, UnitsRow
```

### B.3 `queries/stats.py`
Lightweight `sa.table(...)` literal per `fct_*` (only the columns we project) + a pure builder per endpoint. Pattern (no pagination):
```python
def by_classification_stmt(source: StatsSource | None) -> Select:
    stmt = sa.select(*_CLASSIFICATION_COLS)
    if source is not None:
        stmt = stmt.where(fct_classification.c.source == sa.bindparam("source", source.value))
    return stmt.order_by(fct_classification.c.source, fct_classification.c.event_count.desc())

def firm_leaderboard_stmt(limit: int) -> Select:
    return (sa.select(*_FIRM_COLS)
            .order_by(fct_firm.c.event_count_rank.asc())
            .limit(sa.bindparam("limit", limit)))
```
`/stats/overview` is a few scalar reads assembled in the router/service (count `mart_recall_summary`, count `mart_firm_profile`, `select rebuilt_at from gold_meta`).

### B.4 `routers/stats.py` + `main.py`
- A `stats.router` (prefix `/stats`, tag `stats`) with one handler per endpoint; reuse `Depends(get_conn)`; wrap DB failures via the existing error handlers (no new error types). Validate `grain` / `basis` as enums for free 422s. Register with `app.include_router(stats.router)` in `create_app()`.
- These are GET, cache-eligible, rate-limited like everything else (the 5-min cache is ideal for the website's build-time pull).

### B.5 Seed (`tests/fixtures/seed_gold.sql`) — the main ceremony
Add a `CREATE TABLE` + a few rows for **each** `fct_*` we read, plus `gold_meta`, consistent with the existing seeded recalls so integration assertions are deterministic. Keep them tiny (2–5 rows each), e.g.:
- `fct_recalls_by_classification`: FDA `2`→1, FDA `3`→1, USDA `Class II`→1, `ALL` rollup rows.
- `fct_recalls_by_firm`: Acme (id `aaaa…`) event_count 2, rank 1; others.
- `fct_recalls_by_geography`: `distribution` CA/OR/WA, plus a `firm_registration` row.
- `fct_recalls_by_month` / `gold_meta` (`rebuilt_at`) / etc.

### B.6 Tests
- **Unit** (`test_queries_stats.py`): each builder compiles; `source`/`grain`/`limit` binds present; leaderboard orders by rank.
- **Integration** (`test_stats.py`): each endpoint returns the seeded rows; `?source=FDA` filters; `?source` omitted includes the `ALL` rollup; `grain` switches tables; `basis` switches the geography lens; `firm-leaderboard?limit=1` returns the top firm; `/stats/overview` returns sane counts + `last_rebuilt_at`.
- **Contract** (`test_openapi.py`): add the `/stats/*` paths + the new schemas to the surface-guard loops.

---

## Cross-cutting — OpenAPI + the gate

- Regenerate: `uv run python -m recalls_api.export_openapi`.
- Update `documentation/api-reference.md` (new `## GET /stats/*` section + the `/recalls` `firm_id` row) and `documentation/data_contract.md` (note `/stats/*` reads the `fct_*` marts; the multi-counting + units caveats; the `firm_id` containment).
- **Gate (must be green):** `ruff check` + `ruff format --check` + `pyright` + full `pytest` (via `sg docker -c 'uv run pytest'`) + `export_openapi --check`.

---

## Execution order

Both features are independent and buildable immediately (no gold dependency). Suggested order on the one branch:
1. **Part A** (`firm_id`) — smallest; lands the firm-page unblock first.
2. **Part B scaffolding** — `queries/stats.py` + `models/stats.py` + `routers/stats.py` + register; seed the `fct_*` + `gold_meta`.
3. **Part B endpoints** — start with the landing-page slice (`overview`, `recalls-by-period`, `by-classification`, `status`) to unblock website §5.1, then the dashboards set (`firm-leaderboard`, `by-geography`, `by-country`, `monthly-trend`, `units`).
4. OpenAPI regen + docs + the full gate.

---

## Out of scope / follow-ups
- **GIN index on `mart_recall_summary.firms`** — the user's **pipeline-side** perf follow-up for `?firm_id=` (not a blocker).
- **`GET /firms/{firm_id}/recalls`** sub-resource — optional sugar over `?firm_id=` (delegate to the same list builder), only if the firm page wants the prettier URL. Don't build a second query path.
- **`fct_recalls_overview`** — `/stats/overview` is API-computed here (no new gold model). If you'd rather not run the per-request COUNTs, add a single-row `fct_recalls_overview` upstream and read it instead (a pipeline change; the website plan §5.1 anticipated this).
- **Per-rebuild ETag (R6)** — reading `gold_meta.rebuilt_at` for `/stats/overview` is the same source the deferred per-rebuild ETag wants; wiring that into the cache validator stays out of scope here.
- **ADR 0024** — the `/stats/*` surface is the trigger the pipeline's serving-layer plan deferred to ADR 0024; ratify it when this lands (pipeline ADR register).
