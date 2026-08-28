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
    """Safely drop database tables ignoring Spatialite DDL hooks on SQLite"""
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
    """Create database tables for the explicitly configured database."""
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

    # create_all() does not add columns to an existing table. Keep this small
    # compatibility migration here until the project has a full Alembic
    # migration history.
    if target_engine.dialect.name == "postgresql":
        with target_engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS clerk_user_id VARCHAR"
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
    elif target_engine.dialect.name == "sqlite":
        columns = {column[1] for column in inspect(target_engine).get_columns("users")}
        if "clerk_user_id" not in columns:
            with target_engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN clerk_user_id VARCHAR"))
            with target_engine.begin() as connection:
                connection.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_clerk_user_id "
                    "ON users (clerk_user_id) WHERE clerk_user_id IS NOT NULL"
                ))
        vehicle_columns = {column[1] for column in inspect(target_engine).get_columns("vehicles")}
        if "driver_user_id" not in vehicle_columns:
            with target_engine.begin() as connection:
                connection.execute(text("ALTER TABLE vehicles ADD COLUMN driver_user_id INTEGER"))
            with target_engine.begin() as connection:
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_vehicles_driver_user_id "
                    "ON vehicles (driver_user_id)"
                ))
        for table in ("ride_requests", "cluster_runs", "route_plans", "virtual_stops", "vehicles"):
            columns = {column[1] for column in inspect(target_engine).get_columns(table)}
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



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

