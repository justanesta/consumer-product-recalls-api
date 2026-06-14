"""Integration tests for /firms/{id} against the seeded gold cassette."""

from __future__ import annotations

from httpx import AsyncClient

_ACME = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # FDA only
_GLOBEX = "11111111111111111111111111111111"  # CPSC only (no sidecar)
_TYSON = "22222222222222222222222222222222"  # USDA only
_MULTI = "cccccccccccccccccccccccccccccccc"  # cross-source FDA + USDA


async def test_firm_with_fda_sidecar(client: AsyncClient) -> None:
    f = (await client.get(f"/firms/{_ACME}")).json()
    assert f["canonical_name"] == "Acme Foods Inc"
    assert f["total_recalls"] == 2 and f["active_recalls"] == 1
    assert f["recalls_by_source"] == {"FDA": 2}
    assert len(f["firm_fda_attributes"]) == 1
    assert f["firm_fda_attributes"][0]["firm_legal_nam"] == "ACME FOODS INC"
    assert f["firm_usda_attributes"] == [] and f["firm_uscg_attributes"] == []


async def test_cpsc_firm_has_no_sidecar(client: AsyncClient) -> None:
    f = (await client.get(f"/firms/{_GLOBEX}")).json()
    assert f["recalls_by_source"] == {"CPSC": 1}
    assert f["firm_usda_attributes"] == []
    assert f["firm_uscg_attributes"] == []
    assert f["firm_fda_attributes"] == []


async def test_firm_with_usda_sidecar(client: AsyncClient) -> None:
    f = (await client.get(f"/firms/{_TYSON}")).json()
    assert len(f["firm_usda_attributes"]) == 1
    assert f["firm_usda_attributes"][0]["establishment_id"] == "M12345"


async def test_cross_source_firm_two_sidecars(client: AsyncClient) -> None:
    f = (await client.get(f"/firms/{_MULTI}")).json()
    assert f["recalls_by_source"] == {"FDA": 1, "USDA": 1}
    assert len(f["firm_fda_attributes"]) == 1
    assert len(f["firm_usda_attributes"]) == 1
    assert f["firm_uscg_attributes"] == []


async def test_firm_not_found_returns_404(client: AsyncClient) -> None:
    r = await client.get("/firms/ffffffffffffffffffffffffffffffff")
    assert r.status_code == 404
    assert r.json()["error"]["type"] == "not_found"


async def test_malformed_firm_id_returns_422(client: AsyncClient) -> None:
    r = await client.get("/firms/not-a-valid-id")
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "invalid_parameter"
