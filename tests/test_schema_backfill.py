"""The additive Postgres backfill: statement content and ordering.

The suite runs on SQLite, so the Postgres path has no database to exercise in
CI. Both runtime paths (create_db_tables and run_startup_migrations) execute the
same list, and that list is produced by a pure function — which is what these
tests pin, so a dropped column or a rename-after-add regression is caught.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

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
