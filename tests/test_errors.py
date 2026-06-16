"""Error taxonomy, the uniform envelope, and the opaque catch-all (no SQL/DSN leak)."""

from __future__ import annotations

import json

import pytest
from fastapi.responses import JSONResponse
from starlette.requests import Request

from recalls_api.errors import (
    ApiError,
    BadCursor,
    InvalidParameter,
    ResourceNotFound,
    UpstreamUnavailable,
    _api_error_handler,
    _catch_all_handler,
    _envelope,
    rate_limited_response,
)


def _body(resp: JSONResponse) -> dict:
    return json.loads(bytes(resp.body))


def _fake_request() -> Request:
    return Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
    )


def test_envelope_shape() -> None:
    resp = _envelope("not_found", "missing", 404)
    assert resp.status_code == 404
    assert _body(resp) == {"error": {"type": "not_found", "detail": "missing", "request_id": "-"}}


@pytest.mark.parametrize(
    ("exc", "code", "etype"),
    [
        (ResourceNotFound("x"), 404, "not_found"),
        (InvalidParameter("x"), 422, "invalid_parameter"),
        (BadCursor("x"), 400, "bad_cursor"),
        (UpstreamUnavailable("x"), 503, "upstream_unavailable"),
    ],
)
def test_api_error_taxonomy(exc: ApiError, code: int, etype: str) -> None:
    assert exc.status_code == code
    assert exc.error_type == etype


async def test_api_error_handler_sets_retry_after() -> None:
    resp = await _api_error_handler(_fake_request(), UpstreamUnavailable("cold"))
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "5"
    assert _body(resp)["error"]["type"] == "upstream_unavailable"


async def test_catch_all_is_opaque() -> None:
    resp = await _catch_all_handler(_fake_request(), ValueError("secret SQL select * from x"))
    assert resp.status_code == 500
    body = _body(resp)
    assert body["error"]["detail"] == "an unexpected error occurred"
    assert "secret SQL" not in json.dumps(body)  # never leak the exception text


def test_rate_limited_response_envelope() -> None:
    resp = rate_limited_response()
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"
    assert _body(resp)["error"]["type"] == "rate_limited"
