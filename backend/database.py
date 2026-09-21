from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import String
from sqlalchemy import inspect, text
from geoalchemy2 import Geometry
from config import DATABASE_URL

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Configure it in backend/.env "
        "before starting the backend."
    )

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

try:
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
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
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS clerk_user_id VARCHAR"
            ))
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS driver_status VARCHAR NOT NULL DEFAULT 'active'"
            ))
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS driver_last_seen_at TIMESTAMPTZ"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_clerk_user_id "
                "ON users (clerk_user_id) WHERE clerk_user_id IS NOT NULL"
            ))
            connection.execute(text(
                "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS driver_user_id INTEGER"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_vehicles_driver_user_id "
                "ON vehicles (driver_user_id)"
            ))
            for table in ("ride_requests", "cluster_runs", "route_plans", "virtual_stops", "vehicles"):
                columns = {column["name"] for column in inspect(target_engine).get_columns(table)}
                if "ride_mode" not in columns and "mode" in columns:
                    connection.execute(text(f"ALTER TABLE {table} RENAME COLUMN mode TO ride_mode"))
                connection.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS ride_mode VARCHAR NOT NULL DEFAULT 'live'"
                ))
                connection.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS demo_run_id VARCHAR"
                ))
                connection.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table}_ride_mode ON {table} (ride_mode)"
                ))
                connection.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table}_demo_run_id ON {table} (demo_run_id)"
                ))
            # Shared/carpool flag (added after the ride_mode migration).
            connection.execute(text(
                "ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS is_shared BOOLEAN NOT NULL DEFAULT true"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ride_requests_is_shared ON ride_requests (is_shared)"
            ))
            # Per-rider carpool stage (added after the shared-ride flag).
            connection.execute(text(
                "ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS carpool_status VARCHAR"
            ))
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


# Fast, idempotent additive migrations for Postgres. Postgres supports
# ``ADD COLUMN IF NOT EXISTS``, so this avoids create_db_tables()'s pg_catalog
# reflection - which can exceed a remote database's statement timeout and leave
# the app querying columns the table never got (a missing column 500s every ORM
# query). Run at API/worker startup so a skipped ``alembic upgrade head`` can
# never silently break the running app. SQLite is skipped: the test/dev path
# uses create_db_tables(), which reflects safely there.
#
# Hardened for production:
#   * one writer at a time - a transaction advisory lock stops the API replicas
#     and worker running this concurrently (which can deadlock or raise
#     "tuple concurrently updated" / duplicate index names);
#   * tables that do not exist are skipped, so a fresh or half-built database
#     cannot hard-error here;
#   * the legacy ``mode`` -> ``ride_mode`` rename is applied when needed, so old
#     values are not silently dropped.
_RIDE_SCOPED_TABLES = ("ride_requests", "cluster_runs", "route_plans", "virtual_stops", "vehicles")
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
        if _pg_table_exists(connection, "users"):
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS clerk_user_id VARCHAR"
            ))
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS driver_status VARCHAR NOT NULL DEFAULT 'active'"
            ))
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS driver_last_seen_at TIMESTAMPTZ"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_clerk_user_id "
                "ON users (clerk_user_id) WHERE clerk_user_id IS NOT NULL"
            ))
        if _pg_table_exists(connection, "vehicles"):
            connection.execute(text(
                "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS driver_user_id INTEGER"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_vehicles_driver_user_id ON vehicles (driver_user_id)"
            ))
        for table in _RIDE_SCOPED_TABLES:
            if not _pg_table_exists(connection, table):
                continue
            if (
                not _pg_column_exists(connection, table, "ride_mode")
                and _pg_column_exists(connection, table, "mode")
            ):
                connection.execute(text(f"ALTER TABLE {table} RENAME COLUMN mode TO ride_mode"))
            connection.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS ride_mode VARCHAR NOT NULL DEFAULT 'live'"
            ))
            connection.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS demo_run_id VARCHAR"
            ))
            connection.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_{table}_ride_mode ON {table} (ride_mode)"
            ))
            connection.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_{table}_demo_run_id ON {table} (demo_run_id)"
            ))
        if _pg_table_exists(connection, "ride_requests"):
            connection.execute(text(
                "ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS is_shared BOOLEAN NOT NULL DEFAULT true"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ride_requests_is_shared ON ride_requests (is_shared)"
            ))
            connection.execute(text(
                "ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS carpool_status VARCHAR"
            ))


def get_db():
    """Yield a database session and close it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
