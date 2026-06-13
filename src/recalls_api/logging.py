"""Structured logging — structlog JSON to stdout + per-request request_id correlation.

Mirrors the pipeline's ``src/config/logging.py`` (shared processor chain, contextvars merge, stdlib
bridge so SQLAlchemy/uvicorn logs share one renderer). The correlation key here is ``request_id``
(bound per request by ``RequestIdMiddleware``), not the pipeline's run-scoped ``run_id``.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar

import structlog
import structlog.contextvars
import structlog.dev
import structlog.processors
import structlog.stdlib
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
log = structlog.get_logger(__name__)


def get_request_id() -> str:
    """The current request's id (``-`` outside a request). Read by the error envelope."""
    return _request_id.get()


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog once at startup. JSON to stdout in prod; ConsoleRenderer on a TTY or
    when ``LOG_FORMAT=console``. A single stdlib handler bridges third-party loggers through the
    same processor chain (no double-encoding).
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    use_console = sys.stderr.isatty() or os.getenv("LOG_FORMAT", "").lower() == "console"

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
    ]
    if use_console:
        final_renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        shared_processors.append(structlog.processors.format_exc_info)
        final_renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                final_renderer,
            ],
            foreign_pre_chain=shared_processors,
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silence chatty third-party loggers regardless of our level.
    for noisy in ("sqlalchemy.engine", "sqlalchemy.pool", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a per-request uuid into contextvars; echo it on the response and the log line."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = _request_id.set(rid)
        structlog.contextvars.bind_contextvars(request_id=rid)
        start = time.perf_counter()
        status_code = 500  # if call_next raises, the handler logs the 500 separately
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=status_code,
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            structlog.contextvars.clear_contextvars()
            _request_id.reset(token)
