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


async def test_filter_by_source_multi_value_comma(client: AsyncClient) -> None:
    # Comma-separated any-of (OR): FDA or USDA = both F-rows plus U-2002.
    r = await client.get("/recalls", params={"source": "FDA,USDA", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001", "F-1006", "U-2002"}


async def test_filter_by_source_multi_value_repeated(client: AsyncClient) -> None:
    # Repeated-param form is equivalent to the comma form.
    r = await client.get("/recalls?source=FDA&source=USDA&limit=100")
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001", "F-1006", "U-2002"}


async def test_filter_by_classification_multi_value(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"classification": "Class I,Class III", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001", "F-1006"}  # Class I (F-1001) + Class III (F-1006)


async def test_multi_value_within_field_or_across_fields_and(client: AsyncClient) -> None:
    # source any-of OR, AND-ed with classification: (FDA or USDA) and Class I = F-1001 only.
    r = await client.get(
        "/recalls", params={"source": "FDA,USDA", "classification": "Class I", "limit": 100}
    )
    assert {it["source_recall_id"] for it in r.json()["items"]} == {"F-1001"}


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


async def test_filter_by_distribution_scope(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"distribution_scope": "Regional", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"U-2002"}


async def test_filter_by_lifecycle_status_excludes_null_sources(client: AsyncClient) -> None:
    # lifecycle_status is null for CPSC/NHTSA, so an exact-value filter never returns them.
    r = await client.get("/recalls", params={"lifecycle_status": "Ongoing", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001"}
    assert "24-003" not in ids and "24V-004" not in ids  # CPSC/NHTSA (null) excluded


async def test_announced_after_excludes_null_announced_rows(client: AsyncClient) -> None:
    # Only F-1001/F-1006/U-2002 carry announced_at; CPSC/NHTSA/USCG (null) must drop out.
    r = await client.get("/recalls", params={"announced_after": "2026-01-01", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001", "F-1006", "U-2002"}


async def test_announced_before_inclusive_of_whole_day(client: AsyncClient) -> None:
    # announced_before=2026-04-15 includes U-2002 (announced that day); May rows excluded.
    r = await client.get("/recalls", params={"announced_before": "2026-04-15", "limit": 100})
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert "U-2002" in ids
    assert "F-1001" not in ids and "F-1006" not in ids


async def test_source_recall_id_is_exact_match(client: AsyncClient) -> None:
    hit = await client.get("/recalls", params={"source_recall_id": "F-1001", "limit": 100})
    assert {it["source_recall_id"] for it in hit.json()["items"]} == {"F-1001"}
    # exact, not substring: a partial id matches nothing
    miss = await client.get("/recalls", params={"source_recall_id": "F-100", "limit": 100})
    assert miss.json()["items"] == []


async def test_dimension_filters_and_together(client: AsyncClient) -> None:
    # source AND distribution_scope compose: Nationwide ∩ FDA = the two F-rows.
    r = await client.get(
        "/recalls", params={"source": "FDA", "distribution_scope": "Nationwide", "limit": 100}
    )
    ids = {it["source_recall_id"] for it in r.json()["items"]}
    assert ids == {"F-1001", "F-1006"}


async def test_filter_by_distribution_state(client: AsyncClient) -> None:
    # U-2002 is distributed to {CA, OR, WA}; matching is case-insensitive.
    hit = await client.get("/recalls", params={"distribution_state": "ca", "limit": 100})
    assert {it["source_recall_id"] for it in hit.json()["items"]} == {"U-2002"}
    miss = await client.get("/recalls", params={"distribution_state": "NY", "limit": 100})
    assert miss.json()["items"] == []


async def test_filter_by_distribution_state_multi_value_overlap(client: AsyncClient) -> None:
    # Array overlap (&&) any-of: U-2002 ships to {CA, OR, WA}; {NY, CA} overlaps -> hit.
    hit = await client.get("/recalls", params={"distribution_state": "NY,CA", "limit": 100})
    assert {it["source_recall_id"] for it in hit.json()["items"]} == {"U-2002"}
    # No overlap with the seeded states -> empty.
    miss = await client.get("/recalls", params={"distribution_state": "NY,TX", "limit": 100})
    assert miss.json()["items"] == []


async def test_filter_by_distribution_country_foreign_only(client: AsyncClient) -> None:
    # U-2002 is distributed to {MX, GB}; 'US' is never present (excluded from gold by design).
    hit = await client.get("/recalls", params={"distribution_country": "mx", "limit": 100})
    assert {it["source_recall_id"] for it in hit.json()["items"]} == {"U-2002"}
    us = await client.get("/recalls", params={"distribution_country": "US", "limit": 100})
    assert us.json()["items"] == []  # US is excluded by design, so this is always empty


async def test_distribution_scope_invalid_value_returns_422(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"distribution_scope": "Galaxywide"})
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "invalid_parameter"


async def test_search_keyword_matches_recall(client: AsyncClient) -> None:
    r = await client.get("/recalls/search", params={"q": "salmonella", "limit": 100})
    assert r.status_code == 200
    assert {it["source_recall_id"] for it in r.json()["items"]} == {"F-1001"}


async def test_search_brand_name_match(client: AsyncClient) -> None:
    # "tyson" lives in the firm + folded product names, not just the title -> proves the fold works.
    r = await client.get("/recalls/search", params={"q": "tyson", "limit": 100})
    assert {it["source_recall_id"] for it in r.json()["items"]} == {"U-2002"}


async def test_search_ranks_title_above_narrative(client: AsyncClient) -> None:
    # "hazard": title (A) for 24-003 vs consequence (D) for USCG-005 + U-2002 -> 24-003 first.
    items = (await client.get("/recalls/search", params={"q": "hazard", "limit": 100})).json()[
        "items"
    ]
    ids = [it["source_recall_id"] for it in items]
    assert set(ids) == {"24-003", "USCG-005", "U-2002"}
    assert ids[0] == "24-003"  # the title (A) match outranks both consequence (D) matches
    assert items[0]["rank"] >= items[1]["rank"]


async def test_search_filters_and_in(client: AsyncClient) -> None:
    r = await client.get("/recalls/search", params={"q": "hazard", "source": "CPSC", "limit": 100})
    assert {it["source_recall_id"] for it in r.json()["items"]} == {"24-003"}


async def test_search_q_too_short_returns_422(client: AsyncClient) -> None:
    r = await client.get("/recalls/search", params={"q": "a"})
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "invalid_parameter"


async def test_search_no_match_is_empty(client: AsyncClient) -> None:
    r = await client.get("/recalls/search", params={"q": "zzqqxx", "limit": 100})
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_search_garbage_query_is_injection_safe(client: AsyncClient) -> None:
    # websearch_to_tsquery never raises on operator-y/garbage input -> 200, not 500.
    r = await client.get("/recalls/search", params={"q": "'); drop table mart_recall_summary; --"})
    assert r.status_code == 200


async def test_search_keyset_pagination(client: AsyncClient) -> None:
    # "acme" matches both FDA Acme recalls; walk one-at-a-time without overlap.
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):  # safety bound
        params: dict[str, str | int] = {"q": "acme", "limit": 1}
        if cursor:
            params["cursor"] = cursor
        body = (await client.get("/recalls/search", params=params)).json()
        seen.extend(it["source_recall_id"] for it in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert set(seen) == {"F-1001", "F-1006"}
    assert len(seen) == 2  # no overlap


async def test_search_with_total(client: AsyncClient) -> None:
    r = await client.get(
        "/recalls/search", params={"q": "acme", "with_total": "true", "limit": 100}
    )
    body = r.json()
    assert {it["source_recall_id"] for it in body["items"]} == {"F-1001", "F-1006"}
    assert body["total"] == 2  # exercises search_count_stmt end-to-end


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


async def test_cross_path_cursor_replay_returns_400(client: AsyncClient) -> None:
    # A cursor is sort-path-tagged: replaying a published_at ('p') cursor on the rank-sorted search
    # endpoint (or a rank ('r') cursor on the published_at list) must be 400, not a 5xx.
    p_cursor = (await client.get("/recalls", params={"limit": 1})).json()["next_cursor"]
    assert p_cursor is not None  # 6 seeded recalls -> page 1 of limit 1 has a next cursor
    bad = await client.get("/recalls/search", params={"q": "acme", "cursor": p_cursor})
    assert bad.status_code == 400
    assert bad.json()["error"]["type"] == "bad_cursor"

    r_cursor = (await client.get("/recalls/search", params={"q": "acme", "limit": 1})).json()[
        "next_cursor"
    ]
    assert r_cursor is not None  # "acme" matches 2 recalls -> page 1 of limit 1 has a next cursor
    bad2 = await client.get("/recalls", params={"cursor": r_cursor})
    assert bad2.status_code == 400
    assert bad2.json()["error"]["type"] == "bad_cursor"


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


async def test_detail_upc_recall_does_not_500_and_flattens(client: AsyncClient) -> None:
    # Regression: gold stores UPCs as [{"upc": "X"}] objects; the detail must flatten, not 500.
    r = await client.get("/recalls/fda/F-1001")
    assert r.status_code == 200
    assert r.json()["product_upcs"] == ["012345678905"]


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
