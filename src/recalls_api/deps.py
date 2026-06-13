"""Shared FastAPI dependencies.

``get_conn`` is re-exported here as the single overridable symbol — routers depend on
``deps.get_conn`` so tests swap the DB with one override. The pagination/filter dependencies are
added in C3/C4 (they need ``pagination`` + ``models.common``, which land then).
"""

from __future__ import annotations

from recalls_api.db import get_conn as get_conn

__all__ = ["get_conn"]
