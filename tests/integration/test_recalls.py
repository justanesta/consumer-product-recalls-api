"""Integration tests for /recalls (list + detail) against the seeded gold cassette.

SKIP locally without TEST_DATABASE_URL; run under testcontainers / CI.
"""

from __future__ import annotations

from httpx import AsyncClient

_ALL_IDS = {"24-003", "F-1006", "F-1001", "U-2002", "24V-004", "USCG-005"}


async def test_list_returns_all_newest_first(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"limit": 100})
    assert r.status_code == 200
    body = r.json()
    ids = [it["source_recall_id"] for it in body["items"]]
    assert set(ids) == _ALL_IDS
    # newest first: CPSC 24-003 (2026-06-01) leads, USCG-005 (2026-02-10) last
    assert ids[0] == "24-003"
    assert ids[-1] == "USCG-005"
    assert body["next_cursor"] is None
    assert body["total"] is None  # off by default


async def test_filter_by_source(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"source": "FDA", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001", "F-1006"}


async def test_is_active_true_excludes_null_sources(client: AsyncClient) -> None:
    # is_active=true matches only sources that carry status; CPSC/NHTSA (null) must NOT appear.
    r = await client.get("/recalls", params={"is_active": "true", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001", "USCG-005"}


async def test_filter_by_classification(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"classification": "Class I", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001"}


async def test_firm_substring_is_case_insensitive(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"firm": "acme", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001", "F-1006"}


async def test_date_range_inclusive_of_whole_before_day(client: AsyncClient) -> None:
    # published_before=2026-05-10 must include F-1001 (12:00Z that day) — whole day is inclusive.
    r = await client.get("/recalls", params={"published_before": "2026-05-10", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert "F-1001" in ids  # same-day row is included
    assert "F-1006" not in ids  # 2026-05-12 is after


async def test_with_total(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"source": "FDA", "with_total": "true", "limit": 100})
    assert r.json()["total"] == 2


async def test_keyset_pagination_walks_all_without_overlap(client: AsyncClient) -> None:
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # safety bound
        params: dict[str, str | int] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = (await client.get("/recalls", params=params)).json()
        seen.extend(it["source_recall_id"] for it in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert set(seen) == _ALL_IDS
    assert len(seen) == len(_ALL_IDS)  # no duplicates


async def test_bad_cursor_returns_400(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"cursor": "!!!not-valid!!!"})
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "bad_cursor"


async def test_detail_hit_full_fields(client: AsyncClient) -> None:
    r = await client.get("/recalls/fda/F-1001")
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "FDA"
    assert d["classification"] == "Class I"
    assert d["product_names"] == ["Acme Peanut Butter 16oz", "Acme Peanut Butter 32oz"]
    assert d["models"] == []  # NULL in mart -> coerced to []
    assert d["hins"] == []
    assert d["product_upcs"] == ["012345678905"]
    assert len(d["firms"]) == 1
    assert d["firms"][0]["name"] == "Acme Foods Inc"
    assert d["distribution_states"] == "Nationwide"  # scalar prose string


async def test_detail_source_is_case_insensitive(client: AsyncClient) -> None:
    lower = await client.get("/recalls/fda/F-1001")
    upper = await client.get("/recalls/FDA/F-1001")
    assert lower.status_code == upper.status_code == 200
    assert lower.json()["recall_event_id"] == upper.json()["recall_event_id"]


async def test_detail_multi_firm_rollup(client: AsyncClient) -> None:
    d = (await client.get("/recalls/usda/U-2002")).json()
    assert d["firm_count"] == 2
    assert {f["name"] for f in d["firms"]} == {"Tyson Foods", "Cold Storage Co"}
    assert d["distribution_state_codes"] == ["CA", "OR", "WA"]
    assert d["was_ever_retracted"] is True


async def test_detail_missing_returns_404(client: AsyncClient) -> None:
    r = await client.get("/recalls/fda/NOPE")
    assert r.status_code == 404
    assert r.json()["error"]["type"] == "not_found"


async def test_detail_unknown_source_returns_422(client: AsyncClient) -> None:
    r = await client.get("/recalls/xyz/anything")
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "invalid_parameter"


async def test_invalid_query_param_uses_envelope(client: AsyncClient) -> None:
    # A FastAPI Query-constraint failure must use our envelope, not the default 422 body.
    r = await client.get("/recalls", params={"limit": 0})  # below ge=1
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "invalid_parameter"
