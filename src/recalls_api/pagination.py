"""Keyset (seek) pagination: a pure opaque cursor codec + seek-WHERE builders + page helpers.

No DB handle and no I/O — every function is unit-tested without Postgres. The cursor is an opaque
base64url payload ``[kind, sort_value, id]``; a tampered, wrong-shape, or cross-sort-path cursor
raises ``BadCursor`` (400).

Order shapes (01 keyset sort keys; matches the R2 index ``(published_at DESC, recall_event_id)``).
Each shape is tagged so a cursor minted on one path cannot be silently replayed on another:
  - ``kind='p'`` — recalls list / product identifier+UPC paths: ``(published_at DESC, <id> ASC)``
  - ``kind='r'`` — recall/product FTS paths: ``(ts_rank_cd DESC, <id> ASC)`` — rank is an app-level
    keyset over the matched set (the GIN serves the ``@@`` match, not the sort).

A DESC-then-ASC compound can't use a plain row-value ``<`` (all-ascending), so the WHERE expands to
``col < :c OR (col = :c AND id > :id)`` with bound params.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.sql.elements import ColumnElement

from recalls_api.errors import BadCursor

CursorKind = Literal["p", "r"]  # 'p' = published_at (ISO date), 'r' = rank (float)


@dataclass(frozen=True, slots=True)
class Cursor:
    """The decoded last-row sort tuple plus its sort-kind tag.

    ``kind='p'`` -> ``(published_at_iso, id)`` for the ``published_at DESC`` paths; ``kind='r'`` ->
    ``(rank, id)`` for the ``ts_rank_cd DESC`` FTS paths. The tag makes the opaque cursor
    self-describing: a cursor minted on one sort path and replayed on another is rejected with
    ``BadCursor`` (400) by the seek-WHERE builder, instead of binding a float as a ``timestamptz``
    (or a date string into a numeric compare) and leaking a 5xx. Payload: ``[kind, value, id]``.
    """

    values: tuple[Any, ...]
    kind: CursorKind

    def encode(self) -> str:
        raw = json.dumps([self.kind, *self.values], separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")  # drop padding

    @classmethod
    def decode(cls, token: str) -> Cursor:
        try:
            pad = "=" * (-len(token) % 4)
            raw = base64.urlsafe_b64decode(token + pad)
            payload = json.loads(raw)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise BadCursor("malformed pagination cursor") from exc
        # Wire payload is [kind, sort_value, id]: a 3-element list whose head is a known sort-kind
        # tag. Guarding shape AND tag here means a wrong-shape or cross-path payload (legacy
        # 2-element, unknown kind) raises BadCursor (400) before a seek-WHERE builder unpacks it —
        # an uncaught crash downstream would leak a 5xx.
        if not isinstance(payload, list) or len(payload) != 3 or payload[0] not in ("p", "r"):
            raise BadCursor("cursor payload has an unexpected shape")
        kind, sort_value, ident = payload
        return cls(values=(sort_value, ident), kind=kind)


def published_at_keyset_where(
    cursor: Cursor,
    pub_col: ColumnElement[datetime],
    id_col: ColumnElement[str],
) -> ColumnElement[bool]:
    """Seek WHERE for ``ORDER BY published_at DESC, id ASC``. Bound params only.

    The cursor carries published_at as an ISO string (JSON-safe); parse it back to a ``datetime`` so
    asyncpg binds a ``timestamptz`` (a bare str would fail the timestamptz comparison).
    """
    # A rank ('r') cursor here would bind a float as a timestamptz -> 5xx; reject as 400 instead.
    if cursor.kind != "p":
        raise BadCursor("pagination cursor is not valid for this sort order")
    cur_pub_raw, cur_id = cursor.values
    cur_pub = datetime.fromisoformat(cur_pub_raw) if isinstance(cur_pub_raw, str) else cur_pub_raw
    p = sa.bindparam("cur_pub", cur_pub, type_=sa.TIMESTAMP(timezone=True))
    i = sa.bindparam("cur_id", cur_id, type_=sa.Text())
    return sa.or_(pub_col < p, sa.and_(pub_col == p, id_col > i))


def rank_keyset_where(
    cursor: Cursor,
    rank_expr: ColumnElement[float],
    id_col: ColumnElement[str],
) -> ColumnElement[bool]:
    """Seek WHERE for ``ts_rank_cd DESC, recall_product_id ASC`` (app-level over the match)."""
    # A published_at ('p') cursor here would compare a date string numerically -> 5xx; 400 instead.
    if cursor.kind != "r":
        raise BadCursor("pagination cursor is not valid for this sort order")
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
