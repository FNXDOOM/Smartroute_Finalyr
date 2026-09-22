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

"dev database" means local, though: ``backend/.env`` points at a hosted
Postgres, and ``create_db_tables()`` issues real DDL there (``ALTER TABLE``
backfills, ``CREATE INDEX``). Running the suite without overriding
``DATABASE_URL`` would migrate production, so the fixture aborts instead. Set
``TEST_DB_ALLOW_REMOTE=1`` to opt back in deliberately.
"""

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import models  # noqa: F401,E402 — register ORM tables on Base.metadata
from config import DATABASE_URL  # noqa: E402
from database import create_db_tables  # noqa: E402

LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "::ffff:127.0.0.1"}


def hits_hosted_database(url: str) -> bool:
    """True when running DDL against ``url`` would touch a shared database."""
    if os.getenv("TEST_DB_ALLOW_REMOTE") == "1":
        return False
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite"):
        return False
    return (parsed.host or "") not in LOCAL_HOSTS


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_schema():
    if hits_hosted_database(DATABASE_URL):
        pytest.exit(
            "Refusing to run: DATABASE_URL points at a hosted database "
            f"({make_url(DATABASE_URL).host}). create_db_tables() issues DDL, "
            "so the suite would migrate it. Run with "
            "DATABASE_URL=sqlite:///./ci_test.db (what CI uses), point it at a "
            "local Postgres, or set TEST_DB_ALLOW_REMOTE=1 to proceed anyway."
        )
    create_db_tables()
    yield
