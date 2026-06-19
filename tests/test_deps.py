"""Unit tests for deps helpers — the comma-tolerant multi-value query splitter."""

from __future__ import annotations

from recalls_api.deps import split_query_list


def test_split_none_passes_through() -> None:
    assert split_query_list(None) is None


def test_split_repeated_form_unchanged() -> None:
    # FastAPI already collected ?x=A&x=B into ["A", "B"]; nothing to split.
    assert split_query_list(["CPSC", "FDA"]) == ["CPSC", "FDA"]


def test_split_comma_form_expands() -> None:
    assert split_query_list(["CPSC,FDA"]) == ["CPSC", "FDA"]


def test_split_mixed_and_whitespace() -> None:
    # A mix of repeated + comma elements, with surrounding spaces stripped on the split parts.
    assert split_query_list(["CPSC, FDA", "USDA"]) == ["CPSC", "FDA", "USDA"]


def test_split_drops_empty_parts() -> None:
    assert split_query_list(["CPSC,,FDA,"]) == ["CPSC", "FDA"]
