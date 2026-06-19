"""Integration tests for /stats/* against the seeded gold_meta + fct_* tables."""

from __future__ import annotations

from httpx import AsyncClient


async def test_overview(client: AsyncClient) -> None:
    r = await client.get("/stats/overview")
    assert r.status_code == 200
    b = r.json()
    assert b["total_recalls"] == 6  # six seeded recalls in mart_recall_summary
    assert b["distinct_firms"] == 5  # five seeded firm-profile rows
    assert set(b["sources"]) == {"CPSC", "FDA", "USDA", "NHTSA", "USCG"}
    assert b["last_rebuilt_at"] is not None


async def test_recalls_by_period_default_month(client: AsyncClient) -> None:
    rows = (await client.get("/stats/recalls-by-period")).json()
    fda_may = [x for x in rows if x["source"] == "FDA" and x["period"] == "2026-05-01"]
    assert fda_may and fda_may[0]["event_count"] == 2


async def test_recalls_by_period_grain_week_switches_table(client: AsyncClient) -> None:
    rows = (await client.get("/stats/recalls-by-period", params={"grain": "week"})).json()
    assert "2026-05-04" in {x["period"] for x in rows}  # a seeded ISO-week (Monday) row


async def test_recalls_by_period_source_filter(client: AsyncClient) -> None:
    rows = (await client.get("/stats/recalls-by-period", params={"source": "FDA"})).json()
    assert {x["source"] for x in rows} == {"FDA"}


async def test_by_classification_is_source_native(client: AsyncClient) -> None:
    rows = (await client.get("/stats/by-classification", params={"source": "FDA"})).json()
    # FDA is source-native 1/2/3/NC — never the Roman 'Class I'
    assert {x["classification"] for x in rows} == {"2", "3"}


async def test_by_classification_all_rollup_when_unfiltered(client: AsyncClient) -> None:
    rows = (await client.get("/stats/by-classification")).json()
    assert "ALL" in {x["source"] for x in rows}


async def test_status_active_inactive(client: AsyncClient) -> None:
    rows = (await client.get("/stats/status", params={"source": "FDA"})).json()
    assert {x["status"] for x in rows} == {"active", "inactive"}


async def test_firm_leaderboard_top1(client: AsyncClient) -> None:
    rows = (await client.get("/stats/firm-leaderboard", params={"limit": 1})).json()
    assert len(rows) == 1
    assert rows[0]["canonical_name"] == "Acme Foods Inc"
    assert rows[0]["event_count_rank"] == 1


async def test_by_geography_basis_switches_lens(client: AsyncClient) -> None:
    dist = await client.get(
        "/stats/by-geography", params={"basis": "distribution", "source": "USDA"}
    )
    assert {x["state_code"] for x in dist.json()} == {"CA", "OR", "WA"}
    reg = await client.get("/stats/by-geography", params={"basis": "firm_registration"})
    assert {x["state_code"] for x in reg.json()} == {"IL"}


async def test_by_country_source_filter(client: AsyncClient) -> None:
    rows = (await client.get("/stats/by-country", params={"source": "USDA"})).json()
    assert {x["country_code"] for x in rows} == {"MX", "GB"}


async def test_units_per_source(client: AsyncClient) -> None:
    rows = (await client.get("/stats/units", params={"source": "NHTSA"})).json()
    assert rows and rows[0]["unit_category"] == "count"
    assert rows[0]["total_units"] == 5000


async def test_monthly_trend_returns_rows(client: AsyncClient) -> None:
    rows = (await client.get("/stats/monthly-trend")).json()
    assert any(x["source"] == "FDA" for x in rows)


async def test_invalid_enum_params_are_422(client: AsyncClient) -> None:
    assert (
        await client.get("/stats/recalls-by-period", params={"grain": "decade"})
    ).status_code == 422
    assert (await client.get("/stats/by-geography", params={"basis": "nope"})).status_code == 422
    assert (
        await client.get("/stats/by-classification", params={"source": "XYZ"})
    ).status_code == 422
