"""Logging config runs and the request-id contextvar defaults outside a request."""

from __future__ import annotations

from recalls_api.logging import configure_logging, get_request_id


def test_get_request_id_default() -> None:
    assert get_request_id() == "-"


def test_configure_logging_runs() -> None:
    configure_logging("INFO")
    configure_logging("DEBUG")  # should be safe to call again
