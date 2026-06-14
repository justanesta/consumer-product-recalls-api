"""Integration fixtures: a Postgres seeded with the cassette + an in-process httpx client.

Gated on ``TEST_DATABASE_URL`` (a ``postgresql+asyncpg://...`` URL) — integration tests SKIP when
it is unset, so the unit suite still runs anywhere. The host is pluggable (local testcontainers, CI
``services: postgres``, or a Neon branch) — only the URL changes. The seed runs via a raw asyncpg
connection (one multi-statement call); the app's ``get_conn`` is overridden to the seeded engine
and the lifespan/real pool is never opened.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

_SEED = Path(__file__).resolve().parents[1] / "fixtures" / "seed_gold.sql"


def _require_db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL unset — integration tests need Postgres (testcontainers / CI)."
        )
    return url


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    url = _require_db_url()  # postgresql+asyncpg://...

    # Seed via raw asyncpg (handles the multi-statement script); strip the SQLAlchemy driver suffix.
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.execute(_SEED.read_text())
    finally:
        await conn.close()

    # Pin UTC (as prod db.py does) so date-vs-timestamptz filters resolve on UTC day boundaries
    # regardless of the test host's timezone.
    engine = create_async_engine(url, connect_args={"server_settings": {"timezone": "UTC"}})

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
