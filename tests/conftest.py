"""Session setup: build the scratch schema, refusing a hosted DATABASE_URL (create_db_tables() issues real DDL)
and outbound sockets (osmnx is in CI but not locally, so road-graph fetches make CI crawl)."""

import os
import socket
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import models  # noqa: F401,E402 — register ORM tables on Base.metadata
from config import DATABASE_URL  # noqa: E402
from database import create_db_tables  # noqa: E402

LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "::ffff:127.0.0.1"}


@pytest.fixture
def mock_road_matrix(monkeypatch):
    """Explicit synthetic routing for solver tests, never live-road evidence."""
    from services.routing import vrp_solver

    monkeypatch.setattr(
        vrp_solver, "build_stadia_distance_matrix",
        lambda points: vrp_solver.build_distance_matrix(points),
    )


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


def is_external_address(address) -> bool:
    """True when a socket target leaves this machine; a bare string is an AF_UNIX path."""
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    return isinstance(host, str) and host not in LOCAL_HOSTS


@pytest.fixture(scope="session", autouse=True)
def _keep_the_suite_hermetic():
    """Refuse outbound sockets so CI behaves like a laptop; opt out with ``TEST_ALLOW_NETWORK=1``."""
    if os.getenv("TEST_ALLOW_NETWORK") == "1":
        yield
        return

    original_connect = socket.socket.connect
    original_connect_ex = getattr(socket.socket, "connect_ex", None)

    def guarded_connect(self, address, *args, **kwargs):
        if is_external_address(address):
            raise AssertionError(
                f"blocked outbound connection to {address!r}: the test suite must "
                "not reach the internet. Mock the client, or set "
                "TEST_ALLOW_NETWORK=1 if the dependency is deliberate."
            )
        return original_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):
        if is_external_address(address):
            raise AssertionError(f"blocked outbound connection to {address!r}")
        return original_connect_ex(self, address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    if original_connect_ex is not None:
        socket.socket.connect_ex = guarded_connect_ex
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        if original_connect_ex is not None:
            socket.socket.connect_ex = original_connect_ex


def prepare_scratch_database(url: str) -> None:
    """Create the scratch folder SQLite will not make, and keep only the newest DBs."""
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
