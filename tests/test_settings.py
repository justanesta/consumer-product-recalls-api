"""Settings: env-driven, sensible defaults, and fail-loud when the DSN is missing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from recalls_api.settings import Settings

_DSN = "postgresql+asyncpg://ro:pw@host/db"


def test_settings_reads_dsn_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEON_DATABASE_URL_RO", _DSN)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.neon_database_url_ro.get_secret_value() == _DSN
    assert s.db_pool_size == 5
    assert s.db_pool_recycle_seconds == 300
    assert s.page_limit_max == 100
    assert s.rate_limit_default == "60/minute"
    assert s.is_production is False


def test_settings_is_production_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEON_DATABASE_URL_RO", _DSN)
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert Settings(_env_file=None).is_production is True  # type: ignore[call-arg]


def test_settings_fail_loud_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEON_DATABASE_URL_RO", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
