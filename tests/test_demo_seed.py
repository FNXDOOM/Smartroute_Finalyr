"""Demo seed timestamps; request_time is a tz-aware column compared against tz-aware analytics bounds."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from demo_seed.pipeline import _seed_ride_requests
from models.user import User

PASSENGER_EMAIL = "demo_seed_rider@example.com"
CITY_CENTER = (12.9716, 77.5946)


def _user(db):
    user = db.query(User).filter(User.email == PASSENGER_EMAIL).first()
    if user:
        return user
    user = User(
        clerk_user_id=f"demo_seed_test_{PASSENGER_EMAIL}",
        email=PASSENGER_EMAIL,
        name="Demo Seed Tester",
        password_hash="test_hash",
        role="passenger",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_seeded_request_times_are_timezone_aware():
    """Naive request_time values compare incorrectly against the tz-aware analytics window bound, and on PostgreSQL a naive insert into timestamptz is read back as local time. Times are read before commit because SQLite has no timezone storage and would hand back naive values on reload."""
    db = SessionLocal()
    try:
        passenger = _user(db)
        rides = _seed_ride_requests(
            db,
            passengers=[passenger],
            rng=random.Random(7),
            city_center=CITY_CENTER,
            count=3,
            start_hours_ago=2,
        )
        request_times = [ride.request_time for ride in rides]
        db.rollback()
        assert request_times
        for request_time in request_times:
            assert request_time is not None
            assert request_time.tzinfo is not None, (
                f"seeded request_time {request_time!r} is naive; the column is "
                "DateTime(timezone=True) and get_analytics_daily filters it against a "
                "tz-aware bound"
            )
    finally:
        db.close()
