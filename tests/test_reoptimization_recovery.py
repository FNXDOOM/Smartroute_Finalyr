"""Cancellation must not hide a reserved vehicle or orphan its remaining riders."""
from types import SimpleNamespace

import pytest

from database import SessionLocal
from routers.rides import cancel_ride_request, update_ride_request_status
from routers.route import accept_route, list_routes, depart_carpool_route, confirm_carpool_dropoff, complete_carpool_route
from schemas.ride_request import RideRequestStatusUpdate
from services import background_jobs
from services import carpool_lifecycle
from test_carpool_lifecycle import _two_rider_route, _cleanup, _board_rider


@pytest.fixture
def run():
    db = SessionLocal()
    driver, rider_a, rider_b, vehicle, a, b, persisted = _two_rider_route(db)
    stop_ids = [a.virtual_stop_id, b.virtual_stop_id]
    vehicle.driver_user_id = driver.id
    db.commit()
    try:
        yield db, driver, rider_a, rider_b, vehicle, a, b, persisted
    finally:
        db.rollback()
        _cleanup(db, persisted, [a.id, b.id], stop_ids, vehicle.id)
        db.close()


def test_cancellation_after_acceptance_keeps_remaining_pickup_assigned(run):
    db, driver, _, rider_b, vehicle, a, b, persisted = run
    accept_route(route_id=persisted.route_id, db=db, current_user=driver)
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    db.refresh(a)
    db.refresh(vehicle)
    assert a.status == "assigned"
    assert a.carpool_status == "driver_accepted"
    assert vehicle.assigned_route_id == persisted.route_id


def test_driver_history_includes_reoptimization_routes(run):
    db, driver, _, rider_b, _, _, b, persisted = run
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    actor = SimpleNamespace(id=driver.id, role="driver", driver_status="active")
    response = list_routes(limit=20, db=db, current_user=actor)
    assert persisted.route_id in {route.route_id for route in response.routes}


def test_listing_repairs_legacy_accepted_clustered_rider_without_freeing_vehicle(run):
    db, driver, _, rider_b, vehicle, a, b, persisted = run
    accept_route(route_id=persisted.route_id, db=db, current_user=driver)
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    a.status, a.carpool_status = "clustered", "clustered"
    db.commit()
    response = list_routes(limit=20, db=db, current_user=driver)
    db.refresh(a)
    db.refresh(vehicle)
    assert a.status == "assigned"
    assert a.carpool_status == "driver_accepted"
    assert vehicle.assigned_route_id == persisted.route_id
    assert persisted.route_id in {route.route_id for route in response.routes}


def test_worker_reconciliation_repairs_legacy_accepted_run_idempotently(run):
    db, driver, _, rider_b, vehicle, a, b, persisted = run
    accept_route(route_id=persisted.route_id, db=db, current_user=driver)
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    a.status, a.carpool_status = "clustered", "clustered"
    db.commit()
    assert carpool_lifecycle.reconcile_reoptimization_run(db, persisted.route_plan)
    db.flush()
    assert not carpool_lifecycle.reconcile_reoptimization_run(db, persisted.route_plan)
    assert a.status == "assigned"
    assert vehicle.assigned_route_id == persisted.route_id


def test_bound_clustered_rider_is_not_redispatched_to_another_vehicle(run):
    db, _, _, rider_b, _, a, b, persisted = run
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    db.refresh(a)
    assert a.status == "clustered"
    candidates = background_jobs.unassigned_clustered_rides_query(db, "live", None).all()
    assert a.id not in {ride.id for ride in candidates}


def test_onboard_rider_is_never_rewound_by_reconciliation(run):
    db, driver, rider_a, rider_b, vehicle, a, b, persisted = run
    accept_route(route_id=persisted.route_id, db=db, current_user=driver)
    _board_rider(db, persisted.route_id, driver, rider_a, a)
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    before = (a.status, a.carpool_status)
    carpool_lifecycle.reconcile_reoptimization_run(db, persisted.route_plan)
    assert (a.status, a.carpool_status) == before
    assert a.status == "in_progress"
    assert vehicle.assigned_route_id == persisted.route_id


def test_idle_label_cannot_make_reserved_vehicle_dispatchable(run):
    from models.vehicle import Vehicle
    db, _, _, _, vehicle, _, _, persisted = run
    vehicle.status = "idle"
    db.flush()
    candidates = background_jobs.available_vehicles_query(db.query(Vehicle)).all()
    assert vehicle.id not in {item.id for item in candidates}
    assert vehicle.assigned_route_id == persisted.route_id


def test_reconciliation_does_not_reactivate_historical_assignment(run):
    db, driver, _, rider_b, vehicle, a, b, persisted = run
    accept_route(route_id=persisted.route_id, db=db, current_user=driver)
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    a.status, a.carpool_status = "clustered", "clustered"
    vehicle.assigned_route_id = "some-newer-route"
    db.commit()
    assert not carpool_lifecycle.reconcile_reoptimization_run(db, persisted.route_plan)
    assert a.status == "clustered"
    assert vehicle.assigned_route_id == "some-newer-route"


def test_worker_recovers_legacy_state_without_redispatching_accepted_rider(run):
    db, driver, _, rider_b, vehicle, a, b, persisted = run
    accept_route(route_id=persisted.route_id, db=db, current_user=driver)
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    a.status, a.carpool_status = "clustered", "clustered"
    db.commit()
    result = background_jobs.run_auto_dispatch_pipeline(db, is_scheduled=False)
    db.refresh(a)
    db.refresh(vehicle)
    assert result["recovered_reoptimization_runs"] == 1
    assert result["assigned_rides"] == 0
    assert a.status == "assigned"
    assert vehicle.assigned_route_id == persisted.route_id


def test_recovered_single_remaining_rider_can_finish_and_release_vehicle(run):
    db, driver, rider_a, rider_b, vehicle, a, b, persisted = run
    accept_route(route_id=persisted.route_id, db=db, current_user=driver)
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    a.status, a.carpool_status = "clustered", "clustered"
    db.commit()
    carpool_lifecycle.reconcile_reoptimization_run(db, persisted.route_plan)
    db.commit()
    _board_rider(db, persisted.route_id, driver, rider_a, a)
    depart_carpool_route(route_id=persisted.route_id, db=db, current_user=driver)
    confirm_carpool_dropoff(route_id=persisted.route_id, ride_id=a.id, db=db, current_user=driver)
    complete_carpool_route(route_id=persisted.route_id, db=db, current_user=driver)
    db.refresh(vehicle)
    assert vehicle.status == "idle"
    assert vehicle.assigned_route_id is None


def test_private_completion_releases_reservation_on_backend(run):
    db, driver, _, rider_b, vehicle, a, b, persisted = run
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    # Private routes use the coarse status endpoint, not the carpool ladder.
    a.is_shared, a.carpool_status, a.status = False, None, "in_progress"
    persisted.route_plan.route_metadata = {
        **persisted.route_plan.route_metadata, "carpool_run": False, "driver_accepted": True,
    }
    db.commit()
    update_ride_request_status(
        ride_id=a.id, status_update=RideRequestStatusUpdate(status="completed"),
        db=db, current_user=driver,
    )
    db.refresh(vehicle)
    assert vehicle.assigned_route_id is None
    assert vehicle.status == "idle"


def test_legacy_accepted_private_rider_is_not_left_clustered(run):
    db, driver, _, rider_b, vehicle, a, b, persisted = run
    accept_route(route_id=persisted.route_id, db=db, current_user=driver)
    cancel_ride_request(ride_id=b.id, db=db, current_user=rider_b)
    a.is_shared, a.status, a.carpool_status = False, "clustered", None
    persisted.route_plan.route_metadata = {**persisted.route_plan.route_metadata, "carpool_run": False}
    db.commit()
    assert carpool_lifecycle.reconcile_reoptimization_run(db, persisted.route_plan)
    assert a.status == "assigned"
    assert a.carpool_status is None
    assert vehicle.assigned_route_id == persisted.route_id
