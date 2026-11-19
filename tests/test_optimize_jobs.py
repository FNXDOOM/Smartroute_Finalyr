"""Async route optimization: adaptive budgets, queue, ownership, worker completion/failure."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from models.job_run import JobRun
from models.user import User
from models.vehicle import Vehicle
from routers import route as route_router
from schemas.route import VRPRequest
from services.background_jobs import run_optimize_jobs
from services.routing import vrp_solver
from utils.rate_limit import match_rule

EMAIL = "optimize.owner@example.com"
OTHER_EMAIL = "optimize.other@example.com"
PLATE = "TEST-OPT-001"


def _user(db, email, role="admin"):
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(name="Optimize Tester", email=email, password_hash="x", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _payload(vehicle_id):
    return VRPRequest(
        vehicle_ids=[vehicle_id], virtual_stop_ids=[], depot_lat=12.9784, depot_lng=77.6408
    )


def _cleanup(db, user_ids=(), vehicle_ids=(), job_ids=()):
    if job_ids:
        db.query(JobRun).filter(JobRun.id.in_(job_ids)).delete(synchronize_session=False)
    if vehicle_ids:
        db.query(Vehicle).filter(Vehicle.id.in_(vehicle_ids)).delete(synchronize_session=False)
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()


def test_solver_budget_tiers(monkeypatch):
    monkeypatch.delenv("SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS", raising=False)
    monkeypatch.setattr(vrp_solver, "ROUTE_SOLVER_MIN_SECONDS", 2)
    monkeypatch.setattr(vrp_solver, "ROUTE_SOLVER_MAX_SECONDS", 15)
    assert [vrp_solver.solver_time_limit_for_size(n) for n in (1, 3, 4, 6, 7, 12, 13)] == [
        2, 2, 4, 4, 8, 8, 15,
    ]
    monkeypatch.setenv("SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS", "1")
    assert vrp_solver.solver_time_limit_for_size(1) == 1


def test_async_route_is_covered_by_the_optimize_rate_limit():
    rule = match_rule("/route/optimize/async", "POST")
    assert rule is not None and rule.name == "route_optimize"


def test_async_endpoint_queues_and_enforces_ownership():
    db = SessionLocal()
    owner = _user(db, EMAIL)
    other = _user(db, OTHER_EMAIL, role="passenger")
    vehicle = Vehicle(license_plate=PLATE, capacity=4, mode="live", status="idle",
                      lat=12.9784, lng=77.6408)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    try:
        queued = route_router.optimize_routes_async(
            VRPRequest(vehicle_ids=[vehicle.id], virtual_stop_ids=[], depot_lat=12.9, depot_lng=77.6),
            db,
            owner,
        )
        assert queued["status"] == "queued"
        job = db.query(JobRun).filter(JobRun.id == queued["job_id"]).first()
        assert job.status == "queued"
        assert job.summary["request"]["vehicle_ids"] == [vehicle.id]

        with pytest.raises(Exception) as exc:
            route_router.get_optimize_job(job.id, db, other)
        assert getattr(exc.value, "status_code", None) == 403

        visible = route_router.get_optimize_job(job.id, db, owner)
        assert visible["status"] == "queued"
    finally:
        job_ids = [j.id for j in db.query(JobRun).filter(JobRun.triggered_by_user_id == owner.id).all()]
        _cleanup(db, user_ids=[owner.id, other.id], vehicle_ids=[vehicle.id], job_ids=job_ids)
        db.close()


def test_async_endpoint_rejects_missing_vehicle_before_queue():
    db = SessionLocal()
    owner = _user(db, EMAIL)
    with pytest.raises(Exception) as exc:
        route_router.optimize_routes_async(
            VRPRequest(vehicle_ids=[999999], virtual_stop_ids=[], depot_lat=12.9, depot_lng=77.6),
            db,
            owner,
        )
    assert getattr(exc.value, "status_code", None) == 404
    assert db.query(JobRun).filter(JobRun.triggered_by_user_id == owner.id).count() == 0
    _cleanup(db, user_ids=[owner.id])
    db.close()


def test_worker_completes_a_queued_job():
    db = SessionLocal()
    owner = _user(db, EMAIL)
    vehicle = Vehicle(license_plate=PLATE, capacity=4, mode="live", status="idle",
                      lat=12.9784, lng=77.6408)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    job = JobRun(
        job_name="optimize_route",
        status="queued",
        triggered_by_user_id=owner.id,
        is_scheduled=False,
        summary={"request": _payload(vehicle.id).model_dump(mode="json")},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        result = run_optimize_jobs(db)
        assert result["status"] == "succeeded"
        db.refresh(job)
        assert job.status == "succeeded"
        assert job.summary["result"]["status"] == "no_virtual_stops"
    finally:
        _cleanup(db, user_ids=[owner.id], vehicle_ids=[vehicle.id], job_ids=[job.id])
        db.close()


def test_worker_records_a_failed_solve():
    db = SessionLocal()
    owner = _user(db, EMAIL)
    job = JobRun(
        job_name="optimize_route",
        status="queued",
        triggered_by_user_id=owner.id,
        is_scheduled=False,
        summary={"request": _payload(999999).model_dump(mode="json")},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        result = run_optimize_jobs(db)
        assert result["status"] == "failed"
        db.refresh(job)
        assert job.status == "failed"
        assert job.error_message
    finally:
        _cleanup(db, user_ids=[owner.id], job_ids=[job.id])
        db.close()
