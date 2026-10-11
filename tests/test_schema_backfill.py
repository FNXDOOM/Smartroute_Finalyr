"""Pin the Postgres backfill list, which SQLite can never execute: both runtime paths share this one
pure function, so a dropped column or a rename-after-add regression surfaces only here."""

import os
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import conftest  # noqa: E402
from database import postgres_backfill_statements  # noqa: E402

ALL_TABLES = {
    "users",
    "vehicles",
    "ride_requests",
    "cluster_runs",
    "route_plans",
    "virtual_stops",
}
RIDE_SCOPED = ("ride_requests", "cluster_runs", "route_plans", "virtual_stops", "vehicles")


def _statements(*, tables=ALL_TABLES, columns=frozenset(), has_legacy_mode=frozenset()):
    def table_exists(table):
        return table in tables

    def column_exists(table, column):
        if column == "mode":
            return table in has_legacy_mode
        return (table, column) in columns

    return list(
        postgres_backfill_statements(table_exists=table_exists, column_exists=column_exists)
    )


def test_backfill_covers_every_ride_scoped_table():
    statements = _statements()
    for table in RIDE_SCOPED:
        assert (
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS ride_mode VARCHAR NOT NULL DEFAULT 'live'"
            in statements
        )
        assert f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS demo_run_id VARCHAR" in statements
        assert f"CREATE INDEX IF NOT EXISTS ix_{table}_ride_mode ON {table} (ride_mode)" in statements
        assert f"CREATE INDEX IF NOT EXISTS ix_{table}_demo_run_id ON {table} (demo_run_id)" in statements


def test_backfill_adds_carpool_columns_and_identity_columns():
    statements = _statements()
    assert "ALTER TABLE users ADD COLUMN IF NOT EXISTS clerk_user_id VARCHAR" in statements
    assert "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS driver_user_id INTEGER" in statements
    assert (
        "ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS is_shared BOOLEAN NOT NULL DEFAULT true"
        in statements
    )
    assert "ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS carpool_status VARCHAR" in statements


def test_legacy_mode_is_renamed_before_the_column_is_added():
    statements = _statements(has_legacy_mode={"ride_requests"})
    rename = statements.index("ALTER TABLE ride_requests RENAME COLUMN mode TO ride_mode")
    add = statements.index(
        "ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS ride_mode VARCHAR NOT NULL DEFAULT 'live'"
    )
    assert rename < add


def test_no_rename_when_the_column_already_exists():
    statements = _statements(
        columns={("ride_requests", "ride_mode")},
        has_legacy_mode={"ride_requests"},
    )
    assert not any("RENAME COLUMN" in statement for statement in statements)


def test_a_missing_table_is_skipped_entirely():
    statements = _statements(tables={"users"})
    assert "ALTER TABLE users ADD COLUMN IF NOT EXISTS clerk_user_id VARCHAR" in statements
    assert not any("ride_requests" in statement for statement in statements)
    assert not any("vehicles" in statement for statement in statements)


# --- the DDL above is real, so conftest refuses to run create_db_tables() on a hosted database ---

def test_a_hosted_database_would_be_left_alone(monkeypatch):
    monkeypatch.delenv("TEST_DB_ALLOW_REMOTE", raising=False)
    hosted = "postgresql://postgres:secret@aws-0.example.pooler.supabase.com:5432/postgres"
    assert conftest.hits_hosted_database(hosted)


def test_a_local_database_is_fine(monkeypatch):
    monkeypatch.delenv("TEST_DB_ALLOW_REMOTE", raising=False)
    assert not conftest.hits_hosted_database("sqlite:///./.testdb/ci_test.db")
    assert not conftest.hits_hosted_database("postgresql://postgres@localhost:5432/postgres")


def test_the_opt_in_is_explicit(monkeypatch):
    monkeypatch.setenv("TEST_DB_ALLOW_REMOTE", "1")
    hosted = "postgresql://postgres:secret@aws-0.example.pooler.supabase.com:5432/postgres"
    assert not conftest.hits_hosted_database(hosted)


# --- prepare_scratch_database() deletes files, so pin exactly which ones it may touch ---

def _aged_folder(tmp_path, names, active):
    scratch = tmp_path / ".testdb"
    scratch.mkdir()
    for i, name in enumerate(names):
        path = scratch / name
        path.write_bytes(b"x")
        os.utime(path, (1000 + i, 1000 + i))
    return scratch, f"sqlite:///{(scratch / active).as_posix()}"


def test_older_scratch_databases_are_trimmed(tmp_path):
    keep = conftest.KEEP_SCRATCH_DBS
    names = [f"run_{i}.db" for i in range(keep + 3)]
    scratch, url = _aged_folder(tmp_path, names, names[-1])
    conftest.prepare_scratch_database(url)
    assert sorted(p.name for p in scratch.glob("*.db")) == sorted(names[-keep:])


def test_the_database_in_use_is_never_deleted(tmp_path):
    names = [f"run_{i}.db" for i in range(conftest.KEEP_SCRATCH_DBS + 3)]
    scratch, url = _aged_folder(tmp_path, names, names[0])
    conftest.prepare_scratch_database(url)
    assert names[0] in [p.name for p in scratch.glob("*.db")]


def test_a_database_outside_the_scratch_folder_is_untouched(tmp_path):
    names = ["a.db", "b.db", "c.db", "d.db"]
    scratch, url = _aged_folder(tmp_path, names, names[-1])
    outside = tmp_path / "dev_data.db"
    outside.write_bytes(b"x")
    os.utime(outside, (1, 1))
    conftest.prepare_scratch_database(url)
    assert outside.exists()


def test_a_postgres_url_needs_no_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conftest.prepare_scratch_database("postgresql://postgres@localhost:5432/postgres")
    assert not (tmp_path / ".testdb").exists()


# --- written offline, where road snapping fails fast; a networked runner turns this into a real Overpass fetch per grid cell ---

def test_only_a_host_string_can_be_external():
    assert conftest.is_external_address(("api.stadiamaps.com", 443))
    assert conftest.is_external_address(("148.253.91.245", 80))
    assert not conftest.is_external_address(("127.0.0.1", 5432))
    assert not conftest.is_external_address(("::1", 5432))
    assert not conftest.is_external_address("/tmp/.s.PGSQL.5432")  # AF_UNIX path


def test_an_outbound_connection_is_refused(monkeypatch):
    monkeypatch.delenv("TEST_ALLOW_NETWORK", raising=False)
    with pytest.raises(AssertionError, match="blocked outbound"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect(("148.253.91.245", 80))
