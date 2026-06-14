"""Export / verify the committed OpenAPI snapshot — the cross-repo contract artifact.

  python -m recalls_api.export_openapi           # (re)write openapi.json at the repo root
  python -m recalls_api.export_openapi --check   # exit 1 if the committed openapi.json is stale

Generating the spec introspects routes + models — it never hits the DB — so a dummy DSN is set if
one is absent (the app is built via the factory; the lifespan/pool is never opened here).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_OPENAPI = Path(__file__).resolve().parents[2] / "openapi.json"  # repo root


def generate() -> dict[str, Any]:
    os.environ.setdefault(
        "NEON_DATABASE_URL_RO", "postgresql+asyncpg://export:export@localhost/export"
    )
    from recalls_api.main import create_app

    return create_app().openapi()


def render(spec: dict[str, Any]) -> str:
    # Deterministic (insertion order stable for the same code) + trailing newline for clean diffs.
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    rendered = render(generate())
    if "--check" in args:
        current = _OPENAPI.read_text(encoding="utf-8") if _OPENAPI.exists() else ""
        if current != rendered:
            sys.stderr.write(
                "openapi.json is stale — run `python -m recalls_api.export_openapi` and commit.\n"
            )
            return 1
        print("openapi.json is up to date.")
        return 0
    _OPENAPI.write_text(rendered, encoding="utf-8")
    print(f"wrote {_OPENAPI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
