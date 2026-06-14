"""Core builder for ``mart_firm_profile`` (01 — Mart 3). A single point read on ``UNIQUE(firm_id)``.

The three sidecar columns carry the post-R5 names (firm_usda/uscg/fda_attributes), confirmed against
the upstream mart SQL.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Select

firm_profile = sa.table(
    "mart_firm_profile",
    sa.column("firm_id", sa.Text),
    sa.column("canonical_name", sa.Text),
    sa.column("normalized_name", sa.Text),
    sa.column("observed_names", sa.JSON),
    sa.column("observed_company_ids", sa.JSON),
    sa.column("alternate_names", sa.JSON),
    sa.column("total_recalls", sa.BigInteger),
    sa.column("active_recalls", sa.BigInteger),
    sa.column("first_recall_at", sa.TIMESTAMP(timezone=True)),
    sa.column("last_recall_at", sa.TIMESTAMP(timezone=True)),
    sa.column("roles", sa.JSON),
    sa.column("recalls_by_source", sa.JSON),
    sa.column("distinct_products", sa.Numeric),  # numeric, integer-valued -> model int (01)
    sa.column("firm_usda_attributes", sa.JSON),  # USDA (renamed from establishment_attributes, R5)
    sa.column("firm_uscg_attributes", sa.JSON),  # USCG (renamed from manufacturer_attributes, R5)
    sa.column("firm_fda_attributes", sa.JSON),  # FDA  (renamed from fda_attributes, R5)
)


def firm_stmt(firm_id: str) -> Select:
    """Point read on ``UNIQUE(firm_id)``. firm_id is an opaque md5 cluster id (01)."""
    return sa.select(firm_profile).where(firm_profile.c.firm_id == sa.bindparam("firm_id", firm_id))
