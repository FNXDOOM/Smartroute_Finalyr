from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import TypeDecorator, String
from geoalchemy2 import Geometry
from config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

try:
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
except Exception:
    # Fallback to local SQLite if PostgreSQL connection fails during local standalone testing
    fallback_url = "sqlite:///./smartrouteai.db"
    engine = create_engine(fallback_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class PortableGeometry(TypeDecorator):
    """Geometry column type that uses PostGIS Geometry on PostgreSQL and degrades gracefully to String on SQLite"""

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Geometry("POINT", srid=4326))
        return dialect.type_descriptor(String())




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
    """Safely create database tables for PostgreSQL+PostGIS or SQLite development fallback"""
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



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

