"""Unit tests for ProductSearchHit — UPC flattening + the constant honesty flag."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from recalls_api.models.products import ProductSearchHit


def _base_row() -> dict[str, Any]:
    return {
        "recall_product_id": "rp-1",
        "recall_event_id": "abc",
        "source": "CPSC",
        "source_recall_id": "24-001",
        "published_at": datetime(2026, 5, 1, tzinfo=UTC),
    }


def test_hit_flattens_object_shaped_recall_upcs() -> None:
    # Gold stores recall_product_upcs as [{"upc": "X"}] objects; unwrap to bare strings.
    h = ProductSearchHit.model_validate(
        _base_row() | {"recall_product_upcs": [{"upc": "082294319754"}]}
    )
    assert h.recall_product_upcs == ["082294319754"]
    assert h.upc_is_recall_level is True


def test_hit_recall_upcs_none_becomes_empty_list() -> None:
    h = ProductSearchHit.model_validate(_base_row() | {"recall_product_upcs": None})
    assert h.recall_product_upcs == []


def test_hit_recall_upcs_tolerates_plain_string_shape() -> None:
    h = ProductSearchHit.model_validate(_base_row() | {"recall_product_upcs": ["012345678905"]})
    assert h.recall_product_upcs == ["012345678905"]
