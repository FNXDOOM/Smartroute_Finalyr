from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import String
from sqlalchemy import inspect, text
from geoalchemy2 import Geometry
from config import DATABASE_URL, DB_MAX_OVERFLOW, DB_POOL_SIZE, DB_POOL_TIMEOUT

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Configure it in backend/.env "
        "before starting the backend."
    )


def build_engine_kwargs(database_url: str) -> dict:
    """SQLite needs its connect args; PostgreSQL gets a pre-ping pool."""
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_pre_ping": True,
        "pool_size": DB_POOL_SIZE,
        "max_overflow": DB_MAX_OVERFLOW,
        "pool_timeout": DB_POOL_TIMEOUT,
        "pool_recycle": 1800,
    }


try:
    engine = create_engine(DATABASE_URL, **build_engine_kwargs(DATABASE_URL))
except Exception as exc:
    if DATABASE_URL.startswith("sqlite"):
        raise
    raise RuntimeError(
        "Could not initialize the configured PostgreSQL database. "
        "Check DATABASE_URL and install psycopg2-binary. "
        "SQLite fallback is only available when DATABASE_URL explicitly starts with sqlite:///."
    ) from exc

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


PortableGeometry = (
    Geometry("POINT", srid=4326)
    if DATABASE_URL.startswith("postgresql")
    else String()
)


# create_all skips existing tables, so a new model column is missing from an old table until backfilled.
# One ordered list, used by both the create path and startup, so a column is added in exactly one place.
_RIDE_SCOPED_TABLES = ("ride_requests", "cluster_runs", "route_plans", "virtual_stops", "vehicles")


def _ride_scoped_backfill(table: str):
    """The per-table columns shared by every ride-scoped table."""
    return (
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS ride_mode VARCHAR NOT NULL DEFAULT 'live'",
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS demo_run_id VARCHAR",
        f"CREATE INDEX IF NOT EXISTS ix_{table}_ride_mode ON {table} (ride_mode)",
        f"CREATE INDEX IF NOT EXISTS ix_{table}_demo_run_id ON {table} (demo_run_id)",
    )


def postgres_backfill_statements(*, table_exists, column_exists):
    """Ordered backfill DDL; the existence callables skip a half-built DB and put the mode -> ride_mode rename before the add."""
    if table_exists("users"):
        yield "ALTER TABLE users ADD COLUMN IF NOT EXISTS clerk_user_id VARCHAR"
        yield "ALTER TABLE users ADD COLUMN IF NOT EXISTS driver_status VARCHAR NOT NULL DEFAULT 'active'"
        yield "ALTER TABLE users ADD COLUMN IF NOT EXISTS driver_last_seen_at TIMESTAMPTZ"
        yield (
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_clerk_user_id "
            "ON users (clerk_user_id) WHERE clerk_user_id IS NOT NULL"
        )
    if table_exists("vehicles"):
        yield "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS driver_user_id INTEGER"
        yield "CREATE INDEX IF NOT EXISTS ix_vehicles_driver_user_id ON vehicles (driver_user_id)"
    for table in _RIDE_SCOPED_TABLES:
        if not table_exists(table):
            continue
        if not column_exists(table, "ride_mode") and column_exists(table, "mode"):
            yield f"ALTER TABLE {table} RENAME COLUMN mode TO ride_mode"
        yield from _ride_scoped_backfill(table)
    if table_exists("ride_requests"):
        yield "ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS is_shared BOOLEAN NOT NULL DEFAULT true"
        yield "CREATE INDEX IF NOT EXISTS ix_ride_requests_is_shared ON ride_requests (is_shared)"
        yield "ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS carpool_status VARCHAR"
    if table_exists("ride_requests"):
        yield "CREATE INDEX IF NOT EXISTS ix_ride_requests_ride_mode_status ON ride_requests (ride_mode, status)"
        yield "CREATE INDEX IF NOT EXISTS ix_ride_requests_h3_index_status ON ride_requests (h3_index, status)"
        yield "CREATE INDEX IF NOT EXISTS ix_ride_requests_status_request_time ON ride_requests (status, request_time)"
        yield "CREATE INDEX IF NOT EXISTS ix_ride_requests_cluster_id ON ride_requests (cluster_id)"
        yield "CREATE INDEX IF NOT EXISTS ix_ride_requests_virtual_stop_id ON ride_requests (virtual_stop_id)"
    if table_exists("demand_snapshots"):
        yield "CREATE INDEX IF NOT EXISTS ix_demand_snapshots_created_at ON demand_snapshots (created_at)"
        yield (
            "CREATE INDEX IF NOT EXISTS ix_demand_snapshots_h3_index_created_at "
            "ON demand_snapshots (h3_index, created_at)"
        )
    if table_exists("notifications"):
        yield (
            "CREATE INDEX IF NOT EXISTS ix_notifications_user_id_is_read_created_at "
            "ON notifications (user_id, is_read, created_at)"
        )
    if table_exists("tracking_events"):
        yield "CREATE INDEX IF NOT EXISTS ix_tracking_events_created_at ON tracking_events (created_at)"
        yield (
            "CREATE INDEX IF NOT EXISTS ix_tracking_events_vehicle_id_created_at "
            "ON tracking_events (vehicle_id, created_at)"
        )


def drop_db_tables(bind_engine=None):
    """Drop tables; ignore Spatialite errors."""
    target_engine = bind_engine or engine
    try:
        Base.metadata.drop_all(bind=target_engine)
    except Exception:
        for table in reversed(Base.metadata.sorted_tables):
            try:
                table.drop(bind=target_engine, checkfirst=True)
            except Exception:
                pass


def create_db_tables(bind_engine=None):
    """Create tables for configured DB."""
    target_engine = bind_engine or engine
    try:
        Base.metadata.create_all(bind=target_engine)
    except Exception as e:
        if "RecoverGeometryColumn" in str(e) or "spatialite" in str(e).lower() or "sqlite" in target_engine.dialect.name:
            for table in Base.metadata.tables.values():
                try:
                    table.create(bind=target_engine, checkfirst=True)
                except Exception:
                    pass
        else:
            raise e

    # Backfill columns; create_all skips existing tables.
    if target_engine.dialect.name == "postgresql":
        with target_engine.begin() as connection:
            # Engine-bound reflection checks out a second connection, which
            # can wait on the table locks held by this DDL transaction.
            inspector = inspect(connection)

            def _column_exists(table: str, column: str) -> bool:
                return column in {item["name"] for item in inspector.get_columns(table)}

            # create_all just ran, so every table exists and only column checks matter.
            for statement in postgres_backfill_statements(
                table_exists=lambda _table: True,
                column_exists=_column_exists,
            ):
                connection.execute(text(statement))
    elif target_engine.dialect.name == "sqlite":
        from sqlalchemy.exc import NoSuchTableError

        def _sqlite_columns(table_name: str) -> set:
            """Return the column names for an existing SQLite table."""
            try:
                return {
                    column["name"]
                    for column in inspect(target_engine).get_columns(table_name)
                }
            except NoSuchTableError:
                return set()

        existing_tables = set(inspect(target_engine).get_table_names())

        columns = _sqlite_columns("users")
        if "users" in existing_tables:
            if "clerk_user_id" not in columns:
                with target_engine.begin() as connection:
                    connection.execute(text("ALTER TABLE users ADD COLUMN clerk_user_id VARCHAR"))
            if "driver_status" not in columns:
                with target_engine.begin() as connection:
                    connection.execute(text("ALTER TABLE users ADD COLUMN driver_status VARCHAR NOT NULL DEFAULT 'active'"))
            if "driver_last_seen_at" not in _sqlite_columns("users"):
                with target_engine.begin() as connection:
                    connection.execute(text("ALTER TABLE users ADD COLUMN driver_last_seen_at DATETIME"))
            # Indexes independently of whether columns were newly added.
            if "clerk_user_id" in _sqlite_columns("users"):
                with target_engine.begin() as connection:
                    connection.execute(text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_clerk_user_id "
                        "ON users (clerk_user_id) WHERE clerk_user_id IS NOT NULL"
                    ))
        vehicle_columns = _sqlite_columns("vehicles")
        if "vehicles" in existing_tables:
            if "driver_user_id" not in vehicle_columns:
                with target_engine.begin() as connection:
                    connection.execute(text("ALTER TABLE vehicles ADD COLUMN driver_user_id INTEGER"))
            if "driver_user_id" in _sqlite_columns("vehicles"):
                with target_engine.begin() as connection:
                    connection.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_vehicles_driver_user_id "
                        "ON vehicles (driver_user_id)"
                    ))
        for table in ("ride_requests", "cluster_runs", "route_plans", "virtual_stops", "vehicles"):
            if table not in existing_tables:
                continue
            columns = _sqlite_columns(table)
            with target_engine.begin() as connection:
                if "ride_mode" not in columns and "mode" in columns:
                    connection.execute(text(f"ALTER TABLE {table} RENAME COLUMN mode TO ride_mode"))
                    columns.remove("mode")
                    columns.add("ride_mode")
                if "ride_mode" not in columns:
                    connection.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN ride_mode VARCHAR NOT NULL DEFAULT 'live'"
                    ))
                if "demo_run_id" not in columns:
                    connection.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN demo_run_id VARCHAR"
                    ))
                connection.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table}_ride_mode ON {table} (ride_mode)"
                ))
                connection.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table}_demo_run_id ON {table} (demo_run_id)"
                ))


        ride_request_columns = _sqlite_columns("ride_requests")
        if "ride_requests" in existing_tables and "is_shared" not in ride_request_columns:
            with target_engine.begin() as connection:
                connection.execute(text(
                    "ALTER TABLE ride_requests ADD COLUMN is_shared BOOLEAN NOT NULL DEFAULT 1"
                ))
        if "ride_requests" in existing_tables and "is_shared" in _sqlite_columns("ride_requests"):
            with target_engine.begin() as connection:
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_ride_requests_is_shared ON ride_requests (is_shared)"
                ))
        if "ride_requests" in existing_tables and "carpool_status" not in _sqlite_columns("ride_requests"):
            with target_engine.begin() as connection:
                connection.execute(text(
                    "ALTER TABLE ride_requests ADD COLUMN carpool_status VARCHAR"
                ))


# Idempotent additive Postgres migrations, run at API and worker startup so a skipped
# `alembic upgrade head` cannot leave the app querying columns the table never got.
# Deliberately avoids create_db_tables()'s pg_catalog reflection, which can exceed a remote
# statement timeout and half-apply. A transaction advisory lock serialises the API and the
# worker — concurrent runs deadlock or raise "tuple concurrently updated" — missing tables
# are skipped, and the legacy mode -> ride_mode rename is applied so old values survive.
# SQLite is a no-op here: the test and dev path uses create_db_tables().
# Arbitrary constant shared by every process that runs this function.
_STARTUP_MIGRATION_LOCK_KEY = 0x5A1D0001


def _pg_table_exists(connection, table: str) -> bool:
    return connection.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = :table"
    ), {"table": table}).first() is not None


def _pg_column_exists(connection, table: str, column: str) -> bool:
    return connection.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :table AND column_name = :column"
    ), {"table": table, "column": column}).first() is not None


def run_startup_migrations(bind_engine=None) -> None:
    """Apply additive schema backfills at startup (Postgres only)."""
    target_engine = bind_engine or engine
    if target_engine.dialect.name != "postgresql":
        return
    with target_engine.begin() as connection:
        # Serialise across API replicas + worker; released with the transaction.
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _STARTUP_MIGRATION_LOCK_KEY},
        )
        for statement in postgres_backfill_statements(
            table_exists=lambda table: _pg_table_exists(connection, table),
            column_exists=lambda table, column: _pg_column_exists(connection, table, column),
        ):
            connection.execute(text(statement))


def get_db():
    """Yield a database session and close it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
