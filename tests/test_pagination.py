"""Keyset cursor codec (round-trip + property + tamper), slice_page, and build_page."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recalls_api.errors import BadCursor
from recalls_api.models.common import Page
from recalls_api.pagination import Cursor, build_page, slice_page


def test_cursor_roundtrip() -> None:
    c = Cursor(("2026-01-01T00:00:00+00:00", "abc123"))
    assert Cursor.decode(c.encode()) == c


_value = st.one_of(
    st.text(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.none(),
    st.booleans(),
)


@given(st.lists(_value, min_size=1, max_size=4))
def test_cursor_roundtrip_property(values: list[object]) -> None:
    decoded = Cursor.decode(Cursor(tuple(values)).encode())
    assert list(decoded.values) == values


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
