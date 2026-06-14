"""Unit tests for the DB layer: DSN normalization + the cold-tolerant / prod-strict boot."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from recalls_api import db


def test_normalize_dsn_strips_libpq_tls_params() -> None:
    url, ssl = db.normalize_dsn("postgresql://u:p@h/d?sslmode=require&channel_binding=require")
    assert url.drivername == "postgresql+asyncpg"
    assert "sslmode" not in url.query and "channel_binding" not in url.query
    assert ssl == {"ssl": True}


def test_normalize_dsn_preserves_asyncpg_and_pulls_ssl() -> None:
    url, ssl = db.normalize_dsn("postgresql+asyncpg://u:p@h/d?ssl=require")
    assert url.drivername == "postgresql+asyncpg"
    assert "ssl" not in url.query  # pulled into connect_args
    assert ssl == {"ssl": True}


def test_normalize_dsn_respects_disabled_tls() -> None:
    _url, ssl = db.normalize_dsn("postgresql://u:p@h/d?sslmode=disable")
    assert ssl == {}


def _async_cm(*, enter_side_effect: Any = None, conn: Any = None) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=enter_side_effect, return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _fake_engine(connect_cm: MagicMock) -> MagicMock:
    engine = MagicMock()
    engine.connect = MagicMock(return_value=connect_cm)
    return engine


def _read_only_conn(value: str) -> MagicMock:
    conn = MagicMock()
    result = MagicMock()
    result.scalar_one.return_value = value
    conn.execute = AsyncMock(return_value=result)
    return conn


async def test_open_pool_tolerates_cold_db(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fake_engine(_async_cm(enter_side_effect=TimeoutError("cold neon")))
    monkeypatch.setattr(db, "make_engine", lambda _s: engine)
    app = MagicMock(state=MagicMock())
    await db.open_pool(app, MagicMock(is_production=True, db_pool_size=5))  # must NOT raise
    assert app.state.engine is engine  # engine is stored so serving comes up regardless


async def test_open_pool_hardfails_on_writable_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fake_engine(_async_cm(conn=_read_only_conn("off")))
    monkeypatch.setattr(db, "make_engine", lambda _s: engine)
    with pytest.raises(RuntimeError):
        await db.open_pool(
            MagicMock(state=MagicMock()), MagicMock(is_production=True, db_pool_size=5)
        )


async def test_open_pool_warns_but_starts_writable_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fake_engine(_async_cm(conn=_read_only_conn("off")))
    monkeypatch.setattr(db, "make_engine", lambda _s: engine)
    app = MagicMock(state=MagicMock())
    await db.open_pool(app, MagicMock(is_production=False, db_pool_size=5))  # warns, no raise
    assert app.state.engine is engine


def test_create_app_maps_db_connectivity_errors_to_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEON_DATABASE_URL_RO", "postgresql+asyncpg://u:p@h/d")
    from recalls_api.settings import get_settings

    get_settings.cache_clear()
    from recalls_api.main import create_app

    handlers = create_app().exception_handlers
    assert OSError in handlers  # covers bare TimeoutError/ConnectionError from a cold Neon (MRO)
    assert OperationalError in handlers
