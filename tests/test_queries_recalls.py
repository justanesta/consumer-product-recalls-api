"""Unit tests for the recalls Core builders — compile the SQL + assert bound params (no DB)."""

from __future__ import annotations

import hashlib
from datetime import date, datetime

from sqlalchemy.dialects import postgresql

from recalls_api.deps import RecallFilters
from recalls_api.models.common import DistributionScope, Source
from recalls_api.pagination import Cursor, published_at_keyset_where
from recalls_api.queries import recalls as q


def _compiled(stmt: object):
    return stmt.compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]


def _no_filters() -> RecallFilters:
    return RecallFilters(None, None, None, None, None, None)


def test_compute_recall_event_id_uppercases_source() -> None:
    assert q.compute_recall_event_id("cpsc", "24-001") == q.compute_recall_event_id(
        "CPSC", "24-001"
    )
    assert q.compute_recall_event_id("FDA", "F-1") == hashlib.md5(b"FDA|F-1").hexdigest()


def test_detail_stmt_binds_md5_key() -> None:
    c = _compiled(q.detail_stmt("nhtsa", "24V-9"))
    assert c.params["rid"] == hashlib.md5(b"NHTSA|24V-9").hexdigest()
    assert "recall_event_id = " in str(c)


def test_list_stmt_no_filters_has_no_where() -> None:
    sql = str(_compiled(q.list_stmt(_no_filters(), None, 10))).upper()
    assert "WHERE" not in sql
    assert "ORDER BY" in sql and "DESC" in sql


def test_list_stmt_source_filter_binds_value() -> None:
    c = _compiled(q.list_stmt(RecallFilters([Source.FDA], None, None, None, None, None), None, 25))
    assert c.params["source"] == ["FDA"]  # expanding IN list
    assert " IN " in str(c).upper()
    assert "WHERE" in str(c).upper()


def test_list_stmt_source_multi_value_uses_expanding_in() -> None:
    c = _compiled(
        q.list_stmt(
            RecallFilters([Source.FDA, Source.CPSC], None, None, None, None, None), None, 25
        )
    )
    assert c.params["source"] == ["FDA", "CPSC"]  # any-of (OR) within the field
    assert " IN " in str(c).upper()


def test_list_stmt_classification_multi_value() -> None:
    f = RecallFilters(None, ["Class I", "Class II"], None, None, None, None)
    c = _compiled(q.list_stmt(f, None, 25))
    assert c.params["classification"] == ["Class I", "Class II"]


def test_list_stmt_limit_is_plus_one() -> None:
    c = _compiled(q.list_stmt(_no_filters(), None, 25))
    assert 26 in c.params.values()  # limit + 1 for has_next


def test_published_before_is_exclusive_next_day() -> None:
    c = _compiled(
        q.list_stmt(RecallFilters(None, None, None, None, date(2026, 5, 1), None), None, 25)
    )
    assert c.params["pub_before"] == date(2026, 5, 2)  # inclusive of the whole 2026-05-01


def test_published_after_is_inclusive_same_day() -> None:
    c = _compiled(
        q.list_stmt(RecallFilters(None, None, None, date(2026, 5, 1), None, None), None, 25)
    )
    assert c.params["pub_after"] == date(2026, 5, 1)


def test_firm_filter_wraps_substring() -> None:
    c = _compiled(q.list_stmt(RecallFilters(None, None, None, None, None, "acme"), None, 25))
    assert c.params["firm"] == "%acme%"
    assert "ILIKE" in str(c).upper()


def test_is_active_filter_uses_equality() -> None:
    c = _compiled(q.list_stmt(RecallFilters(None, None, True, None, None, None), None, 25))
    assert c.params["is_active"] is True


def test_keyset_where_parses_cursor_to_datetime() -> None:
    expr = published_at_keyset_where(
        Cursor(("2026-01-01T00:00:00+00:00", "abc")),
        q.recall_summary.c.published_at,
        q.recall_summary.c.recall_event_id,
    )
    c = expr.compile(dialect=postgresql.dialect())
    assert isinstance(c.params["cur_pub"], datetime)
    assert c.params["cur_id"] == "abc"


def test_count_stmt_reuses_predicates() -> None:
    c = _compiled(q.list_count_stmt(RecallFilters([Source.USDA], None, None, None, None, None)))
    assert c.params["source"] == ["USDA"]
    assert "COUNT(" in str(c).upper()


def test_distribution_scope_filter_binds_enum_value() -> None:
    f = RecallFilters(
        None, None, None, None, None, None, distribution_scope=[DistributionScope.REGIONAL]
    )
    c = _compiled(q.list_stmt(f, None, 25))
    assert c.params["dist_scope"] == ["Regional"]


def test_lifecycle_status_filter_binds_value() -> None:
    f = RecallFilters(None, None, None, None, None, None, lifecycle_status=["Ongoing", "Open"])
    c = _compiled(q.list_stmt(f, None, 25))
    assert c.params["lifecycle"] == ["Ongoing", "Open"]


def test_announced_after_is_inclusive_same_day() -> None:
    f = RecallFilters(None, None, None, None, None, None, announced_after=date(2026, 4, 15))
    c = _compiled(q.list_stmt(f, None, 25))
    assert c.params["ann_after"] == date(2026, 4, 15)


def test_announced_before_is_exclusive_next_day() -> None:
    f = RecallFilters(None, None, None, None, None, None, announced_before=date(2026, 4, 15))
    c = _compiled(q.list_stmt(f, None, 25))
    assert c.params["ann_before"] == date(2026, 4, 16)  # inclusive of the whole 2026-04-15


def test_source_recall_id_filter_uses_equality() -> None:
    f = RecallFilters(None, None, None, None, None, None, source_recall_id="F-1001")
    c = _compiled(q.list_stmt(f, None, 25))
    assert c.params["source_recall_id"] == "F-1001"


def test_distribution_state_filter_uppercases_and_uses_array_overlap() -> None:
    f = RecallFilters(None, None, None, None, None, None, distribution_state=["ca", "or"])
    c = _compiled(q.list_stmt(f, None, 25))
    assert c.params["dist_state"] == ["CA", "OR"]  # normalized to uppercase, any-of
    assert "&&" in str(c)  # array overlap, not containment


def test_distribution_country_filter_uppercases() -> None:
    f = RecallFilters(None, None, None, None, None, None, distribution_country=["mx", "gb"])
    c = _compiled(q.list_stmt(f, None, 25))
    assert c.params["dist_country"] == ["MX", "GB"]
    assert "&&" in str(c)


def test_search_stmt_uses_fts_and_binds_q() -> None:
    c = _compiled(
        q.search_stmt(RecallFilters(None, None, None, None, None, None), "salmonella", None, 25)
    )
    assert c.params["q"] == "salmonella"
    sql = str(c).lower()
    assert "@@" in sql and "ts_rank_cd" in sql


def test_search_stmt_applies_filters() -> None:
    c = _compiled(
        q.search_stmt(RecallFilters([Source.FDA], None, None, None, None, None), "acme", None, 25)
    )
    assert c.params["q"] == "acme"
    assert c.params["source"] == ["FDA"]


def test_search_count_stmt_counts_matches() -> None:
    c = _compiled(q.search_count_stmt(RecallFilters(None, None, None, None, None, None), "fire"))
    assert c.params["q"] == "fire"
    assert "COUNT(" in str(c).upper()
