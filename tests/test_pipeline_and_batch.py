import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from models.user import User
from models.vehicle import Vehicle
from models.ride_request import RideRequest
from services.background_jobs import run_auto_dispatch_pipeline


def test_periodic_job_survives_a_raising_runner(caplog):
    """Nothing awaits these tasks, so an escaping exception used to retire the job silently."""
    import asyncio
    import logging

    from services.background_jobs import _run_periodic

    calls = []

    async def scenario():
        def runner(db):
            calls.append(1)
            raise RuntimeError("simulated job failure")

        task = asyncio.ensure_future(_run_periodic("simulated_job", 0.01, runner))
        try:
            # Poll for the third tick: a fixed wall-clock window can be too short under full-suite load.
            for _ in range(500):
                if len(calls) >= 3:
                    break
                await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    with caplog.at_level(logging.ERROR):
        asyncio.run(scenario())

    assert len(calls) >= 3, "schedule stopped after the first failure, ran %d time(s)" % len(calls)
    assert "simulated_job" in caplog.text, "the failure was not logged"


def test_starting_a_demo_reclaims_abandoned_demo_runs():
    """A presenter closing the app mid-demo used to strand its riders: the scheduler clusters live rides only."""
    from datetime import timedelta

    from routers.rides import create_demo_shared_batch
    from schemas.ride_request import DemoSharedBatchCreate, RideRequestCreate

    db = SessionLocal()
    user = db.query(User).filter(User.email == "pipeline_tester@example.com").first()
    if user is None:
        user = User(
            clerk_user_id="test_pipeline_user",
            email="pipeline_tester@example.com",
            name="Pipeline Tester",
            password_hash="test_hash",
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    marker_run = "abandoned-marker"
    fresh_run = "recent-marker"
    new_run = "starting-marker"
    try:
        now = datetime.now(timezone.utc)
        for run_id, age in ((marker_run, 25), (fresh_run, 1)):
            db.add(RideRequest(
                user_id=user.id, pickup_lat=12.9719, pickup_lng=77.6412,
                dest_lat=12.9756, dest_lng=77.6066, status="pending", is_shared=True,
                mode="presentation_demo", demo_run_id=run_id, request_time=now - timedelta(hours=age),
            ))
        db.commit()

        payload = DemoSharedBatchCreate(demo_run_id=new_run, riders=[
            RideRequestCreate(pickup_lat=12.9719, pickup_lng=77.6412,
                              dest_lat=12.9756, dest_lng=77.6066),
        ])
        create_demo_shared_batch(payload, db=db, current_user=user)

        assert db.query(RideRequest).filter(RideRequest.demo_run_id == marker_run).count() == 0, \
            "a demo run abandoned past the TTL should be reclaimed"
        assert db.query(RideRequest).filter(RideRequest.demo_run_id == fresh_run).count() == 1, \
            "a recent demo run must be left alone"
        assert db.query(RideRequest).filter(RideRequest.demo_run_id == new_run).count() == 1
    finally:
        for run_id in (marker_run, fresh_run, new_run):
            db.query(RideRequest).filter(RideRequest.demo_run_id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_auto_dispatch_pipeline_groups_and_assigns_rides():
    """Pipeline test: cluster, route, assign 3 rides."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "pipeline_tester@example.com").first()
        if not user:
            user = User(
                clerk_user_id="test_pipeline_user",
                email="pipeline_tester@example.com",
                name="Pipeline Tester",
                password_hash="test_hash",
                role="admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        driver = db.query(User).filter(User.email == "pipeline_driver@example.com").first()
        if not driver:
            driver = User(
                clerk_user_id="test_pipeline_driver",
                email="pipeline_driver@example.com",
                name="Pipeline Driver",
                password_hash="test_hash",
                role="driver",
                driver_status="active",
                driver_last_seen_at=datetime.now(timezone.utc),
            )
            db.add(driver)
            db.commit()
            db.refresh(driver)
        else:
            driver.role = "driver"
            driver.driver_status = "active"
            driver.driver_last_seen_at = datetime.now(timezone.utc)
            db.commit()

        vehicle = db.query(Vehicle).filter(Vehicle.license_plate == "KA-01-TEST-99").first()
        if not vehicle:
            vehicle = Vehicle(
                license_plate="KA-01-TEST-99",
                capacity=6,
                status="idle",
                lat=12.9784,
                lng=77.6408,
                driver_user_id=driver.id,
            )
            db.add(vehicle)
            db.commit()
            db.refresh(vehicle)
        else:
            vehicle.status = "idle"
            vehicle.assigned_route_id = None
            vehicle.driver_user_id = driver.id
            db.commit()

        db.query(RideRequest).filter(RideRequest.user_id == user.id).delete()
        db.commit()

        # 3 rides within 20m in same H3 cell
        presets = [
            {"plat": 12.97190, "plng": 77.64124, "dlat": 12.9756, "dlng": 77.6066},
            {"plat": 12.97192, "plng": 77.64126, "dlat": 12.9749, "dlng": 77.6080},
            {"plat": 12.97194, "plng": 77.64120, "dlat": 12.9734, "dlng": 77.6075},
        ]
        created_rides = []
        for p in presets:
            r = RideRequest(
                user_id=user.id,
                pickup_lat=p["plat"],
                pickup_lng=p["plng"],
                dest_lat=p["dlat"],
                dest_lng=p["dlng"],
                status="pending",
                pickup_label="Test Pickup",
                destination_label="Test Dest",
                ride_option_id="swift-x",
                ride_option_name="SwiftX",
                ride_option_price="₹12–15",
            )
            db.add(r)
            created_rides.append(r)
        db.commit()

        for r in created_rides:
            db.refresh(r)
            assert r.status == "pending"

        result = run_auto_dispatch_pipeline(db, triggered_by_user_id=user.id, is_scheduled=False)

        assert result["clusters_formed"] >= 1, f"Expected >=1 cluster, got {result}"
        assert result["routes_optimized"] >= 1, f"Expected >=1 route, got {result}"
        assert result["assigned_rides"] >= 2, f"Expected >=2 rides assigned, got {result}"

        assigned_count = 0
        for r in created_rides:
            db.refresh(r)
            if r.status == "assigned":
                assigned_count += 1
        assert assigned_count >= 2, f"Expected >=2 rides assigned, got {assigned_count}"

    finally:
        db.close()


def test_batch_rejects_rides_outside_the_service_area():
    """/request enforces the India geofence; /batch must not be the way around it."""
    import pytest
    from fastapi import HTTPException

    from routers.rides import create_batch_ride_requests
    from schemas.ride_request import RideRequestBatchCreate, RideRequestCreate

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "pipeline_tester@example.com").first()
        if user is None:
            user = User(
                clerk_user_id="test_pipeline_user",
                email="pipeline_tester@example.com",
                name="Pipeline Tester",
                password_hash="test_hash",
                role="admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        batch = RideRequestBatchCreate(requests=[
            RideRequestCreate(pickup_lat=51.5074, pickup_lng=-0.1278,
                              dest_lat=12.9716, dest_lng=77.5946),
        ])
        with pytest.raises(HTTPException) as refused:
            create_batch_ride_requests(batch, db=db, current_user=user)
        assert refused.value.status_code == 422
        assert db.query(RideRequest).filter(RideRequest.pickup_lat == 51.5074).first() is None
    finally:
        db.close()
