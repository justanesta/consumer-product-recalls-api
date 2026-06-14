"""Integration fixtures: a Postgres seeded with the cassette + an in-process httpx client.

The DB host is resolved once per session by ``database_url``:
  1. ``TEST_DATABASE_URL`` if set (CI ``services: postgres``, or a Neon branch), else
  2. an ephemeral testcontainers ``postgres:16`` (needs Docker), else
  3. SKIP (so the unit suite still runs anywhere).
The seed runs via a raw asyncpg connection (one multi-statement call); the app's ``get_conn`` is
then overridden to the seeded engine, and the lifespan/real pool is never opened.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

_SEED = Path(__file__).resolve().parents[1] / "fixtures" / "seed_gold.sql"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        yield explicit
        return
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("integration tests need TEST_DATABASE_URL or testcontainers + Docker")
    try:
        with PostgresContainer("postgres:16", driver="asyncpg") as pg:
            yield pg.get_connection_url()
    except Exception as exc:  # Docker not running / image pull failed
        pytest.skip(f"could not start a Postgres testcontainer (Docker unavailable?): {exc}")


@pytest_asyncio.fixture
async def client(database_url: str) -> AsyncIterator[AsyncClient]:
    # Seed via raw asyncpg (handles the multi-statement script); strip the SQLAlchemy driver suffix.
    conn = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.execute(_SEED.read_text())
    finally:
        await conn.close()

    # Pin UTC (as prod db.py does) so date-vs-timestamptz filters resolve on UTC day boundaries.
    engine = create_async_engine(
        database_url, connect_args={"server_settings": {"timezone": "UTC"}}
    )

    # create_app() reads NEON_DATABASE_URL_RO at boot; set a dummy (get_conn is overridden, so the
    # real pool/lifespan is never used).
    os.environ.setdefault(
        "NEON_DATABASE_URL_RO", "postgresql+asyncpg://unused:unused@localhost/unused"
    )
    from recalls_api import deps
    from recalls_api.main import create_app
    from recalls_api.settings import get_settings

    get_settings.cache_clear()
    app = create_app()

    async def _override_get_conn() -> AsyncIterator[AsyncConnection]:
        async with engine.connect() as c:
            yield c

    app.dependency_overrides[deps.get_conn] = _override_get_conn
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()
