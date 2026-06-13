"""Operational endpoints: ``/health`` (liveness) and ``/health/db`` (readiness, SELECT 1)."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from recalls_api import deps
from recalls_api.db import healthcheck

router = APIRouter(tags=["ops"])
log = structlog.get_logger(__name__)


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: process is up. No DB touch, so the Docker/Fly probe never wakes Neon."""
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(
    conn: Annotated[AsyncConnection, Depends(deps.get_conn)],
    response: Response,
) -> dict[str, str]:
    """Readiness: a SELECT 1 to Neon. Cold/asleep Neon -> 503 + Retry-After, never hang."""
    try:
        ok = await healthcheck(conn)
    except (OperationalError, DBAPIError, TimeoutError) as exc:
        log.warning("health.db_unavailable", error=str(exc))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.headers["Retry-After"] = "5"
        return {"status": "degraded", "db": "unavailable"}
    return {"status": "ok", "db": "ok" if ok else "unexpected"}
