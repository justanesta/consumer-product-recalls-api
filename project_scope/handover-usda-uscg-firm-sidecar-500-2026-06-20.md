# Handover: `GET /firms/{id}` 500s for every USDA-establishment & USCG-manufacturer firm (2026-06-20)

**Branch:** `feature/announce-date-and-usda-uscg-firm-model-sync` (this repo). This is the "usda/uscg
firm model sync" half of the branch — companion to `handover-announce-date-timeseries-2026-06-20.md`
(the announce-date half). Surfaced by the website repo (`consumer-product-recalls-site`) while building
the firm-profile "Agency registration records" UI.

## TL;DR

`GET /firms/{firm_id}` returns **HTTP 500** (`{"error":{"type":"internal_error",...}}`) for any firm
whose profile carries a populated `firm_usda_attributes` or `firm_uscg_attributes` sidecar. Root cause:
the `UsdaEstablishment` / `UscgManufacturer` response models (`src/recalls_api/models/firms.py`) declare
`str` fields (`zip`, `fips_code`, `establishment_id`, `mic`, …) and a non-nullable
`prior_holders: list[str]`, but the mart's JSONB sidecars contain **numeric** zips/FIPS/ids (and
possibly `null` arrays). Pydantic v2 refuses `int → str` and `null → list`, the `ResponseValidationError`
is unhandled → 500. **FDA sidecars serialize fine** because the only numeric FDA field is typed
`int | str` (`firm_fei_num`, `models/firms.py:85`) — that contrast is the whole bug in one line.

This is a **live production outage** for a whole class of firm pages, not just a test artifact.

## Reproduction

Two real firm_ids (provided by the site owner; both have sidecars):

```
# USDA establishment firm  -> 500
curl -s -o /dev/null -w '%{http_code}\n' https://consumer-product-recalls-api.fly.dev/firms/00932d429e1fe10348437040d6fad1a4
# USCG manufacturer firm    -> 500
curl -s -o /dev/null -w '%{http_code}\n' https://consumer-product-recalls-api.fly.dev/firms/007c0a5f72b98156b055e59ed35fe357
# control: FDA firm (ConMed) -> 200   /firms/b97bf24bd7753acb205ba611db4e0876
# control: top-leaderboard firm -> 200
```

Both 500 deterministically while the machine is warm (`/health` 200 in ~120 ms), so it is **not**
cold-start / load shedding — it is the response body for these specific firms.

Confirmed against the real models with no DB (run from repo root,
`PYTHONPATH=src .venv/bin/python`):

| Input to the model | Result |
|---|---|
| `UscgManufacturer({"mic":"ABC","prior_holders":None})` | **ValidationError → 500** |
| `UscgManufacturer({"mic":"ABC","zip":48108})` (numeric zip) | **ValidationError → 500** |
| `UscgManufacturer({"mic":12345})` (numeric mic) | **ValidationError → 500** |
| `UsdaEstablishment({"establishment_id":46841})` (numeric id) | **ValidationError → 500** |
| `UsdaEstablishment({"establishment_id":"M1","zip":55101})` (numeric zip) | **ValidationError → 500** |
| `UsdaEstablishment({"establishment_id":"M1","fips_code":27053})` (numeric fips) | **ValidationError → 500** |
| same rows with string values | OK |

So any one numeric `zip` / `fips_code` / `establishment_id` / `mic` in the JSONB is sufficient to 500
the whole firm response. (The most likely production trigger is numeric `zip` / `fips_code`; see below.)

## Where the bad values come from

- API reads the JSONB sidecars verbatim from `mart_firm_profile` (`queries/firms.py:27-29`,
  `sa.column(..., sa.JSON)`); SQLAlchemy decodes them to Python `list[dict]` and Pydantic validates each
  dict into the sub-model.
- The sidecar rows originate in the data repo's silver models
  (`consumer-product-recalls/dbt/models/silver/firm_usda_attributes.sql`,
  `firm_uscg_attributes.sql`). `zip` / `fips_code` / `establishment_id` are passed through from
  bronze/staging and are **not guaranteed to be text** — numeric source values land in the JSONB as JSON
  numbers.
- `prior_holders` is built as `to_jsonb(array_remove(array[past_company_1..3], null))`, so at the silver
  grain it is `[]`, never `null`. The `prior_holders: None` failure mode is therefore **defensive-only**
  *unless* the `mart_firm_profile` aggregation can re-introduce a null (verify the json_agg /
  jsonb_build_object that assembles the per-firm array). Treat numeric `zip`/`fips`/`id` as the primary
  cause and `prior_holders` null as a belt-and-suspenders fix.

## Recommended fix (API trust boundary — smallest, immediate)

In `src/recalls_api/models/firms.py`:

1. Add `coerce_numbers_to_str=True` to the `model_config` of **`UsdaEstablishment`** and
   **`UscgManufacturer`** (and, for symmetry, `FdaAttributes` — harmless, and `firm_surviving_fei`
   becomes consistent). This coerces numeric `zip`/`fips_code`/`establishment_id`/`mic` → `str` at the
   boundary. Identifiers should stay strings on the wire anyway (leading zeros, non-arithmetic).
2. Add a `None → []` `field_validator(mode="before")` for `UscgManufacturer.prior_holders` (the existing
   `_none_to_list` validator on `FirmProfile` only covers the **top-level** sidecar lists, not nested
   row fields — `models/firms.py:231-243`).
3. Keep the wire contract `string | null` for these fields (do **not** switch to numeric types) so the
   committed website OpenAPI types don't churn. If you *do* change any field's wire type, the site must
   re-run `npm run gen:api` (its CI drift gate will fail until it does).

This is ~5 lines + a validator. It unblocks the live site immediately without a data rebuild.

## How this slipped through (so we fix the gap, not just the symptom)

The firm tests only ever exercised **idealized, all-string** sidecar data:
- `tests/fixtures/seed_gold.sql:258` (USDA) / `:264` (USCG) / `:270-272` (cross-source) — every value a
  clean string, `prior_holders: []`, no `zip`, no `fips_code`, `establishment_id:"M12345"`.
- `tests/test_models_firms.py:18-27` only checks the top-level `None → []` coercion, never a numeric
  field inside a sidecar row.
- `tests/integration/test_firms.py:33-34` asserts `establishment_id == "M12345"` (a prefixed string).

The strict `str` types never met a real numeric value. The seed mirrors the mart's *shape* but not its
*type messiness*.

## Open questions to resolve before/at the start of work

1. **Where should the schema be enforced — API or data layer (or both)?** The API is a trust boundary
   and should coerce defensively (recommended immediate fix). But the durable contract question is
   whether `mart_firm_profile` / the silver models should **guarantee text types** for
   `zip`/`fips_code`/`establishment_id` (cast to text) and **non-null** for array fields. Recommendation:
   do the API coercion now (unblocks prod) **and** file a data-repo follow-up to normalize the sidecar
   JSON value types at the source, so the wire shape is stable regardless of bronze drift.
2. **Canonical wire type per field.** Confirm these stay `string | null` (identifiers, leading zeros) vs.
   genuinely-numeric (`fips_code`?). The website currently types all of them `string | null`; changing
   that is a coordinated change (regen the site's `schema.d.ts`).
3. **Which field(s) actually fire in prod?** Pin it exactly by temporarily logging the
   `ResponseValidationError` (`loc` + value) for the two repro firms, or by selecting the raw
   `firm_usda_attributes` / `firm_uscg_attributes` JSONB for those `firm_id`s and inspecting value types.
   (Hypothesis: numeric `zip`/`fips_code`.)
4. **Observability hardening.** The 500 returned a generic `"an unexpected error occurred"` that hid the
   offending field — diagnosis required re-deriving it from the models. Should response-model validation
   failures log the `loc`/field (and ideally never reach the client as an opaque 500)? Consider a
   `ResponseValidationError` handler that logs structured detail.
5. **Contract/fixture realism.** Beyond the unit fix: add a realistic fixture firm (numeric `zip`,
   numeric `fips_code`, numeric/null edge cases, `prior_holders: null`) and, ideally, a per-source
   "firm-with-sidecar returns 200" check so this can't regress silently.

## Testing plan

- Unit (`tests/test_models_firms.py`): add cases that validate `UsdaEstablishment` /
  `UscgManufacturer` from numeric `zip`/`fips_code`/`establishment_id`/`mic` and `prior_holders: null` →
  expect success (coerced), mirroring the repro table above.
- Fixture (`tests/fixtures/seed_gold.sql`): change one seeded sidecar row to use a **numeric** `zip` and
  `fips_code` (and a `null` `prior_holders`) so the integration path exercises real-world types.
- Integration (`tests/integration/test_firms.py`): assert that firm returns 200 and that the coerced
  fields come back as strings.

## Verify (definition of done)

- The two repro firm_ids return **200** with populated `firm_usda_attributes` / `firm_uscg_attributes`.
- `pytest` green (new numeric/null cases included).
- Site confirmation: the website's firm "Agency registration records" section renders the USDA/USCG
  cards (the FDA card path is already verified in the site repo). The site code is done and waiting;
  it will light up the moment the API serves these firms (no site change needed unless a wire type
  changes — then regen `schema.d.ts`).

## References

- `src/recalls_api/models/firms.py` — `UsdaEstablishment` (:17), `UscgManufacturer` (:41, `prior_holders`
  :77), `FdaAttributes` (:80, `firm_fei_num: int | str` :85), top-level `_none_to_list` (:231-243).
- `src/recalls_api/queries/firms.py:27-29` — JSONB sidecar columns.
- `tests/fixtures/seed_gold.sql:258,264,270` — idealized fixtures (the blind spot).
- Data repo silver models: `dbt/models/silver/firm_usda_attributes.sql`, `firm_uscg_attributes.sql`.
- Companion: `project_scope/handover-announce-date-timeseries-2026-06-20.md` (same branch workstream;
  `mart_firm_profile.first_recall_at/last_recall_at` basis change).
