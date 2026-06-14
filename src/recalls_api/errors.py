"""Error taxonomy + handlers. Every non-2xx body is the same envelope:

    {"error": {"type": <ApiError subtype>, "detail": <human message>, "request_id": <uuid>}}

The catch-all logs the full traceback and returns an OPAQUE body — it never leaks SQL/DSN/exception
text to the client.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlTimeoutError

from recalls_api.logging import get_request_id

log = structlog.get_logger(__name__)


class ApiError(Exception):
    """Base for every API-raised error. Subclasses set ``status_code`` + ``error_type``."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type: str = "internal_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ResourceNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "not_found"


class InvalidParameter(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT  # 422 (Starlette renamed from _ENTITY)
    error_type = "invalid_parameter"


class BadCursor(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "bad_cursor"


class UpstreamUnavailable(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_type = "upstream_unavailable"


class RateLimited(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_type = "rate_limited"


# --- The wire envelope (Pydantic models for OpenAPI) + reusable `responses=` maps ---


class ErrorDetail(BaseModel):
    type: str = Field(examples=["not_found"])  # the ApiError error_type
    detail: Any = Field(examples=["No recall found for CPSC/24-001."])
    request_id: str = Field(examples=["b1d9c6f2-3a1e-4c7e-9f0a-7d2c1e5b8a40"])


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


_ERR: dict[str, Any] = {"model": ErrorEnvelope}
# Keys typed int|str: FastAPI's responses= key type is invariant (int alone is not int|str).
ERR_400: dict[int | str, dict[str, Any]] = {400: {**_ERR, "description": "BadCursor."}}
ERR_404: dict[int | str, dict[str, Any]] = {404: {**_ERR, "description": "ResourceNotFound."}}
ERR_422: dict[int | str, dict[str, Any]] = {422: {**_ERR, "description": "InvalidParameter."}}
ERR_503: dict[int | str, dict[str, Any]] = {503: {**_ERR, "description": "UpstreamUnavailable."}}
ERR_429: dict[int | str, dict[str, Any]] = {429: {**_ERR, "description": "RateLimited."}}

# Per-endpoint maps for the route `responses=` kwarg (so error shapes appear in the OpenAPI spec).
LIST_ERRORS: dict[int | str, dict[str, Any]] = {**ERR_400, **ERR_422, **ERR_503, **ERR_429}
ITEM_ERRORS: dict[int | str, dict[str, Any]] = {**ERR_404, **ERR_422, **ERR_503, **ERR_429}


def _envelope(
    error_type: str,
    detail: Any,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"type": error_type, "detail": detail, "request_id": get_request_id()}},
        headers=headers,
    )


async def _api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    # 503 (cold DB) and 429 (rate limit) are retry-friendly.
    headers = {"Retry-After": "5"} if isinstance(exc, UpstreamUnavailable | RateLimited) else None
    return _envelope(exc.error_type, exc.detail, exc.status_code, headers)


async def _db_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Cold / asleep / timed-out Neon -> 503; never leak the SQLAlchemy/asyncpg message.
    log.warning("db.upstream_unavailable", error=str(exc))
    return _envelope(
        "upstream_unavailable",
        "database temporarily unavailable",
        status.HTTP_503_SERVICE_UNAVAILABLE,
        {"Retry-After": "5"},
    )


async def _catch_all_handler(_: Request, exc: Exception) -> JSONResponse:
    # Full traceback to logs; OPAQUE body to the client. Never leak SQL/DSN/exception text.
    log.error("unhandled_exception", exc_info=exc)
    return _envelope(
        "internal_error",
        "an unexpected error occurred",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's own request-validation 422 (Query/Path/body) -> our uniform envelope.
    details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return _envelope("invalid_parameter", details, status.HTTP_422_UNPROCESSABLE_CONTENT)


def rate_limited_response(retry_after: str = "60") -> JSONResponse:
    """The 429 envelope — wired to slowapi's RateLimitExceeded in main.create_app."""
    return _envelope(
        "rate_limited",
        "rate limit exceeded; please slow down",
        status.HTTP_429_TOO_MANY_REQUESTS,
        {"Retry-After": retry_after},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Wire the handlers. One ApiError handler covers all subtypes (FastAPI matches by MRO)."""
    app.add_exception_handler(ApiError, _api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore
    # Cold/asleep/unreachable Neon: asyncpg raises bare TimeoutError/ConnectionError/OSError that
    # SQLAlchemy does NOT wrap (OSError's MRO covers them); map those + SQLAlchemy's own errors to
    # 503 + Retry-After rather than leaking a 500.
    for db_exc in (OperationalError, DBAPIError, SqlTimeoutError, OSError):
        app.add_exception_handler(db_exc, _db_error_handler)
    app.add_exception_handler(Exception, _catch_all_handler)  # last resort
