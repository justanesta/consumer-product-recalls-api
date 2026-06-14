"""Unit tests for the FirmProfile model — null coercion and per-source sidecar parsing."""

from __future__ import annotations

from typing import Any

from recalls_api.models.firms import FirmProfile


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
