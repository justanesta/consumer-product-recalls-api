"""App factory + lifespan.

Middleware is added inner-first; the LAST add is the OUTERMOST. CORSMiddleware is added last so it
wraps everything — its Access-Control-* headers land on every handled response — and
RequestIdMiddleware, just inside it, binds the request_id before any handler runs. Error handlers
emit the uniform envelope; slowapi rate-limiting and Cache-Control headers are wired here.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from email.utils import formatdate

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from recalls_api import __version__, db
from recalls_api.errors import rate_limited_response, register_error_handlers
from recalls_api.logging import RequestIdMiddleware, configure_logging
from recalls_api.middleware import CacheControlMiddleware
from recalls_api.routers import firms, health, products, recalls, stats
from recalls_api.settings import get_settings

_DESCRIPTION = (
    "Open, read-only API for US consumer product recalls from five agencies (CPSC, FDA, USDA, "
    "NHTSA, USCG). No key, GET-only, cursor-paginated. A few things worth knowing up front: a "
    "recall's `is_active` flag is `null` (not false) for CPSC and NHTSA, which don't track an "
    "open/closed status; `classification` uses each agency's own severity scale and can't be "
    "compared across agencies; UPC search matches a whole recall, not an individual product; and "
    "search is exact, so a typo finds nothing."
    "\n\n**Common lookups:** by product name → `GET /products/search?q=`; by **UPC barcode** → "
    "`GET /products/search?upc=`; vehicle or boat by identifier → `GET /products/search?model=` / "
    "`?hin=`; a single recall → `GET /recalls/{source}/{recall_id}`."
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # fail-loud: a missing DSN raises ValidationError at boot
    await db.open_pool(app, settings)  # verifies connectivity + read-only posture
    try:
        yield
    finally:
        await db.close_pool(app)


async def _on_rate_limited(request: Request, exc: RateLimitExceeded) -> Response:
    return rate_limited_response()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Consumer Product Recalls API",
        version=__version__,
        description=_DESCRIPTION,
        lifespan=lifespan,
    )

    # Rate limit (slowapi, per-IP; an API-repo choice, not ADR-ratified). default_limits applies to
    # every route via the middleware; health routes are exempted below so probes never consume the
    # budget. NOTE: the default MemoryStorage is per-process — with scale-to-zero it resets on cold
    # start and each machine counts separately, so the limit is effectively per-machine, not a true
    # global (fine at personal scale; use a shared store like Redis for a global limit).
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[settings.rate_limit_default],
        enabled=settings.rate_limit_enabled,
    )
    app.state.limiter = limiter
    limiter.exempt(health.health)
    limiter.exempt(health.health_db)

    # Coarse cache validators (per-startup; a per-rebuild ETag awaits gold_meta.rebuilt_at, R6).
    startup_id = os.getenv("GIT_SHA") or uuid.uuid4().hex[:12]

    # Inner-first. CORS is added LAST below (outermost); RequestIdMiddleware sits just inside it and
    # binds request_id before any handler runs.
    app.add_middleware(
        CacheControlMiddleware,
        max_age=settings.cache_max_age_seconds,
        etag=f'W/"{__version__}-{startup_id}"',
        last_modified=formatdate(usegmt=True),
    )
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # Open CORS, added LAST (outermost): the API is public, read-only, and credential-free, so any
    # browser origin may read responses (only what an unauthenticated curl already returns). `*` is
    # safe because there are no cookies/auth, so the rejected `*`-with-credentials combo never
    # applies. Outermost placement puts the headers on every response, including errors.
    # expose_headers makes the non-safelisted Retry-After / ETag / X-Request-ID readable by JS.
    # See ADR 0014.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
        expose_headers=["Retry-After", "ETag", "X-Request-ID"],
    )

    register_error_handlers(app)
    app.add_exception_handler(RateLimitExceeded, _on_rate_limited)  # type: ignore[arg-type]

    app.include_router(health.router)
    app.include_router(recalls.router)
    app.include_router(products.router)
    app.include_router(firms.router)
    app.include_router(stats.router)
    return app


# Served via the factory so importing this module never builds the app (nor needs the DSN):
#   uvicorn --factory recalls_api.main:create_app --proxy-headers
