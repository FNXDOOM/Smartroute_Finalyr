"""Database tuning: pool kwargs, model indexes, batch demand, heatmap snapshots, simulate job."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import inspect

from database import SessionLocal, build_engine_kwargs, create_db_tables, engine
from models.demand_snapshot import DemandSnapshot
from models.job_run import JobRun
from models.notification import Notification
from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.route_waypoint import RouteWaypointRecord
from models.user import User
from models.vehicle import Vehicle
from models.virtual_stop import VirtualStop
from routers.predict import predict_demand_heatmap
from services.background_jobs import run_demand_refresh_job, run_simulate_ride_dispatch_job
from services.clustering.h3_partitioner import get_h3_index
from services.prediction import demand_model
from utils.ride_scope import LIVE_MODE
from utils.ride_states import RIDE_ARRIVING, RIDE_ASSIGNED


def test_engine_kwargs_only_pools_postgres():
    sqlite = build_engine_kwargs("sqlite:///./x.db")
    assert sqlite == {"connect_args": {"check_same_thread": False}}
    postgres = build_engine_kwargs("postgresql://u:p@localhost/db")
    assert postgres["pool_pre_ping"] is True
    assert postgres["pool_size"] >= 1
    assert postgres["max_overflow"] >= 0
    assert postgres["pool_timeout"] >= 1
    assert postgres["pool_recycle"] == 1800


def test_performance_indexes_exist():
    create_db_tables()
    expected = {
        "ride_requests": {
            "ix_ride_requests_ride_mode_status",
            "ix_ride_requests_h3_index_status",
            "ix_ride_requests_status_request_time",
            "ix_ride_requests_cluster_id",
            "ix_ride_requests_virtual_stop_id",
        },
        "demand_snapshots": {
            "ix_demand_snapshots_created_at",
            "ix_demand_snapshots_h3_index_created_at",
        },
        "notifications": {"ix_notifications_user_id_is_read_created_at"},
        "tracking_events": {"ix_tracking_events_created_at", "ix_tracking_events_vehicle_id_created_at"},
    }
    with engine.connect() as connection:
        for table, names in expected.items():
            actual = {index["name"] for index in inspect(connection).get_indexes(table)}
            assert names <= actual, f"{table} missing {names - actual}"


def test_batch_demand_matches_grouped_counts(monkeypatch):
    monkeypatch.setattr(demand_model, "load_model", lambda: None)
    db = SessionLocal()
    user = User(name="Demand Batch", email="demand.batch@example.com", password_hash="x", role="passenger")
    db.add(user)
    db.commit()
    db.refresh(user)
    now = datetime.now(timezone.utc)
    h3_a = get_h3_index(12.34, 77.89)
    h3_b = get_h3_index(12.35, 77.90)
    rides = [
        RideRequest(user_id=user.id, pickup_lat=12.34, pickup_lng=77.89, dest_lat=12.4, dest_lng=77.9,
                    status="pending", mode=LIVE_MODE, h3_index=h3_a, request_time=now),
        RideRequest(user_id=user.id, pickup_lat=12.34, pickup_lng=77.89, dest_lat=12.4, dest_lng=77.9,
                    status="pending", mode=LIVE_MODE, h3_index=h3_a, request_time=now),
        RideRequest(user_id=user.id, pickup_lat=12.35, pickup_lng=77.90, dest_lat=12.4, dest_lng=77.9,
                    status="pending", mode=LIVE_MODE, h3_index=h3_b, request_time=now),
    ]
    db.add_all(rides)
    db.commit()
    try:
        counts = demand_model.count_requests_by_h3(db, reference_time=now, lookback_days=30)
        assert counts[h3_a] == 2
        assert counts[h3_b] == 1
        results = demand_model.predict_zone_demands(
            db, h3_indexes=[h3_a, h3_b], reference_time=now, lookback_days=30, counts_by_h3=counts
        )
        by_h3 = {item["h3_index"]: item for item in results}
        assert by_h3[h3_a]["historical_request_count"] == 2
        assert by_h3[h3_b]["historical_request_count"] == 1
        assert by_h3[h3_a]["method"] == "heuristic_fallback"
    finally:
        db.query(RideRequest).filter(RideRequest.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_demand_job_snapshots_grouped_counts(monkeypatch):
    monkeypatch.setattr(demand_model, "load_model", lambda: None)
    db = SessionLocal()
    user = User(name="Demand Job", email="demand.job@example.com", password_hash="x", role="passenger")
    db.add(user)
    db.commit()
    db.refresh(user)
    now = datetime.now(timezone.utc)
    h3_a = get_h3_index(12.36, 77.91)
    h3_b = get_h3_index(12.37, 77.92)
    rides = [
        RideRequest(user_id=user.id, pickup_lat=12.36, pickup_lng=77.91, dest_lat=12.4, dest_lng=77.9,
                    status="pending", mode=LIVE_MODE, h3_index=h3_a, request_time=now),
        RideRequest(user_id=user.id, pickup_lat=12.36, pickup_lng=77.91, dest_lat=12.4, dest_lng=77.9,
                    status="pending", mode=LIVE_MODE, h3_index=h3_a, request_time=now),
        RideRequest(user_id=user.id, pickup_lat=12.37, pickup_lng=77.92, dest_lat=12.4, dest_lng=77.9,
                    status="pending", mode=LIVE_MODE, h3_index=h3_b, request_time=now),
    ]
    db.add_all(rides)
    db.commit()
    job_id = None
    try:
        result = run_demand_refresh_job(
            db, reference_time=now, lookback_days=30,
            triggered_by_user_id=user.id, is_scheduled=False,
        )
        job_id = result["job_run_id"]
        snapshots = db.query(DemandSnapshot).filter(DemandSnapshot.job_run_id == job_id).all()
        by_h3 = {snapshot.h3_index: snapshot.historical_request_count for snapshot in snapshots}
        assert by_h3[h3_a] == 2
        assert by_h3[h3_b] == 1
    finally:
        if job_id is not None:
            db.query(DemandSnapshot).filter(DemandSnapshot.job_run_id == job_id).delete(synchronize_session=False)
            db.query(JobRun).filter(JobRun.id == job_id).delete(synchronize_session=False)
        db.query(RideRequest).filter(RideRequest.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_heatmap_prefers_latest_snapshots():
    db = SessionLocal()
    user = User(name="Heatmap Tester", email="heatmap.tester@example.com", password_hash="x", role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    job = JobRun(job_name="refresh_demand_snapshots", status="success", is_scheduled=True)
    db.add(job)
    db.commit()
    db.refresh(job)
    h3_index = get_h3_index(12.345, 77.895)
    snapshot = DemandSnapshot(
        job_run_id=job.id, h3_index=h3_index, lat=12.345, lng=77.895,
        lookback_days=30, historical_request_count=4, predicted_demand=7.5,
        model_name="test", method="heuristic_fallback",
    )
    db.add(snapshot)
    db.commit()
    try:
        response = predict_demand_heatmap(
            min_lat=12.3, min_lng=77.8, max_lat=12.4, max_lng=77.9,
            resolution=9, reference_time=None, lookback_days=30,
            db=db, current_user=user,
        )
        cell = next(item for item in response.cells if item.h3_index == h3_index)
        assert cell.predicted_demand == 7.5
        assert cell.historical_request_count == 4
    finally:
        db.query(DemandSnapshot).filter(DemandSnapshot.id == snapshot.id).delete(synchronize_session=False)
        db.query(JobRun).filter(JobRun.id == job.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_heatmap_ignores_snapshot_for_other_lookback_windows():
    db = SessionLocal()
    user = User(name="Heatmap Window", email="heatmap.window@example.com", password_hash="x", role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    job = JobRun(job_name="refresh_demand_snapshots", status="success", is_scheduled=True)
    db.add(job)
    db.commit()
    db.refresh(job)
    h3_index = get_h3_index(12.345, 77.895)
    snapshot = DemandSnapshot(
        job_run_id=job.id, h3_index=h3_index, lat=12.345, lng=77.895,
        lookback_days=30, historical_request_count=4, predicted_demand=7.5,
        model_name="test", method="heuristic_fallback",
    )
    db.add(snapshot)
    db.commit()
    try:
        response = predict_demand_heatmap(
            min_lat=12.3, min_lng=77.8, max_lat=12.4, max_lng=77.9,
            resolution=9, reference_time=None, lookback_days=7,
            db=db, current_user=user,
        )
        assert all(cell.h3_index != h3_index for cell in response.cells)
    finally:
        db.query(DemandSnapshot).filter(DemandSnapshot.id == snapshot.id).delete(synchronize_session=False)
        db.query(JobRun).filter(JobRun.id == job.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_simulate_job_still_advances_accepted_private_ride():
    db = SessionLocal()
    user = User(name="Sim Tester", email="sim.tester@example.com", password_hash="x", role="passenger")
    db.add(user)
    db.commit()
    db.refresh(user)
    vehicle = Vehicle(license_plate="TEST-SIM-001", capacity=4, mode="live", status="active",
                      driver_user_id=None, lat=12.97, lng=77.64)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    stop = VirtualStop(cluster_id=99001, mode="live", lat=12.97, lng=77.64, passenger_count=1)
    db.add(stop)
    db.commit()
    db.refresh(stop)
    ride = RideRequest(user_id=user.id, pickup_lat=12.97, pickup_lng=77.64, dest_lat=12.98, dest_lng=77.65,
                       status=RIDE_ASSIGNED, mode=LIVE_MODE, is_shared=False, virtual_stop_id=stop.id)
    db.add(ride)
    db.commit()
    db.refresh(ride)
    plan = RoutePlan(route_id="test-sim-route", vehicle_id=vehicle.id, status="solved", mode="live",
                     depot_lat=12.97, depot_lng=77.64, route_metadata={"driver_accepted": True})
    db.add(plan)
    db.commit()
    db.refresh(plan)
    waypoint = RouteWaypointRecord(route_plan_id=plan.id, sequence=1, stop_id=stop.id,
                                   lat=12.97, lng=77.64, waypoint_type="pickup")
    db.add(waypoint)
    db.commit()
    try:
        result = run_simulate_ride_dispatch_job(db, is_scheduled=False)
        assert result["updates_count"] == 1
        db.refresh(ride)
        assert ride.status == RIDE_ARRIVING

        run_simulate_ride_dispatch_job(db, is_scheduled=False)
        run_simulate_ride_dispatch_job(db, is_scheduled=False)
        db.refresh(ride)
        assert ride.status == "completed"
        db.refresh(vehicle)
        assert vehicle.status == "idle"
        assert vehicle.assigned_route_id is None
    finally:
        db.query(Notification).filter(Notification.user_id == user.id).delete(synchronize_session=False)
        db.query(RouteWaypointRecord).filter(RouteWaypointRecord.route_plan_id == plan.id).delete(synchronize_session=False)
        db.query(RoutePlan).filter(RoutePlan.id == plan.id).delete(synchronize_session=False)
        db.query(RideRequest).filter(RideRequest.id == ride.id).delete(synchronize_session=False)
        db.query(VirtualStop).filter(VirtualStop.id == stop.id).delete(synchronize_session=False)
        db.query(Vehicle).filter(Vehicle.id == vehicle.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
