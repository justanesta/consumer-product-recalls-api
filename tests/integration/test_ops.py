"""Integration tests for ops behavior: HTTP cache headers on data vs health endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_data_endpoint_has_cache_headers(client: AsyncClient) -> None:
    r = await client.get("/recalls", params={"limit": 1})
    assert r.status_code == 200
    assert r.headers["cache-control"].startswith("public, max-age=")
    assert "etag" in r.headers
    assert "last-modified" in r.headers


async def test_health_is_no_store(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.headers["cache-control"] == "no-store"


async def test_cors_allow_origin_on_get(client: AsyncClient) -> None:
    # CORSMiddleware only emits ACAO when the request carries an Origin (a cross-origin call).
    r = await client.get("/health", headers={"Origin": "https://example.com"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "*"


async def test_cors_preflight_allows_get(client: AsyncClient) -> None:
    r = await client.options(
        "/recalls",
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "*"
    assert "GET" in r.headers["access-control-allow-methods"]
