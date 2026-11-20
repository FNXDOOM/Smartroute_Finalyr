"""A routing outage must not poison the whole clustering tick.

Regression for the fail-fast corridor pass: one unroutable rider used to raise
out of run_cluster_job, and job_runs.running rolled back every cluster formed
earlier in the same tick, so co-located riders never clustered while Stadia was
down or rate-limited.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from models.cluster_run import ClusterRun
from models.ride_request import RideRequest
from models.user import User
from models.virtual_stop import VirtualStop
from services import background_jobs
from services import carpool_matching as matching
from utils.ride_scope import LIVE_MODE
from utils.ride_states import RIDE_CLUSTERED, RIDE_PENDING

PICKUP = (12.97190, 77.64124)
DEST_NEAR = (12.9756, 77.6066)
DEST_FAR = (13.0500, 77.7500)
DEST_FAR_B = (13.0520, 77.7520)


def _user(db):
    user = db.query(User).filter(User.email == "cluster_resilience@example.com").first()
    if not user:
        user = User(
            name="Cluster Resilience",
            email="cluster_resilience@example.com",
            password_hash="test_hash",
            role="passenger",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _ride(db, user, dest, pickup=PICKUP):
    ride = RideRequest(
        user_id=user.id,
        pickup_lat=pickup[0],
        pickup_lng=pickup[1],
        dest_lat=dest[0],
        dest_lng=dest[1],
        status=RIDE_PENDING,
        mode=LIVE_MODE,
        is_shared=True,
    )
    db.add(ride)
    return ride


def test_unroutable_rider_does_not_roll_back_good_clusters(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("routing unavailable")

    monkeypatch.setattr(matching, "matrix", unavailable)
    monkeypatch.setattr(matching, "route", unavailable)
    monkeypatch.setattr(background_jobs, "build_road_graph",
                        lambda *a, **k: pytest.fail("Dedicated pickups must not download OSM graphs"))

    db = SessionLocal()
    user = None
    stop_ids = set()
    try:
        user = _user(db)
        good_a = _ride(db, user, DEST_NEAR)
        good_b = _ride(db, user, DEST_NEAR)
        # ~450 m apart: outside the 300 m HDBSCAN epsilon, so only the road-based
        # corridor pass can pool them — and that pass is what fails here.
        far_pickup = (PICKUP[0] + 0.004, PICKUP[1])
        far_pickup_b = (PICKUP[0] + 0.008, PICKUP[1])
        unroutable = _ride(db, user, DEST_FAR, far_pickup)
        unroutable_b = _ride(db, user, DEST_FAR_B, far_pickup_b)
        db.commit()
        ids = [good_a.id, good_b.id, unroutable.id, unroutable_b.id]

        result = background_jobs.run_cluster_job(
            db, triggered_by_user_id=user.id, is_scheduled=False, mode=LIVE_MODE
        )

        assert result["clusters_formed"] >= 1
        assert result["routing_failures"] > 0
        assert result["matrix_attempts"] == 1
        from models.job_run import JobRun
        assert db.get(JobRun, result["job_run_id"]).status == "partial"
        db.expire_all()
        rides = db.query(RideRequest).filter(RideRequest.id.in_(ids)).all()
        statuses = {ride.id: ride.status for ride in rides}
        stop_ids = {ride.virtual_stop_id for ride in rides if ride.virtual_stop_id}
        assert statuses[good_a.id] == RIDE_CLUSTERED
        assert statuses[good_b.id] == RIDE_CLUSTERED
        assert statuses[unroutable.id] == RIDE_PENDING
        assert statuses[unroutable_b.id] == RIDE_PENDING
    finally:
        db.rollback()
        if user is not None:
            db.query(RideRequest).filter(RideRequest.user_id == user.id).delete(
                synchronize_session=False
            )
            db.query(ClusterRun).filter(ClusterRun.created_by_user_id == user.id).delete(
                synchronize_session=False
            )
            db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        if stop_ids:
            db.query(VirtualStop).filter(VirtualStop.id.in_(stop_ids)).delete(
                synchronize_session=False
            )
        db.commit()
        db.close()
