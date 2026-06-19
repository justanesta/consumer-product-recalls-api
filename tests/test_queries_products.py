"""Unit tests for the product-search builders — compile SQL + assert bound params (no DB)."""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from recalls_api.models.common import Source
from recalls_api.queries import products as pq


def _c(stmt: object):
    return stmt.compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]


def test_fts_stmt_uses_websearch_rank_and_limit_plus_one() -> None:
    c = _c(pq.fts_stmt("peanut butter", None, 25, None))
    sql = str(c)
    assert "websearch_to_tsquery" in sql
    assert "ts_rank_cd" in sql
    assert "@@" in sql
    assert c.params["q"] == "peanut butter"
    assert 26 in c.params.values()  # limit + 1


def test_fts_stmt_source_anded() -> None:
    c = _c(pq.fts_stmt("x", None, 25, [Source.FDA]))
    assert c.params["source"] == ["FDA"]


def test_fts_stmt_source_multi_value_uses_expanding_in() -> None:
    c = _c(pq.fts_stmt("x", None, 25, [Source.FDA, Source.USDA]))
    assert c.params["source"] == ["FDA", "USDA"]  # any-of (OR)
    assert " IN " in str(c).upper()


def test_identifier_stmt_binds_hin() -> None:
    c = _c(pq.identifier_stmt("ABC123", None, None, 25, None))
    assert c.params["hin"] == "ABC123"
    assert "published_at" in str(c).lower()


def test_identifier_stmt_binds_model() -> None:
    c = _c(pq.identifier_stmt(None, "Civic", None, 25, None))
    assert c.params["model"] == "Civic"


def test_upc_stmt_uses_jsonb_containment() -> None:
    c = _c(pq.upc_stmt("012345678905", None, 25, None))
    # Gold stores UPCs as [{"upc": "X"}] objects, so containment binds the same object shape.
    assert c.params["upc_arr"] == [{"upc": "012345678905"}]
    assert "@>" in str(c)


def test_count_stmts_reuse_predicates() -> None:
    assert _c(pq.fts_count_stmt("x", None)).params["q"] == "x"
    ci = _c(pq.identifier_count_stmt("H1", None, [Source.USCG]))
    assert ci.params["hin"] == "H1" and ci.params["source"] == ["USCG"]
    assert _c(pq.upc_count_stmt("999", None)).params["upc_arr"] == [{"upc": "999"}]
    assert "count(" in str(_c(pq.fts_count_stmt("x", None))).lower()
