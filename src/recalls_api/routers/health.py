"""Operational endpoints: ``/health`` (liveness) and ``/health/db`` (readiness, SELECT 1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import __version__, deps
from recalls_api.db import healthcheck
from recalls_api.errors import ERR_503
from recalls_api.models.common import DbHealth, Health

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=Health, summary="Liveness probe (no DB touch).")
async def health() -> Health:
    """Liveness: process is up. No DB touch, so the Docker/Fly probe never wakes Neon."""
    return Health(version=__version__)


@router.get(
    "/health/db",
    response_model=DbHealth,
    responses=ERR_503,
    summary="Readiness probe — verifies the read-only DB connection.",
)
async def health_db(conn: Annotated[AsyncConnection, Depends(deps.get_conn)]) -> DbHealth:
    """Readiness: SELECT 1 to Neon; a cold DB becomes 503 + Retry-After via the error handler."""
    await healthcheck(conn)  # raises OperationalError/TimeoutError on a cold DB -> handled as 503
    return DbHealth()
