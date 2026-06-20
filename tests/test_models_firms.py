"""Unit tests for the FirmProfile model — null coercion and per-source sidecar parsing."""

from __future__ import annotations

from typing import Any

from recalls_api.models.firms import FirmProfile, UscgManufacturer, UsdaEstablishment


def _base() -> dict[str, Any]:
    return {"firm_id": "x", "canonical_name": "Acme", "normalized_name": "acme"}


def test_firm_profile_coerces_nulls() -> None:
    f = FirmProfile.model_validate(
        _base()
        | {
            "firm_usda_attributes": None,
            "firm_uscg_attributes": None,
            "firm_fda_attributes": None,
            "observed_names": None,
            "roles": None,
            "recalls_by_source": None,
        }
    )
    assert f.firm_usda_attributes == []
    assert f.firm_uscg_attributes == []
    assert f.firm_fda_attributes == []
    assert f.observed_names == [] and f.roles == []
    assert f.recalls_by_source == {}
    assert f.total_recalls == 0


def test_firm_profile_parses_fda_sidecar() -> None:
    f = FirmProfile.model_validate(
        _base()
        | {
            "firm_fda_attributes": [
                {"firm_fei_num": 1000000001, "firm_legal_nam": "ACME FOODS INC"}
            ],
            "recalls_by_source": {"FDA": 2},
        }
    )
    assert len(f.firm_fda_attributes) == 1
    assert f.firm_fda_attributes[0].firm_legal_nam == "ACME FOODS INC"
    assert f.firm_fda_attributes[0].firm_fei_num == 1000000001
    assert f.recalls_by_source == {"FDA": 2}


def test_usda_establishment_coerces_numeric_identifiers() -> None:
    # Real mart JSONB carries numeric zip/fips_code/establishment_id (not text); the str fields must
    # coerce at the trust boundary instead of raising ResponseValidationError -> 500. See
    # project_scope/handover-usda-uscg-firm-sidecar-500-2026-06-20.md.
    e = UsdaEstablishment.model_validate(
        {"establishment_id": 46841, "zip": 55101, "fips_code": 27053}
    )
    assert e.establishment_id == "46841"
    assert e.zip == "55101"
    assert e.fips_code == "27053"


def test_uscg_manufacturer_coerces_numeric_and_null_prior_holders() -> None:
    m = UscgManufacturer.model_validate({"mic": 12345, "zip": 48108, "prior_holders": None})
    assert m.mic == "12345"
    assert m.zip == "48108"
    assert m.prior_holders == []  # None -> [] (the nested-row validator, not the top-level one)


def test_firm_profile_parses_numeric_usda_uscg_sidecars() -> None:
    # End-to-end via FirmProfile: a numeric zip/fips inside a sidecar row, and a null prior_holders,
    # must not 500 the whole firm response (the production trigger).
    f = FirmProfile.model_validate(
        _base()
        | {
            "firm_usda_attributes": [{"establishment_id": "M1", "zip": 55101, "fips_code": 27053}],
            "firm_uscg_attributes": [{"mic": "ABC", "zip": 48108, "prior_holders": None}],
        }
    )
    assert f.firm_usda_attributes[0].zip == "55101"
    assert f.firm_usda_attributes[0].fips_code == "27053"
    assert f.firm_uscg_attributes[0].zip == "48108"
    assert f.firm_uscg_attributes[0].prior_holders == []
