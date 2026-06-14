"""Unit tests for the recall response models — jsonb coercion, scalar-vs-array geo, nested firms."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from recalls_api.models.recalls import RecallDetail, RecallSummary


def _base_row() -> dict[str, Any]:
    return {
        "recall_event_id": "abc",
        "source": "FDA",
        "source_recall_id": "F-1",
        "published_at": datetime(2026, 5, 1, tzinfo=UTC),
        "distribution_scope": "Nationwide",
    }


def test_recall_summary_minimal_defaults() -> None:
    s = RecallSummary.model_validate(_base_row())
    assert s.source is s.source.FDA
    assert s.firm_count == 0 and s.product_count == 0
    assert s.is_active is None and s.title is None


def test_recall_detail_coerces_null_arrays_to_empty() -> None:
    row = _base_row() | {
        "product_names": None,
        "models": None,
        "hins": None,
        "product_upcs": None,
        "firms": None,
    }
    d = RecallDetail.model_validate(row)
    assert d.product_names == [] and d.models == [] and d.hins == []
    assert d.product_upcs == [] and d.firms == []
    assert d.hazards is None  # hazards is NOT coerced — null stays null


def test_recall_detail_parses_nested_firms() -> None:
    row = _base_row() | {
        "firms": [
            {
                "firm_id": "f1",
                "name": "Acme",
                "role": "establishment",
                "match_confidence": "fei_exact",
            }
        ]
    }
    d = RecallDetail.model_validate(row)
    assert len(d.firms) == 1 and d.firms[0].name == "Acme"


def test_recall_detail_scalar_states_vs_codes_array() -> None:
    row = _base_row() | {"distribution_states": "CA, OR", "distribution_state_codes": ["CA", "OR"]}
    d = RecallDetail.model_validate(row)
    assert d.distribution_states == "CA, OR"  # scalar prose string
    assert d.distribution_state_codes == ["CA", "OR"]  # parsed codes array
