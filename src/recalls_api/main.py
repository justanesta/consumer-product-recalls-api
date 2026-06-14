"""App factory + lifespan. Registration order: configure_logging -> RequestIdMiddleware (outermost)
-> error handlers -> routers. slowapi rate limiting and Cache-Control/ETag headers are added in C9.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from recalls_api import db
from recalls_api.errors import register_error_handlers
from recalls_api.logging import RequestIdMiddleware, configure_logging
from recalls_api.routers import health, recalls
from recalls_api.settings import get_settings

_DESCRIPTION = (
    "Open, read-only API over the consumer product recalls gold marts (CPSC, FDA, USDA, NHTSA, "
    "USCG). Honest caveats: `is_active` is tri-state (CPSC/NHTSA carry no status -> null); "
    "`classification` is source-native and not comparable across sources; UPC search matches "
    "recall-level UPC arrays, not per-product UPC; there is no fuzzy/typo search."
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # fail-loud: a missing DSN raises ValidationError at boot
    await db.open_pool(app, settings)  # verifies connectivity + read-only posture
    try:
        yield
    finally:
        await db.close_pool(app)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Consumer Product Recalls API",
        version="0.1.0",
        description=_DESCRIPTION,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)  # outermost: binds request_id before handlers run
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(recalls.router)
    # TODO(C6-C7): include products / firms routers as they land.
    # TODO(C9): slowapi limiter + middleware (RateLimitExceeded -> 429 envelope) and
    #           Cache-Control / ETag / Last-Modified keyed off the nightly ~03:00 UTC rebuild.
    return app


# Served via the factory so importing this module never builds the app (nor needs the DSN):
#   uvicorn --factory recalls_api.main:create_app
