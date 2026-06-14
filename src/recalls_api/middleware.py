"""Response-header middleware: HTTP caching for a read-only, nightly-batch dataset.

v1 is a COARSE cache — a fixed ``Cache-Control: public, max-age`` on data GETs (the data changes
once a night), plus a per-startup weak ETag + Last-Modified. A precise per-rebuild validator awaits
an upstream gold rebuild timestamp (gold-readiness R6 / ``gold_meta.rebuilt_at``). Health endpoints
are ``no-store`` so probes never cache.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class CacheControlMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, max_age: int, etag: str, last_modified: str) -> None:
        super().__init__(app)
        self._cache_control = f"public, max-age={max_age}"
        self._etag = etag
        self._last_modified = last_modified

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.method != "GET":
            return response
        if request.url.path.startswith("/health"):
            response.headers["Cache-Control"] = "no-store"
        elif response.status_code == 200:
            response.headers["Cache-Control"] = self._cache_control
            response.headers.setdefault("ETag", self._etag)
            response.headers.setdefault("Last-Modified", self._last_modified)
        return response
