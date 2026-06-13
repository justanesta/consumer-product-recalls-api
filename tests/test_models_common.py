"""Cross-cutting models: Source enum, the Page[T] envelope, FirmRef, health bodies."""

from __future__ import annotations

from recalls_api.models.common import DbHealth, FirmRef, Health, Page, Source


def test_source_is_closed_uppercase_enum() -> None:
    assert Source("CPSC") is Source.CPSC
    assert Source.USCG.value == "USCG"
    assert {s.value for s in Source} == {"CPSC", "FDA", "USDA", "NHTSA", "USCG"}


def test_page_defaults() -> None:
    page = Page[int](items=[1, 2], limit=25)
    assert page.items == [1, 2]
    assert page.next_cursor is None
    assert page.total is None


def test_firmref_from_mapping() -> None:
    fr = FirmRef.model_validate(
        {"firm_id": "x", "name": "Acme", "role": "manufacturer", "match_confidence": "exact_name"}
    )
    assert fr.name == "Acme"
    assert fr.role == "manufacturer"


def test_health_bodies() -> None:
    assert Health(version="0.1.0").status == "ok"
    assert DbHealth().database == "reachable"
