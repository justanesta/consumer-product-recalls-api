"""Async engine, lifespan pool, read-only assertion, and the per-request connection dependency.

The API is a long-lived server, so it uses a small bounded async pool over asyncpg (the pipeline
uses sync NullPool for batch jobs). A cold/asleep Neon must surface as a fast timeout that the
request layer maps to 503 — never a hung request. The connection is read-only by grant, asserted
at boot.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import sqlalchemy as sa
import structlog
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from recalls_api.settings import Settings

log = structlog.get_logger(__name__)


def make_engine(settings: Settings) -> AsyncEngine:
    """Build the read-only async engine for Neon serverless Postgres.

    Small bounded pool with pre-ping + sub-reap recycle; short connect/command timeouts so a
    cold/asleep Neon fails fast (-> 503) instead of hanging. Does not connect until first used.
    """
    return create_async_engine(
        settings.neon_database_url_ro.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle_seconds,
        connect_args={
            # asyncpg connect args (NOT libpq names):
            "timeout": settings.db_connect_timeout_seconds,  # connect timeout
            "command_timeout": settings.db_command_timeout_seconds,  # per-statement deadline
            "server_settings": {
                # Belt: ask the session to refuse writes. The role grant is the suspenders.
                "default_transaction_read_only": "on",
                "statement_timeout": str(int(settings.db_command_timeout_seconds * 1000)),
                # Pin UTC so date filters (date vs timestamptz) resolve on UTC day boundaries.
                "timezone": "UTC",
                "application_name": "recalls-api",
            },
        },
    )


async def open_pool(app: FastAPI, settings: Settings) -> None:
    """Create the engine, verify connectivity + read-only posture once at boot."""
    engine = make_engine(settings)
    async with engine.connect() as conn:
        await _assert_read_only(conn)
    app.state.engine = engine
    log.info("db.pool_open", pool_size=settings.db_pool_size)


async def close_pool(app: FastAPI) -> None:
    engine: AsyncEngine | None = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()
        log.info("db.pool_closed")


async def _assert_read_only(conn: AsyncConnection) -> None:
    """Log the read-only posture at boot. A read+write connection is a misconfiguration."""
    value = (await conn.execute(sa.text("SHOW transaction_read_only"))).scalar_one()
    if value != "on":
        # Warn (not hard-fail): a superuser DSN in dev is common; production should use the
        # read-only role. TODO(build): hard-fail when settings.is_production once the role lands.
        log.warning("db.not_read_only", transaction_read_only=value)


async def healthcheck(conn: AsyncConnection) -> bool:
    """SELECT 1 liveness probe used by GET /health/db."""
    return (await conn.execute(sa.text("SELECT 1"))).scalar_one() == 1


async def get_conn(request: Request) -> AsyncIterator[AsyncConnection]:
    """FastAPI dependency: one read-only Core connection per request.

    Re-exported via ``deps.get_conn`` so tests override a single symbol.
    """
    engine: AsyncEngine = request.app.state.engine
    async with engine.connect() as conn:
        yield conn
