"""Integration tests for /firms/{id} against the seeded gold cassette."""

from __future__ import annotations

from httpx import AsyncClient

_ACME = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # FDA only
_GLOBEX = "11111111111111111111111111111111"  # CPSC only (no sidecar)
_TYSON = "22222222222222222222222222222222"  # USDA only (numeric zip/fips_code in sidecar)
_BOATY = "55555555555555555555555555555555"  # USCG only (numeric zip, null prior_holders)
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
    r = await client.get(f"/firms/{_TYSON}")
    assert r.status_code == 200
    f = r.json()
    assert len(f["firm_usda_attributes"]) == 1
    est = f["firm_usda_attributes"][0]
    assert est["establishment_id"] == "M12345"
    # numeric zip/fips_code in the mart JSONB are coerced to strings on the wire (not a 500)
    assert est["zip"] == "72762"
    assert est["fips_code"] == "5007"
    # dbas/activities arrive as jsonb arrays from the FSIS directory; collapsed to CSV (not a 500)
    assert est["dbas"] == "TYSON, TYSON FOODS"
    assert est["activities"] == "Slaughter, Processing"


async def test_firm_with_uscg_sidecar(client: AsyncClient) -> None:
    # USCG sidecar carries a numeric zip and a null prior_holders in the seed; both used to 500 the
    # response before the model coercion fix (handover-usda-uscg-firm-sidecar-500-2026-06-20).
    r = await client.get(f"/firms/{_BOATY}")
    assert r.status_code == 200
    f = r.json()
    assert len(f["firm_uscg_attributes"]) == 1
    mfr = f["firm_uscg_attributes"][0]
    assert mfr["mic"] == "BMC"
    assert mfr["zip"] == "33101"  # numeric -> coerced to string
    assert mfr["prior_holders"] == []  # null -> []
    assert f["firm_usda_attributes"] == [] and f["firm_fda_attributes"] == []


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
