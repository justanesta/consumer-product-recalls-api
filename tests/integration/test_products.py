"""Integration tests for /products/search against the seeded gold cassette."""

from __future__ import annotations

from httpx import AsyncClient


async def test_keyword_fts_single_hit_has_rank(client: AsyncClient) -> None:
    body = (await client.get("/products/search", params={"q": "peanut", "limit": 50})).json()
    assert {h["recall_product_id"] for h in body["items"]} == {"rp-001"}
    assert body["items"][0]["rank"] is not None  # FTS path populates rank


async def test_keyword_fts_matches_firm_name(client: AsyncClient) -> None:
    # "acme" appears in the firm name of two products (peanut butter + cereal).
    body = (await client.get("/products/search", params={"q": "acme", "limit": 50})).json()
    assert {h["recall_product_id"] for h in body["items"]} == {"rp-001", "rp-005"}


async def test_identifier_hin_exact(client: AsyncClient) -> None:
    body = (await client.get("/products/search", params={"hin": "ABC12345D404"})).json()
    assert {h["recall_product_id"] for h in body["items"]} == {"rp-004"}
    assert body["items"][0]["rank"] is None  # identifier path: no rank


async def test_identifier_model_exact(client: AsyncClient) -> None:
    body = (await client.get("/products/search", params={"model": "Civic"})).json()
    assert {h["recall_product_id"] for h in body["items"]} == {"rp-002"}


async def test_upc_recall_level_containment(client: AsyncClient) -> None:
    body = (await client.get("/products/search", params={"upc": "012345678905"})).json()
    hit = body["items"][0]
    assert {h["recall_product_id"] for h in body["items"]} == {"rp-001"}
    assert hit["upc_is_recall_level"] is True
    assert hit["upc"] is None  # the per-product upc column is all-null


async def test_upc_miss_is_empty_not_error(client: AsyncClient) -> None:
    body = (await client.get("/products/search", params={"upc": "000000000000"})).json()
    assert body["items"] == []


async def test_source_is_anded(client: AsyncClient) -> None:
    none = (await client.get("/products/search", params={"q": "acme", "source": "USCG"})).json()
    assert none["items"] == []
    fda = (await client.get("/products/search", params={"q": "acme", "source": "FDA"})).json()
    assert {h["recall_product_id"] for h in fda["items"]} == {"rp-001", "rp-005"}


async def test_source_multi_value_any_of(client: AsyncClient) -> None:
    # source any-of (OR): FDA or USCG still returns only the acme (FDA) products; USCG adds none.
    body = (await client.get("/products/search", params={"q": "acme", "source": "FDA,USCG"})).json()
    assert {h["recall_product_id"] for h in body["items"]} == {"rp-001", "rp-005"}


async def test_upc_object_shape_containment_matches(client: AsyncClient) -> None:
    # Regression: recall_product_upcs is [{"upc": "X"}] in gold; containment must still match.
    body = (await client.get("/products/search", params={"upc": "012345678905"})).json()
    assert {h["recall_product_id"] for h in body["items"]} == {"rp-001"}
    assert body["items"][0]["recall_product_upcs"] == ["012345678905"]  # flattened in the response


async def test_require_one_selector_returns_422(client: AsyncClient) -> None:
    r = await client.get("/products/search")
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "invalid_parameter"


async def test_precedence_q_over_identifier(client: AsyncClient) -> None:
    # q present -> keyword path even when hin is also supplied.
    body = (
        await client.get("/products/search", params={"q": "peanut", "hin": "ABC12345D404"})
    ).json()
    assert {h["recall_product_id"] for h in body["items"]} == {"rp-001"}


async def test_with_total(client: AsyncClient) -> None:
    body = (await client.get("/products/search", params={"q": "acme", "with_total": "true"})).json()
    assert body["total"] == 2
