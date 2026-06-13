"""Application settings — pydantic-settings, fail-loud at first access.

Mirrors the pipeline's ``src/config/settings.py`` posture (BaseSettings + SecretStr, no module-level
instance) but with the API's own read-only DSN var. Importing this module never requires a secret;
``get_settings()`` constructs lazily so the *first* access (the FastAPI lifespan) raises
``ValidationError`` at boot if the DSN is missing — not on the first request.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database (read-only) -------------------------------------------------
    # asyncpg DSN, e.g. postgresql+asyncpg://recalls_readonly:<pw>@<host>/<db>?ssl=require
    # A DISTINCT var from the pipeline's read+write NEON_DATABASE_URL so the API can never be
    # handed write creds by accident. See 02 MUST-re-verify #1 / the gold-readiness plan R1.
    neon_database_url_ro: SecretStr

    # --- Pool (cold-start tuned for Neon serverless; see db.py) ----------------
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_recycle_seconds: int = Field(default=300, ge=30)  # < Neon idle reap (~300s)
    db_connect_timeout_seconds: float = Field(default=5.0, gt=0)  # cold Neon -> 503, never hang
    db_command_timeout_seconds: float = Field(default=10.0, gt=0)  # per-statement deadline

    # --- Runtime ---------------------------------------------------------------
    environment: str = "development"  # development | staging | production
    log_level: str = "INFO"

    # --- HTTP cache (keyed off the nightly ~03:00 UTC transform rebuild; see 06) ---
    cache_max_age_seconds: int = Field(default=300, ge=0)

    # --- Rate limit (slowapi; chosen here, not ADR-ratified; tune to free-tier DB) ---
    rate_limit_enabled: bool = True
    rate_limit_default: str = "60/minute"

    # --- Pagination guards -----------------------------------------------------
    page_limit_default: int = Field(default=25, ge=1, le=100)
    page_limit_max: int = Field(default=100, ge=1, le=100)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Construct once; raises ValidationError at first call if the DSN is missing.

    Called from the FastAPI lifespan so a misconfigured deploy fails *at boot*, not mid-request.
    """
    return Settings()  # type: ignore[call-arg]  # fields are env-populated
