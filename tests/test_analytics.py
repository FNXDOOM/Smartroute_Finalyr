"""Analytics rollups and monitoring access; counts are asserted as deltas because the scratch database persists between runs."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from models.ride_request import RideRequest
from models.job_run import JobRun
from models.user import User
from routers.analytics import get_analytics_daily, get_monitoring
from utils.ride_scope import LIVE_MODE, PRESENTATION_DEMO_MODE
from utils.ride_states import RIDE_CANCELLED, RIDE_CLUSTERED, RIDE_COMPLETED, RIDE_PENDING

ADMIN_EMAIL = "analytics_admin@example.com"
PASSENGER_EMAIL = "analytics_rider@example.com"


def _user(db, email, role="passenger"):
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(
        clerk_user_id=f"analytics_test_{email}",
        email=email,
        name="Analytics Tester",
        password_hash="test_hash",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _ride(db, user, ride_status, mode=LIVE_MODE):
    ride = RideRequest(
        user_id=user.id,
        pickup_lat=12.9719,
        pickup_lng=77.6412,
        dest_lat=12.9756,
        dest_lng=77.6066,
        status=ride_status,
        mode=mode,
        request_time=datetime.now(timezone.utc),
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return ride


def _today(response):
    today = datetime.now(timezone.utc).date()
    return next(point for point in response.points if point.day == today)


def test_daily_counts_every_status_bucket():
    session = SessionLocal()
    created = []
    try:
        admin = _user(session, ADMIN_EMAIL, role="admin")
        rider = _user(session, PASSENGER_EMAIL)
        before = _today(get_analytics_daily(days=2, db=session, current_user=admin))

        created = [
            _ride(session, rider, RIDE_CLUSTERED),
            _ride(session, rider, RIDE_CLUSTERED),
            _ride(session, rider, RIDE_COMPLETED),
            _ride(session, rider, RIDE_CANCELLED),
            _ride(session, rider, RIDE_PENDING),
            # A presentation ride must never land in live analytics.
            _ride(session, rider, RIDE_CLUSTERED, mode=PRESENTATION_DEMO_MODE),
        ]

        after = _today(get_analytics_daily(days=2, db=session, current_user=admin))

        assert after.ride_requests - before.ride_requests == 5
        assert after.clustered_rides - before.clustered_rides == 2
        assert after.completed_rides - before.completed_rides == 1
        assert after.cancelled_rides - before.cancelled_rides == 1
    finally:
        for ride in created:
            session.delete(ride)
        session.commit()
        session.close()


def test_daily_window_rejects_an_out_of_range_lookback():
    session = SessionLocal()
    try:
        admin = _user(session, ADMIN_EMAIL, role="admin")
        for bad_days in (0, 91):
            with pytest.raises(HTTPException) as exc:
                get_analytics_daily(days=bad_days, db=session, current_user=admin)
            assert exc.value.status_code == 400
    finally:
        session.close()


def test_daily_is_closed_to_passengers():
    session = SessionLocal()
    try:
        rider = _user(session, PASSENGER_EMAIL)
        with pytest.raises(HTTPException) as exc:
            get_analytics_daily(days=2, db=session, current_user=rider)
        assert exc.value.status_code == 403
    finally:
        session.close()


def test_monitoring_reports_jobs_even_without_prometheus():
    """The monitoring stack is opt-in, so the panel must never depend on it."""
    session = SessionLocal()
    marker = "analytics_probe_job"
    try:
        admin = _user(session, ADMIN_EMAIL, role="admin")
        started = datetime.now(timezone.utc) - timedelta(minutes=3)
        session.add(JobRun(job_name=marker, status="failed", started_at=started,
                           finished_at=started, error_message="boom"))
        session.commit()

        response = get_monitoring(db=session, current_user=admin)
        assert response.prometheus.reachable in (True, False)
        by_name = {job.job_name: job for job in response.jobs.jobs}
        assert by_name[marker].failed == 1
        # Started 3 minutes ago: pins the arithmetic, not merely that it is set.
        assert 150 < by_name[marker].seconds_since_last_run < 300
        assert any(f.job_name == marker and "boom" in f.error_message
                   for f in response.jobs.recent_failures)
    finally:
        session.query(JobRun).filter(JobRun.job_name == marker).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_monitoring_is_closed_to_passengers():
    session = SessionLocal()
    try:
        rider = _user(session, PASSENGER_EMAIL)
        with pytest.raises(HTTPException) as exc:
            get_monitoring(db=session, current_user=rider)
        assert exc.value.status_code == 403
    finally:
        session.close()
