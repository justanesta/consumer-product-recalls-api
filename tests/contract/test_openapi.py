"""Contract tests: the committed openapi.json is the cross-repo contract; guard it against drift."""

from __future__ import annotations

from recalls_api.export_openapi import _OPENAPI, generate, render


def test_openapi_snapshot_is_current() -> None:
    assert _OPENAPI.exists(), "openapi.json missing — run `python -m recalls_api.export_openapi`"
    assert _OPENAPI.read_text(encoding="utf-8") == render(generate()), (
        "openapi.json drift — regenerate with `python -m recalls_api.export_openapi` and commit it."
    )


def test_openapi_documents_the_v1_surface() -> None:
    spec = generate()
    paths = spec["paths"]
    for p in (
        "/recalls",
        "/recalls/{source}/{recall_id}",
        "/products/search",
        "/firms/{firm_id}",
        "/stats/overview",
        "/stats/recalls-by-period",
        "/stats/by-classification",
        "/stats/firm-leaderboard",
        "/stats/by-geography",
        "/health",
        "/health/db",
    ):
        assert p in paths, f"missing path {p}"
    schemas = spec["components"]["schemas"]
    for s in (
        "FirmProfile",
        "RecallSummary",
        "RecallDetail",
        "ProductSearchHit",
        "ErrorEnvelope",
        "StatsOverview",
        "PeriodCount",
        "ClassificationCount",
        "FirmLeaderRow",
        "GeographyCount",
    ):
        assert s in schemas, f"missing schema {s}"
    # the uniform error envelope is wired into the OpenAPI responses
    assert "400" in paths["/recalls"]["get"]["responses"]
    assert "404" in paths["/recalls/{source}/{recall_id}"]["get"]["responses"]
