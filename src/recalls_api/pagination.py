"""Keyset (seek) pagination: a pure opaque cursor codec + seek-WHERE builders + page helpers.

No DB handle and no I/O — every function is unit-tested without Postgres. The cursor is an opaque
base64url payload of the last row's sort tuple; a tampered cursor raises ``BadCursor`` (400).

Order shapes (01 keyset sort keys; matches the R2 index ``(published_at DESC, recall_event_id)``):
  - recalls list / product identifier+UPC paths: ``(published_at DESC, <id> ASC)``
  - product FTS path: ``(ts_rank_cd DESC, recall_product_id ASC)`` — rank is an app-level keyset
    over the matched set (the GIN serves the ``@@`` match, not the sort).

A DESC-then-ASC compound can't use a plain row-value ``<`` (all-ascending), so the WHERE expands to
``col < :c OR (col = :c AND id > :id)`` with bound params.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql.elements import ColumnElement

from recalls_api.errors import BadCursor


@dataclass(frozen=True, slots=True)
class Cursor:
    """The decoded last-row sort tuple, e.g. ``(published_at_iso, id)`` or ``(rank, id)``."""

    values: tuple[Any, ...]

    def encode(self) -> str:
        raw = json.dumps(list(self.values), separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")  # drop padding

    @classmethod
    def decode(cls, token: str) -> Cursor:
        try:
            pad = "=" * (-len(token) % 4)
            raw = base64.urlsafe_b64decode(token + pad)
            values = json.loads(raw)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise BadCursor("malformed pagination cursor") from exc
        if not isinstance(values, list):
            raise BadCursor("cursor payload is not a tuple")
        return cls(values=tuple(values))


def published_at_keyset_where(
    cursor: Cursor,
    pub_col: ColumnElement[datetime],
    id_col: ColumnElement[str],
) -> ColumnElement[bool]:
    """Seek WHERE for ``ORDER BY published_at DESC, id ASC``. Bound params only."""
    cur_pub, cur_id = cursor.values
    p = sa.bindparam("cur_pub", cur_pub)
    i = sa.bindparam("cur_id", cur_id)
    return sa.or_(pub_col < p, sa.and_(pub_col == p, id_col > i))


def rank_keyset_where(
    cursor: Cursor,
    rank_expr: ColumnElement[float],
    id_col: ColumnElement[str],
) -> ColumnElement[bool]:
    """Seek WHERE for ``ts_rank_cd DESC, recall_product_id ASC`` (app-level over the match)."""
    cur_rank, cur_id = cursor.values
    r = sa.bindparam("cur_rank", cur_rank)
    i = sa.bindparam("cur_id", cur_id)
    return sa.or_(rank_expr < r, sa.and_(rank_expr == r, id_col > i))


def slice_page(rows: list[Any], limit: int) -> tuple[list[Any], bool]:
    """Given ``limit + 1`` fetched rows, return ``(page_rows, has_next)``."""
    has_next = len(rows) > limit
    return rows[:limit], has_next


def build_page(
    items: list[Any], limit: int, next_cursor: str | None, total: int | None = None
) -> Any:
    """Construct the ``Page[T]`` envelope — the single place the response shape is built.

    Imported locally to avoid a module-level cycle with the pure codec.
    """
    from recalls_api.models.common import Page

    return Page(items=items, next_cursor=next_cursor, limit=limit, total=total)
