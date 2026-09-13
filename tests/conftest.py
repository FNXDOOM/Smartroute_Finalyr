"""Shared pytest setup: ensure the test database schema exists.

CI runs ``pytest tests/ -v`` with ``DATABASE_URL=sqlite:///./ci_test.db`` on a
fresh runner, so the SQLite file has no tables unless something creates them.
``tests/test_pipeline_and_batch.py`` uses ``database.SessionLocal`` directly
and queries ``users`` — without a prior ``create_all`` it fails with
``sqlite3.OperationalError: no such table: users``.

This session-scoped autouse fixture imports all ORM models (registering them
on ``Base.metadata``) and calls ``create_db_tables()`` once before any test
runs. It is idempotent (``checkfirst=True``) so it is safe for local runs
against an existing dev database too.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import models  # noqa: F401,E402 — register ORM tables on Base.metadata
from database import create_db_tables  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_schema():
    create_db_tables()
    yield
