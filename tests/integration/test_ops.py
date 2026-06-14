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
