"""EXPLAIN ANALYZE the app's hot queries; PostgreSQL only, rolls back.

Run from the repo root with DATABASE_URL set:
    py scripts/explain_hot_queries.py
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text

from database import SessionLocal, engine
from routers.predict import latest_demand_snapshots_query
from routers.tracking import latest_tracking_events_query
from services.background_jobs import pending_rides_query, simulate_rides_query
from services.prediction.demand_model import demand_count_query
from utils.ride_scope import LIVE_MODE


def hot_queries():
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        yield "simulate-job rides", simulate_rides_query(db).statement
        yield "pending clustering", pending_rides_query(db, LIVE_MODE, None).statement
        yield "demand group-by", demand_count_query(db, now - timedelta(days=30)).statement
        yield "heatmap snapshots", latest_demand_snapshots_query(db, 30).statement
        yield "tracking latest events", latest_tracking_events_query(db).statement
    finally:
        db.close()


def main() -> int:
    if engine.dialect.name != "postgresql":
        print("This script needs PostgreSQL; DATABASE_URL is not PostgreSQL.", file=sys.stderr)
        return 2
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            for label, statement in hot_queries():
                compiled = statement.compile(engine, compile_kwargs={"literal_binds": True})
                print(f"\n=== {label} ===\n{compiled}")
                rows = connection.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {compiled}"))
                for (line,) in rows:
                    print(line)
                    match = re.search(r"Seq Scan on ([a-zA-Z0-9_]+)", line)
                    if match:
                        table = match.group(1)
                        count = connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                        if int(count) > 1000:
                            print(f"WARNING: Seq Scan on {table} with {count} rows")
        finally:
            transaction.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
