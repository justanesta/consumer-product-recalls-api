"""Async engine, lifespan pool, read-only assertion, and the per-request connection dependency.

The API is a long-lived server, so it uses a small bounded async pool over asyncpg (the pipeline
uses sync NullPool for batch jobs). A cold/asleep Neon must surface as a fast timeout the request
layer maps to 503 — never a hung request, and never a boot crash.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import FastAPI, Request
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from recalls_api.settings import Settings

log = structlog.get_logger(__name__)

# libpq query params that asyncpg rejects as connect kwargs (they crash boot if forwarded verbatim).
_LIBPQ_TLS_PARAMS = ("sslmode", "channel_binding", "ssl")


def normalize_dsn(raw: str) -> tuple[URL, dict[str, Any]]:
    """Normalize a Postgres DSN for the asyncpg driver.

    A Neon-console URL carries libpq TLS params (``sslmode``/``channel_binding``) that asyncpg
    rejects as connect kwargs, crashing boot. Force the ``+asyncpg`` driver, strip those params,
    and put TLS in an ``ssl`` connect-arg (Neon requires TLS; only ``...=disable`` turns it off).
    """
    url = make_url(raw)
    if "+" not in url.drivername:  # postgresql / postgres -> postgresql+asyncpg
        url = url.set(drivername="postgresql+asyncpg")
    query = dict(url.query)
    tls_values = [str(query.pop(p)) for p in _LIBPQ_TLS_PARAMS if p in query]
    url = url.set(query=query)
    disabled = any(v.lower() == "disable" for v in tls_values)
    return url, {} if disabled else {"ssl": True}


def make_engine(settings: Settings) -> AsyncEngine:
    """Build the read-only async engine for Neon (does not connect until first used)."""
    url, ssl_args = normalize_dsn(settings.neon_database_url_ro.get_secret_value())
    return create_async_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle_seconds,
        connect_args={
            **ssl_args,  # ssl=True unless the DSN explicitly disabled TLS
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
    """Create the engine and store it; the boot connectivity + read-only check is best-effort.

    - A cold/asleep/unreachable Neon at boot must NOT crash the app: serving (and DB-free /health
      liveness probe) must come up regardless. ``pool_pre_ping`` validates connections lazily, and
      per-request paths map a cold DB to 503. A boot crash here would crash-loop the machine.
    - But a REACHABLE connection that is NOT read-only in production is a hard misconfiguration (a
      writable role on a public, no-auth API) and fails loud.
    """
    engine = make_engine(settings)
    app.state.engine = engine
    try:
        async with engine.connect() as conn:
            read_only = (await conn.execute(sa.text("SHOW transaction_read_only"))).scalar_one()
    except Exception as exc:  # cold/asleep/unreachable Neon at boot -> tolerate, validate lazily
        log.warning("db.boot_check_skipped", error=str(exc))
        return
    if read_only != "on":
        if settings.is_production:
            raise RuntimeError("DB connection is NOT read-only in production — refusing to start.")
        log.warning(
            "db.not_read_only", transaction_read_only=read_only
        )  # superuser DSN common in dev
    log.info("db.pool_open", pool_size=settings.db_pool_size)


async def close_pool(app: FastAPI) -> None:
    engine: AsyncEngine | None = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()
        log.info("db.pool_closed")


async def healthcheck(conn: AsyncConnection) -> bool:
    """SELECT 1 readiness probe used by GET /health/db."""
    return (await conn.execute(sa.text("SELECT 1"))).scalar_one() == 1


async def get_conn(request: Request) -> AsyncIterator[AsyncConnection]:
    """FastAPI dependency: one read-only Core connection per request (overridable in deps)."""
    engine: AsyncEngine = request.app.state.engine
    async with engine.connect() as conn:
        yield conn
