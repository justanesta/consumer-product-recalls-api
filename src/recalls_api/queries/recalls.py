"""Core builders for ``mart_recall_summary`` (01 — Mart 1). Build statements; never execute.

Every value is bound; predicates are appended only when their filter is set. The detail key is
computed in-API as ``md5(SOURCE|recall_id)`` to hit ``UNIQUE(recall_event_id)`` — no new index.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy import Select
from sqlalchemy.sql.elements import ColumnElement

from recalls_api.deps import RecallFilters
from recalls_api.pagination import Cursor, published_at_keyset_where

# Lightweight table literal (no reflection/ORM). Column names per 01 — Mart 1 (authoritative).
recall_summary = sa.table(
    "mart_recall_summary",
    sa.column("recall_event_id", sa.Text),
    sa.column("source", sa.Text),
    sa.column("source_recall_id", sa.Text),
    sa.column("title", sa.Text),
    sa.column("recall_reason", sa.Text),
    sa.column("url", sa.Text),
    sa.column("announced_at", sa.TIMESTAMP(timezone=True)),
    sa.column("published_at", sa.TIMESTAMP(timezone=True)),
    sa.column("classification", sa.Text),
    sa.column("risk_level", sa.Text),
    sa.column("lifecycle_status", sa.Text),
    sa.column("is_active", sa.Boolean),
    sa.column("reason_category", sa.Text),
    sa.column("distribution_scope", sa.Text),
    sa.column("distribution_states", sa.Text),  # SCALAR text (01) — not the array
    sa.column("distribution_state_codes", sa.ARRAY(sa.Text)),
    sa.column("distribution_country_codes", sa.ARRAY(sa.Text)),
    sa.column("hazards", sa.JSON),
    sa.column("product_upcs", sa.JSON),
    sa.column("corrective_action", sa.Text),
    sa.column("consequence_of_defect", sa.Text),
    sa.column("primary_firm_name", sa.Text),
    sa.column("firm_count", sa.BigInteger),
    sa.column("firms", sa.JSON),
    sa.column("product_count", sa.BigInteger),
    sa.column("product_names", sa.JSON),
    sa.column("models", sa.JSON),
    sa.column("hins", sa.JSON),
    sa.column("first_seen_at", sa.TIMESTAMP(timezone=True)),
    sa.column("last_seen_at", sa.TIMESTAMP(timezone=True)),
    sa.column("edit_count", sa.Integer),
    sa.column("is_currently_active", sa.Boolean),
    sa.column("was_ever_retracted", sa.Boolean),
    sa.column("edit_event_count", sa.BigInteger),
    sa.column("has_been_edited", sa.Boolean),
)

# List projection — the small subset (plan §3). Detail selects the full row (recall_summary).
_LIST_COLS = (
    recall_summary.c.recall_event_id,
    recall_summary.c.source,
    recall_summary.c.source_recall_id,
    recall_summary.c.title,
    recall_summary.c.url,
    recall_summary.c.announced_at,
    recall_summary.c.published_at,
    recall_summary.c.classification,
    recall_summary.c.risk_level,
    recall_summary.c.lifecycle_status,
    recall_summary.c.is_active,
    recall_summary.c.reason_category,
    recall_summary.c.distribution_scope,
    recall_summary.c.primary_firm_name,
    recall_summary.c.firm_count,
    recall_summary.c.product_count,
    recall_summary.c.edit_event_count,
    recall_summary.c.has_been_edited,
)


def compute_recall_event_id(source: str, recall_id: str) -> str:
    """md5(f"{SOURCE_UPPER}|{recall_id}") — the detail key (01, confirmed for all sources)."""
    return hashlib.md5(f"{source.upper()}|{recall_id}".encode()).hexdigest()


def detail_stmt(source: str, recall_id: str) -> Select:
    """Point read on ``UNIQUE(recall_event_id)``. Full wide row."""
    key = compute_recall_event_id(source, recall_id)
    return sa.select(recall_summary).where(
        recall_summary.c.recall_event_id == sa.bindparam("rid", key)
    )


def recalls_predicates(filters: RecallFilters) -> list[ColumnElement[bool]]:
    """Conditional predicates — appended only when a filter is set. All values bound."""
    c = recall_summary.c
    conds: list[ColumnElement[bool]] = []
    if filters.source is not None:
        conds.append(c.source == sa.bindparam("source", filters.source.value))
    if filters.classification is not None:
        conds.append(c.classification == sa.bindparam("classification", filters.classification))
    if filters.is_active is not None:  # == excludes NULL rows (CPSC/NHTSA) by design
        conds.append(c.is_active == sa.bindparam("is_active", filters.is_active))
    if filters.published_after is not None:  # inclusive from the start of that day (UTC)
        conds.append(c.published_at >= sa.bindparam("pub_after", filters.published_after))
    if filters.published_before is not None:
        # Inclusive of the ENTIRE published_before day: compare against (date + 1 day) with a strict
        # `<` (date vs timestamptz — a bare `<=`/`<` on the date would drop same-day rows). Computed
        # in Python (equivalent to ``:d::date + INTERVAL '1 day'``, no fragile SQL interval math).
        conds.append(
            c.published_at
            < sa.bindparam("pub_before", filters.published_before + timedelta(days=1))
        )
    if filters.firm is not None:  # substring; unindexed (02) — accept seq cost
        conds.append(c.primary_firm_name.ilike(sa.bindparam("firm", f"%{filters.firm}%")))
    if filters.distribution_scope is not None:  # NOT NULL 4-value enum
        conds.append(c.distribution_scope == sa.bindparam("dist_scope", filters.distribution_scope))
    if filters.lifecycle_status is not None:  # NULL for CPSC/NHTSA -> excluded
        conds.append(c.lifecycle_status == sa.bindparam("lifecycle", filters.lifecycle_status))
    if filters.announced_after is not None:  # announced_at NULLABLE -> NULL rows excluded
        conds.append(c.announced_at >= sa.bindparam("ann_after", filters.announced_after))
    if filters.announced_before is not None:  # whole-day inclusive (cf. published_before)
        conds.append(
            c.announced_at
            < sa.bindparam("ann_before", filters.announced_before + timedelta(days=1))
        )
    if filters.source_recall_id is not None:  # EXACT; unique only with source
        conds.append(
            c.source_recall_id == sa.bindparam("source_recall_id", filters.source_recall_id)
        )
    return conds


def list_stmt(filters: RecallFilters, cursor: Cursor | None, limit: int) -> Select:
    """Keyset list. ORDER BY published_at DESC, recall_event_id ASC; fetch limit+1 for has_next.

    The (published_at DESC, recall_event_id) sort is index-backed by the gold-readiness R2 index of
    the same shape (applied upstream); a leading ?source= can instead use (source, published_at).
    """
    stmt = sa.select(*_LIST_COLS)
    conds = recalls_predicates(filters)
    if conds:
        stmt = stmt.where(*conds)
    if cursor is not None:
        stmt = stmt.where(
            published_at_keyset_where(
                cursor, recall_summary.c.published_at, recall_summary.c.recall_event_id
            )
        )
    return stmt.order_by(
        recall_summary.c.published_at.desc(), recall_summary.c.recall_event_id.asc()
    ).limit(limit + 1)


def list_count_stmt(filters: RecallFilters) -> Select:
    """COUNT(*) over the same WHERE, for ?with_total=true (no cursor, no limit)."""
    stmt = sa.select(sa.func.count()).select_from(recall_summary)
    conds = recalls_predicates(filters)
    if conds:
        stmt = stmt.where(*conds)
    return stmt
