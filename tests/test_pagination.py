"""Keyset cursor codec (round-trip + property + tamper + cross-path), slice_page, build_page."""

from __future__ import annotations

import base64
import json

import pytest
import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st

from recalls_api.errors import BadCursor
from recalls_api.models.common import Page
from recalls_api.pagination import (
    Cursor,
    build_page,
    date_keyset_where,
    rank_keyset_where,
    slice_page,
)


def _token(payload: object) -> str:
    """Encode an arbitrary JSON payload as a cursor token (to forge wrong-shape cursors)."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def test_cursor_roundtrip_preserves_kind() -> None:
    e = Cursor(("2026-01-01T00:00:00+00:00", "abc123"), "e")
    p = Cursor(("2026-01-01T00:00:00+00:00", "abc123"), "p")
    r = Cursor((0.5732, "abc123"), "r")
    assert Cursor.decode(e.encode()) == e
    assert Cursor.decode(p.encode()) == p
    assert Cursor.decode(r.encode()) == r
    assert Cursor.decode(e.encode()).kind == "e"
    assert Cursor.decode(r.encode()).kind == "r"


_value = st.one_of(
    st.text(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.none(),
    st.booleans(),
)


@given(st.lists(_value, min_size=2, max_size=2), st.sampled_from(["e", "p", "r"]))
def test_cursor_roundtrip_property(values: list[object], kind: str) -> None:
    decoded = Cursor.decode(Cursor(tuple(values), kind).encode())  # type: ignore[arg-type]
    assert list(decoded.values) == values
    assert decoded.kind == kind


@pytest.mark.parametrize(
    "bad",
    [
        "",  # empty -> json error
        "!!!not-base64!!!",  # invalid b64 chars
        "e30",  # decodes to "{}" -> dict, not a list
        "MTIz",  # decodes to "123" -> int, not a list
        "bm90anNvbg",  # decodes to "notjson" -> json error
    ],
)
def test_cursor_tamper_raises_bad_cursor(bad: str) -> None:
    with pytest.raises(BadCursor):
        Cursor.decode(bad)


@pytest.mark.parametrize(
    "payload",
    [
        ["2026-01-01", "abc"],  # legacy 2-element (no kind tag) -> rejected
        ["x", "2026-01-01", "abc"],  # unknown kind tag -> rejected
        ["p", "abc"],  # tagged but only 2 elements -> rejected
        ["p", "v", "id", "extra"],  # 4 elements -> rejected
        {"k": "p"},  # not a list
    ],
)
def test_cursor_wrong_shape_or_kind_raises_bad_cursor(payload: object) -> None:
    # A decodable-but-wrong-shape/kind payload must raise BadCursor (400), not crash downstream.
    with pytest.raises(BadCursor):
        Cursor.decode(_token(payload))


def test_date_keyset_rejects_rank_cursor() -> None:
    # Cross-path replay: a rank ('r') cursor on the date seek builder -> BadCursor, not a
    # float-bound-as-timestamptz 5xx.
    with pytest.raises(BadCursor):
        date_keyset_where(Cursor((0.5, "abc"), "r"), "e", sa.column("event_date"), sa.column("id"))


def test_date_keyset_rejects_cross_date_kind() -> None:
    # The two date paths share the builder but carry distinct tags: a products 'p' cursor on the
    # recalls 'e' path (and vice versa) must 400 -- a /recalls cursor can't seek /products' column.
    with pytest.raises(BadCursor):
        date_keyset_where(
            Cursor(("2026-01-01T00:00:00+00:00", "abc"), "p"),
            "e",
            sa.column("event_date"),
            sa.column("id"),
        )
    with pytest.raises(BadCursor):
        date_keyset_where(
            Cursor(("2026-01-01T00:00:00+00:00", "abc"), "e"),
            "p",
            sa.column("published_at"),
            sa.column("id"),
        )


def test_rank_keyset_rejects_date_cursor() -> None:
    with pytest.raises(BadCursor):
        rank_keyset_where(
            Cursor(("2026-01-01T00:00:00+00:00", "abc"), "e"), sa.column("rank"), sa.column("id")
        )


def test_slice_page() -> None:
    assert slice_page([1, 2, 3], 2) == ([1, 2], True)  # limit+1 fetched -> has_next
    assert slice_page([1, 2], 2) == ([1, 2], False)
    assert slice_page([], 2) == ([], False)


def test_build_page() -> None:
    page = build_page([1, 2], limit=2, next_cursor="cur", total=None)
    assert isinstance(page, Page)
    assert page.items == [1, 2]
    assert page.next_cursor == "cur"
    assert page.limit == 2
    assert page.total is None
