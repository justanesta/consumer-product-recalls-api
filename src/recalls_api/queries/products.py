"""Core builders for ``mart_product_search`` (01 — Mart 2). Pure: build statements; never execute.

Three access paths (each with an optional ``source`` AND-ed, plus a count for ?with_total):
  - FTS: ``search_vector @@ websearch_to_tsquery('english', :q)``, ranked by ts_rank_cd (GIN).
  - identifier: exact ``hin = :hin`` / ``model = :model`` (btree).
  - UPC: recall-level containment ``recall_product_upcs @> :upc_arr`` (per-product ``upc`` is
    NULL for every row, so it is never queried).
``websearch_to_tsquery`` is injection-safe and never raises on bad input. No fuzzy/typo search.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.elements import ColumnElement

from recalls_api.models.common import Source
from recalls_api.pagination import Cursor, date_keyset_where, rank_keyset_where

product_search = sa.table(
    "mart_product_search",
    sa.column("recall_product_id", sa.Text),
    sa.column("recall_event_id", sa.Text),
    sa.column("source", sa.Text),
    sa.column("source_recall_id", sa.Text),
    sa.column("product_name", sa.Text),
    sa.column("product_description", sa.Text),
    sa.column("model", sa.Text),
    sa.column("type", sa.Text),
    sa.column("model_year", sa.Text),  # FLAGGED int|text (01) — read permissively
    sa.column("hin", sa.Text),
    # NB: the mart also has an all-NULL per-product `upc` column; the API no longer projects it
    # (audit A9 — see recall_product_upcs for the recall-level UPC-search path).
    sa.column("recall_title", sa.Text),
    sa.column("classification", sa.Text),
    sa.column("risk_level", sa.Text),
    sa.column("published_at", sa.TIMESTAMP(timezone=True)),
    sa.column("url", sa.Text),
    sa.column("is_active", sa.Boolean),
    sa.column("firm_name", sa.Text),
    sa.column("recall_product_upcs", sa.JSON),
    # search_vector (tsvector) is referenced via literal_column in the FTS predicate, not selected.
)

_HIT_COLS = (
    product_search.c.recall_product_id,
    product_search.c.recall_event_id,
    product_search.c.source,
    product_search.c.source_recall_id,
    product_search.c.product_name,
    product_search.c.product_description,
    product_search.c.model,
    product_search.c.type,
    product_search.c.model_year,
    product_search.c.hin,
    product_search.c.recall_title,
    product_search.c.classification,
    product_search.c.risk_level,
    product_search.c.published_at,
    product_search.c.url,
    product_search.c.is_active,
    product_search.c.firm_name,
    product_search.c.recall_product_upcs,
)

_search_vector = sa.literal_column("search_vector")  # tsvector; GIN-indexed


def _source_cond(sources: list[Source] | None) -> ColumnElement[bool] | None:
    if not sources:
        return None
    return product_search.c.source.in_(
        sa.bindparam("source", [s.value for s in sources], expanding=True)
    )


def _all(*conds: ColumnElement[bool] | None) -> ColumnElement[bool]:
    return sa.and_(*[c for c in conds if c is not None])


def _tsquery(q: str) -> ColumnElement:
    # 'english' must be a SQL literal (it resolves the regconfig overload); a bound *param* would
    # leave only websearch_to_tsquery(text, text), which does not exist -> a runtime error.
    return sa.func.websearch_to_tsquery(sa.literal_column("'english'"), sa.bindparam("q", q))


def _order_by_published(stmt: Select, cursor: Cursor | None, limit: int) -> Select:
    # Products stay on published_at ('p'): mart_product_search carries no event_date, and the
    # announce-recency feed change (ADR 0038 §2026-W26) was scoped to the /recalls list only.
    if cursor is not None:
        stmt = stmt.where(
            date_keyset_where(
                cursor, "p", product_search.c.published_at, product_search.c.recall_product_id
            )
        )
    return stmt.order_by(
        product_search.c.published_at.desc(), product_search.c.recall_product_id.asc()
    ).limit(limit + 1)


def fts_stmt(q: str, cursor: Cursor | None, limit: int, sources: list[Source] | None) -> Select:
    tq = _tsquery(q)
    rank = sa.func.ts_rank_cd(_search_vector, tq).label("rank")
    stmt = sa.select(*_HIT_COLS, rank).where(
        _all(_search_vector.op("@@")(tq), _source_cond(sources))
    )
    if cursor is not None:
        stmt = stmt.where(rank_keyset_where(cursor, rank, product_search.c.recall_product_id))
    # rank is NOT an ordered index path (the GIN serves @@); the sort is over the matched set (01).
    return stmt.order_by(rank.desc(), product_search.c.recall_product_id.asc()).limit(limit + 1)


def fts_count_stmt(q: str, sources: list[Source] | None) -> Select:
    where = _all(_search_vector.op("@@")(_tsquery(q)), _source_cond(sources))
    return sa.select(sa.func.count()).select_from(product_search).where(where)


def _identifier_where(
    hin: str | None, model: str | None, sources: list[Source] | None
) -> ColumnElement[bool]:
    hin_c = product_search.c.hin == sa.bindparam("hin", hin) if hin is not None else None
    model_c = product_search.c.model == sa.bindparam("model", model) if model is not None else None
    return _all(hin_c, model_c, _source_cond(sources))


def identifier_stmt(
    hin: str | None,
    model: str | None,
    cursor: Cursor | None,
    limit: int,
    sources: list[Source] | None,
) -> Select:
    stmt = sa.select(*_HIT_COLS).where(_identifier_where(hin, model, sources))
    return _order_by_published(stmt, cursor, limit)


def identifier_count_stmt(
    hin: str | None, model: str | None, sources: list[Source] | None
) -> Select:
    return (
        sa.select(sa.func.count())
        .select_from(product_search)
        .where(_identifier_where(hin, model, sources))
    )


def _upc_where(upc: str, sources: list[Source] | None) -> ColumnElement[bool]:
    # Gold stores UPCs as an array of objects [{"upc": "X"}] (not bare strings), so containment must
    # match that shape: [{"upc":"X"}] @> [{"upc":"X"}]. Stays GIN-served on recall_product_upcs.
    contains = sa.cast(product_search.c.recall_product_upcs, JSONB).op("@>")(
        sa.bindparam("upc_arr", [{"upc": upc}], type_=JSONB)
    )
    return _all(contains, _source_cond(sources))


def upc_stmt(upc: str, cursor: Cursor | None, limit: int, sources: list[Source] | None) -> Select:
    stmt = sa.select(*_HIT_COLS).where(_upc_where(upc, sources))
    return _order_by_published(stmt, cursor, limit)


def upc_count_stmt(upc: str, sources: list[Source] | None) -> Select:
    return sa.select(sa.func.count()).select_from(product_search).where(_upc_where(upc, sources))
