"""Unit test for the firm point-read builder."""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from recalls_api.queries import firms as q


def test_firm_stmt_binds_id_and_selects_renamed_sidecars() -> None:
    sql_compiled = q.firm_stmt("abc123").compile(dialect=postgresql.dialect())
    assert sql_compiled.params["firm_id"] == "abc123"
    sql = str(sql_compiled)
    assert "firm_id =" in sql
    # the post-R5 sidecar column names are selected (not the old establishment/manufacturer/fda)
    assert "firm_usda_attributes" in sql
    assert "firm_uscg_attributes" in sql
    assert "firm_fda_attributes" in sql
