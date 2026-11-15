"""Demo seed timestamps; request_time is a tz-aware column compared against tz-aware analytics bounds."""

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from demo_seed import fixtures
from demo_seed.pipeline import _seed_ride_requests
from models.ride_request import RideRequest
from models.user import User
from routers.rides import _reclaim_stale_demo_runs
from utils.auth_utils import verify_password
from utils.ride_scope import PRESENTATION_DEMO_MODE
from utils.ride_states import RIDE_PENDING

PASSENGER_EMAIL = "demo_seed_rider@example.com"
CITY_CENTER = (12.9716, 77.5946)


def _user(db, email=PASSENGER_EMAIL):
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(
        clerk_user_id=f"demo_seed_test_{email}",
        email=email,
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


def test_production_seed_refuses_default_demo_passwords(monkeypatch):
    """The seeded riders and drivers used to share password123 even in production; only the admin was guarded."""
    monkeypatch.setattr(fixtures, "APP_ENV", "production")
    monkeypatch.setattr(fixtures, "SEED_ADMIN_PASSWORD", "strong-admin-password")
    monkeypatch.setattr(fixtures, "SEED_DEMO_PASSWORD", "")
    db = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="SEED_DEMO_PASSWORD"):
            fixtures.seed_users(db)
    finally:
        db.rollback()
        db.close()


def test_production_seed_uses_the_configured_demo_password(monkeypatch):
    monkeypatch.setattr(fixtures, "APP_ENV", "production")
    monkeypatch.setattr(fixtures, "SEED_ADMIN_PASSWORD", "strong-admin-password")
    monkeypatch.setattr(fixtures, "SEED_DEMO_PASSWORD", "strong-demo-password")
    db = SessionLocal()
    try:
        users = fixtures.seed_users(db)
        rider = next(user for user in users if user.email == "arjun.sharma@demo.com")
        assert verify_password("strong-demo-password", rider.password_hash)
        assert not verify_password("password123", rider.password_hash)
    finally:
        db.rollback()
        db.close()


def test_stale_demo_reclaim_is_scoped_to_the_caller():
    """Sweeping another presenter's stale run lets any authenticated user destroy someone else's demo data."""
    db = SessionLocal()
    suffix = uuid4().hex[:8]
    run_a = f"reclaim-a-{suffix}"
    run_b = f"reclaim-b-{suffix}"
    keep_run_id = f"keep-{suffix}"
    emails = [f"reclaim.a.{suffix}@example.com", f"reclaim.b.{suffix}@example.com"]
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    try:
        user_a = _user(db, emails[0])
        user_b = _user(db, emails[1])
        ride_a = RideRequest(
            user_id=user_a.id,
            pickup_lat=12.9716,
            pickup_lng=77.5946,
            dest_lat=12.9352,
            dest_lng=77.6245,
            status=RIDE_PENDING,
            mode=PRESENTATION_DEMO_MODE,
            demo_run_id=run_a,
            request_time=old,
        )
        ride_b = RideRequest(
            user_id=user_b.id,
            pickup_lat=12.9716,
            pickup_lng=77.5946,
            dest_lat=12.9352,
            dest_lng=77.6245,
            status=RIDE_PENDING,
            mode=PRESENTATION_DEMO_MODE,
            demo_run_id=run_b,
            request_time=old,
        )
        db.add_all([ride_a, ride_b])
        db.commit()
        db.refresh(ride_a)
        db.refresh(ride_b)
        ride_a_id = ride_a.id
        ride_b_id = ride_b.id

        reclaimed = _reclaim_stale_demo_runs(db, keep_run_id, user_b.id)

        assert reclaimed == 1
        assert db.query(RideRequest).filter(RideRequest.id == ride_a_id).first() is not None
        assert db.query(RideRequest).filter(RideRequest.id == ride_b_id).first() is None
    finally:
        db.rollback()
        db.query(RideRequest).filter(
            RideRequest.demo_run_id.in_([run_a, run_b])
        ).delete(synchronize_session=False)
        db.query(User).filter(User.email.in_(emails)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_demo_job_runs_are_scoped_to_the_runs_owner(monkeypatch):
    """Any passenger could dispatch/cluster another presenter's demo run; resetting one already required ownership."""
    from fastapi import HTTPException

    from routers import jobs as jobs_router

    db = SessionLocal()
    suffix = uuid4().hex[:8]
    run_id = f"job-guard-{suffix}"
    emails = [f"job.owner.{suffix}@example.com", f"job.stranger.{suffix}@example.com"]
    try:
        owner = _user(db, emails[0])
        stranger = _user(db, emails[1])
        db.add(RideRequest(
            user_id=owner.id, pickup_lat=12.9716, pickup_lng=77.5946,
            dest_lat=12.9352, dest_lng=77.6245, status=RIDE_PENDING,
            mode=PRESENTATION_DEMO_MODE, demo_run_id=run_id,
        ))
        db.commit()

        with pytest.raises(HTTPException) as refused:
            jobs_router.run_cluster_now(mode=PRESENTATION_DEMO_MODE, demo_run_id=run_id,
                                        current_user=stranger, db=db)
        assert refused.value.status_code == 403

        with pytest.raises(HTTPException) as refused:
            jobs_router.run_cluster_now(mode=PRESENTATION_DEMO_MODE, demo_run_id=None,
                                        current_user=stranger, db=db)
        assert refused.value.status_code == 422

        # The owner passes the guard; the job itself is stubbed so the test stays about access.
        monkeypatch.setattr(jobs_router, "run_cluster_job", lambda *a, **k: {"ok": True})
        result = jobs_router.run_cluster_now(mode=PRESENTATION_DEMO_MODE, demo_run_id=run_id,
                                             current_user=owner, db=db)
        assert result == {"ok": True}
    finally:
        db.rollback()
        db.query(RideRequest).filter(RideRequest.demo_run_id == run_id).delete(synchronize_session=False)
        db.query(User).filter(User.email.in_(emails)).delete(synchronize_session=False)
        db.commit()
        db.close()
