"""``GET /firms/{id}`` — one canonical (cross-source) firm profile."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.errors import ITEM_ERRORS, ResourceNotFound
from recalls_api.models.firms import FirmProfile
from recalls_api.queries import firms as q

router = APIRouter(prefix="/firms", tags=["firms"])

_DESC = (
    "A single firm, merged across agencies — so a maker that appears under several (e.g. Honda "
    "under NHTSA and USCG) shows up as one profile. Includes recall counts, the per-agency "
    "breakdown (`recalls_by_source`), name variants, and agency registration records: "
    "`firm_usda_attributes` (USDA establishments), `firm_uscg_attributes` (USCG boat builders), "
    "and `firm_fda_attributes` (FDA-registered firms). Each set has a different shape and any may "
    "be empty; CPSC and NHTSA contribute none. `first_recall_at` and `last_recall_at` are null for "
    "a firm with no matched recalls. The id is opaque — get it from a recall's `firms[].firm_id`."
)


@router.get(
    "/{firm_id}",
    response_model=FirmProfile,
    responses=ITEM_ERRORS,
    summary="Fetch a firm profile with its agency registration records.",
    description=_DESC,
)
async def get_firm(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    firm_id: Annotated[
        str,
        Path(
            min_length=32,
            max_length=32,
            pattern=r"^[0-9a-f]{32}$",
            description="Opaque canonical firm id (md5 cluster id).",
        ),
    ],
) -> FirmProfile:
    # The pattern is a cheap shape guard: a malformed id -> 422 before the DB; a well-formed id
    # with no row -> 404.
    row = (await conn.execute(q.firm_stmt(firm_id))).mappings().one_or_none()
    if row is None:
        raise ResourceNotFound(f"no firm for id {firm_id}")
    return FirmProfile.model_validate(dict(row))
