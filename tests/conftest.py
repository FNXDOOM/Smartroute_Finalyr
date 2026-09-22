"""Shared pytest setup: where the test database lives, and what it must never be.

CI runs ``pytest tests/ -v`` with
``DATABASE_URL=sqlite:///./.testdb/ci_test.db`` on a fresh runner, so the SQLite
file has no tables unless something creates them.
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

SCRATCH_DB_DIR = ".testdb"
KEEP_SCRATCH_DBS = 3
TEST_DATABASE_URL = f"sqlite:///./{SCRATCH_DB_DIR}/ci_test.db"


def hits_hosted_database(url: str) -> bool:
    """True when running DDL against ``url`` would touch a shared database."""
    if os.getenv("TEST_DB_ALLOW_REMOTE") == "1":
        return False
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite"):
        return False
    return (parsed.host or "") not in LOCAL_HOSTS


def prepare_scratch_database(url: str) -> None:
    """Create the folder a scratch SQLite URL points into, and retire older runs.

    SQLite will not create a missing parent directory, and each ad-hoc
    ``DATABASE_URL`` name used to leave another file in the repo root forever.
    Only files inside ``SCRATCH_DB_DIR`` are candidates, so a database that
    lives elsewhere is never deleted no matter its name.
    """
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite") or not parsed.database:
        return
    path = Path(parsed.database)
    if path.parent.name != SCRATCH_DB_DIR:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    by_age = sorted(path.parent.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in by_age[KEEP_SCRATCH_DBS:]:
        if stale.resolve() != path.resolve():
            stale.unlink(missing_ok=True)


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_schema():
    if hits_hosted_database(DATABASE_URL):
        pytest.exit(
            "Refusing to run: DATABASE_URL points at a hosted database "
            f"({make_url(DATABASE_URL).host}). create_db_tables() issues DDL, "
            "so the suite would migrate it. Run with "
            f"DATABASE_URL={TEST_DATABASE_URL} (what CI uses), point it at a "
            "local Postgres, or set TEST_DB_ALLOW_REMOTE=1 to proceed anyway."
        )
    prepare_scratch_database(DATABASE_URL)
    create_db_tables()
    yield
