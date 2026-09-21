"""Carpool lifecycle: the per-rider stage machine, its guards, and the
rule that a route closed by driver acceptance cannot take new riders.

Follows this repo's convention of calling router/service functions directly
with a real session instead of spinning up an HTTP client.
"""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from models.notification import Notification
from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.route_waypoint import RouteWaypointRecord
from models.user import User
from models.vehicle import Vehicle
from models.virtual_stop import VirtualStop
from routers.rides import (
    cancel_ride_request,
    confirm_passenger_pickup,
    get_ride_route,
    update_ride_request_status,
)
from schemas.ride_request import RideRequestStatusUpdate
from routers.route import (
    accept_route,
    announce_carpool_pickup,
    complete_carpool_route,
    confirm_carpool_dropoff,
    confirm_carpool_pickup,
    depart_carpool_route,
    mark_carpool_arrived,
)
from services.background_jobs import _try_attach_to_existing_carpool_route
from services.clustering import h3_partitioner
from services.clustering.h3_partitioner import get_h3_index, neighbouring_h3_cells
from services.routing.shared_route_builder import BuiltRoute, persist_shared_route
from utils.carpool_status import CARPOOL_ASSIGNED, set_carpool_stage, sync_carpool_from_status
from utils.ride_scope import LIVE_MODE

DEPOT_LAT, DEPOT_LNG = 12.9784, 77.6408


def _user(db, email, role="passenger"):
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(
        clerk_user_id=f"carpool_test_{email}",
        email=email,
        name="Carpool Tester",
        password_hash="test_hash",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _two_rider_route(db):
    """Two pooled riders on one persisted carpool route."""
    driver = _user(db, "carpool_lifecycle_driver@example.com", role="admin")
    rider_a = _user(db, "carpool_rider_a@example.com")
    rider_b = _user(db, "carpool_rider_b@example.com")

    vehicle = Vehicle(
        license_plate="KA-01-CARPOOL-01",
        capacity=4,
        status="idle",
        lat=DEPOT_LAT,
        lng=DEPOT_LNG,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    stop_a = VirtualStop(cluster_id=9001, lat=12.9719, lng=77.6412, passenger_count=1)
    stop_b = VirtualStop(cluster_id=9001, lat=12.9756, lng=77.6420, passenger_count=1)
    db.add_all([stop_a, stop_b])
    db.flush()

    ride_a = RideRequest(
        user_id=rider_a.id,
        pickup_lat=12.9719,
        pickup_lng=77.6412,
        dest_lat=12.9756,
        dest_lng=77.6066,
        status="clustered",
        is_shared=True,
        carpool_status="clustered",
        virtual_stop_id=stop_a.id,
    )
    ride_b = RideRequest(
        user_id=rider_b.id,
        pickup_lat=12.9756,
        pickup_lng=77.6420,
        dest_lat=12.9756,
        dest_lng=77.6066,
        status="clustered",
        is_shared=True,
        carpool_status="clustered",
        virtual_stop_id=stop_b.id,
    )
    db.add_all([ride_a, ride_b])
    db.commit()
    db.refresh(ride_a)
    db.refresh(ride_b)

    built = BuiltRoute(
        vehicle_index=0,
        depot_lat=DEPOT_LAT,
        depot_lng=DEPOT_LNG,
        waypoints=[
            {"stop_id": None, "lat": DEPOT_LAT, "lng": DEPOT_LNG, "waypoint_type": "depot", "passenger_ids": []},
            {"stop_id": stop_a.id, "lat": stop_a.lat, "lng": stop_a.lng, "waypoint_type": "pickup", "passenger_ids": [ride_a.id]},
            {"stop_id": stop_b.id, "lat": stop_b.lat, "lng": stop_b.lng, "waypoint_type": "pickup", "passenger_ids": [ride_b.id]},
            {"stop_id": None, "lat": 12.9756, "lng": 77.6066, "waypoint_type": "destination", "passenger_ids": [ride_a.id]},
            {"stop_id": None, "lat": 12.9755, "lng": 77.6060, "waypoint_type": "destination", "passenger_ids": [ride_b.id]},
        ],
        ride_ids=[ride_a.id, ride_b.id],
        destination_ride_ids=[ride_a.id, ride_b.id],
        stop_ids=[stop_a.id, stop_b.id],
        distance_m=4200,
        duration_s=480,
        problem="pdp",
    )
    persisted = persist_shared_route(
        db, built, vehicle=vehicle, assign_statuses=("clustered",)
    )
    db.commit()
    return driver, rider_a, rider_b, vehicle, ride_a, ride_b, persisted


def _cleanup(db, persisted, ride_ids, stop_ids, vehicle_id):
    db.query(RouteWaypointRecord).filter(
        RouteWaypointRecord.route_plan_id == persisted.route_plan.id
    ).delete(synchronize_session=False)
    db.query(RoutePlan).filter(RoutePlan.id == persisted.route_plan.id).delete(
        synchronize_session=False
    )
    db.query(RideRequest).filter(RideRequest.id.in_(ride_ids)).delete(
        synchronize_session=False
    )
    db.query(VirtualStop).filter(VirtualStop.id.in_(stop_ids)).delete(
        synchronize_session=False
    )
    db.query(Vehicle).filter(Vehicle.id == vehicle_id).delete(synchronize_session=False)
    db.commit()


def _board_rider(db, route_id, driver, rider, ride):
    """Drive one rider from 'announced' through to being onboard the car."""
    announce_carpool_pickup(route_id=route_id, ride_id=ride.id, db=db, current_user=driver)
    mark_carpool_arrived(route_id=route_id, ride_id=ride.id, db=db, current_user=driver)
    confirm_passenger_pickup(ride_id=ride.id, db=db, current_user=rider)
    confirm_carpool_pickup(route_id=route_id, ride_id=ride.id, db=db, current_user=driver)


def test_neighbouring_h3_cells_include_the_cell_and_its_ring():
    cell = get_h3_index(12.9719, 77.6412, resolution=9)

    neighbours = neighbouring_h3_cells(cell, k=1)

    # 7 for a hexagon, 6 for a pentagon — H3 clips the ring at a pentagon.
    assert cell in neighbours
    assert len(neighbours) in (6, 7)


def test_neighbouring_h3_cells_degrade_to_the_cell_alone(monkeypatch):
    """A build without a ring API must not crash the clustering pass."""
    monkeypatch.delattr(h3_partitioner.h3, "grid_disk", raising=False)
    monkeypatch.delattr(h3_partitioner.h3, "k_ring", raising=False)
    cell = get_h3_index(12.9719, 77.6412, resolution=9)

    assert h3_partitioner.neighbouring_h3_cells(cell) == {cell}


def test_carpool_lifecycle_walks_every_stage_then_completes():
    db = SessionLocal()
    persisted = None
    try:
        driver, rider_a, rider_b, vehicle, ride_a, ride_b, persisted = _two_rider_route(db)
        route_id = persisted.route_id

        # Driver accepts the run: both riders advance together.
        accept_route(route_id=route_id, db=db, current_user=driver)
        db.refresh(ride_a)
        db.refresh(ride_b)
        assert ride_a.carpool_status == "driver_accepted"
        assert ride_b.carpool_status == "driver_accepted"
        assert ride_a.status == "assigned"

        # The passenger's route view now exposes driver acceptance.
        route_view = get_ride_route(ride_id=ride_a.id, db=db, current_user=rider_a)
        assert route_view is not None
        assert route_view.driver_accepted is True
        assert route_view.carpool_status == "driver_accepted"

        # Driver heads to rider A, arrives, then boards them.
        announce_carpool_pickup(route_id=route_id, ride_id=ride_a.id, db=db, current_user=driver)
        db.refresh(ride_a)
        assert ride_a.carpool_status == "driver_arriving"
        assert ride_a.status == "arriving"

        mark_carpool_arrived(route_id=route_id, ride_id=ride_a.id, db=db, current_user=driver)
        db.refresh(ride_a)
        assert ride_a.carpool_status == "pickup_ready"

        confirm_passenger_pickup(ride_id=ride_a.id, db=db, current_user=rider_a)
        db.refresh(ride_a)
        assert ride_a.carpool_status == "passenger_confirmed_pickup_stop"
        assert ride_a.status == "ready_for_pickup"

        confirm_carpool_pickup(route_id=route_id, ride_id=ride_a.id, db=db, current_user=driver)
        db.refresh(ride_a)
        assert ride_a.carpool_status == "boarded"

        depart_carpool_route(route_id=route_id, db=db, current_user=driver)
        db.refresh(ride_a)
        assert ride_a.carpool_status == "in_transit"

        confirm_carpool_dropoff(route_id=route_id, ride_id=ride_a.id, db=db, current_user=driver)
        db.refresh(ride_a)
        assert ride_a.carpool_status == "dropped_off"

        # Rider B is still waiting, so the run must not be completable yet.
        with pytest.raises(HTTPException) as refused:
            complete_carpool_route(route_id=route_id, db=db, current_user=driver)
        assert refused.value.status_code == 409

        # Drive rider B through the same stops.
        announce_carpool_pickup(route_id=route_id, ride_id=ride_b.id, db=db, current_user=driver)
        mark_carpool_arrived(route_id=route_id, ride_id=ride_b.id, db=db, current_user=driver)
        confirm_passenger_pickup(ride_id=ride_b.id, db=db, current_user=rider_b)
        confirm_carpool_pickup(route_id=route_id, ride_id=ride_b.id, db=db, current_user=driver)
        depart_carpool_route(route_id=route_id, db=db, current_user=driver)

        # The final drop-off records the drop-off but leaves the run open: only
        # an explicit completion closes it and releases the vehicle.
        confirm_carpool_dropoff(route_id=route_id, ride_id=ride_b.id, db=db, current_user=driver)
        db.refresh(ride_a)
        db.refresh(ride_b)
        db.refresh(persisted.route_plan)
        assert ride_a.carpool_status == "dropped_off"
        assert ride_b.carpool_status == "dropped_off"
        assert persisted.route_plan.status == "solved"

        result = complete_carpool_route(route_id=route_id, db=db, current_user=driver)
        assert result["status"] == "completed"
        db.refresh(ride_a)
        db.refresh(ride_b)
        db.refresh(persisted.route_plan)
        db.refresh(vehicle)
        assert ride_a.carpool_status == "completed"
        assert ride_b.carpool_status == "completed"
        assert persisted.route_plan.status == "completed"
        assert vehicle.status == "idle"
        assert vehicle.assigned_route_id is None

        # Explicit completion is idempotent after the run closed.
        result = complete_carpool_route(route_id=route_id, db=db, current_user=driver)
        assert result["status"] == "completed"
        assert result["already_completed"] is True
    finally:
        if persisted is not None:
            _cleanup(
                db,
                persisted,
                [r.id for r in (ride_a, ride_b)],
                [ride_a.virtual_stop_id, ride_b.virtual_stop_id],
                vehicle.id,
            )
        db.close()


def test_mark_arrived_requires_the_driver_to_be_arriving_first():
    db = SessionLocal()
    persisted = None
    try:
        driver, rider_a, rider_b, vehicle, ride_a, ride_b, persisted = _two_rider_route(db)
        accept_route(route_id=persisted.route_id, db=db, current_user=driver)

        # Not yet announced -> the driver cannot jump straight to "arrived".
        with pytest.raises(HTTPException) as refused:
            mark_carpool_arrived(
                route_id=persisted.route_id, ride_id=ride_a.id, db=db, current_user=driver
            )
        assert refused.value.status_code == 409
    finally:
        if persisted is not None:
            _cleanup(
                db,
                persisted,
                [r.id for r in (ride_a, ride_b)],
                [ride_a.virtual_stop_id, ride_b.virtual_stop_id],
                vehicle.id,
            )
        db.close()


def test_accepted_route_is_closed_to_new_riders():
    db = SessionLocal()
    persisted = None
    new_ride = None
    try:
        driver, rider_a, rider_b, vehicle, ride_a, ride_b, persisted = _two_rider_route(db)
        accept_route(route_id=persisted.route_id, db=db, current_user=driver)

        # A rider whose pickup sits right on the accepted route's corridor.
        strander = _user(db, "carpool_strander@example.com")
        new_ride = RideRequest(
            user_id=strander.id,
            pickup_lat=12.9756,
            pickup_lng=77.6400,
            dest_lat=12.9756,
            dest_lng=77.6066,
            status="pending",
            is_shared=True,
            carpool_status="pending",
        )
        db.add(new_ride)
        db.commit()
        db.refresh(new_ride)

        attached = _try_attach_to_existing_carpool_route(
            db, new_ride, mode=LIVE_MODE, demo_run_id=None
        )

        assert attached is False, "a driver-accepted route must not take new riders"
        db.refresh(new_ride)
        assert new_ride.virtual_stop_id is None
        assert new_ride.status == "pending"
    finally:
        if new_ride is not None:
            db.query(RideRequest).filter(RideRequest.id == new_ride.id).delete(
                synchronize_session=False
            )
        if persisted is not None:
            _cleanup(
                db,
                persisted,
                [r.id for r in (ride_a, ride_b)],
                [ride_a.virtual_stop_id, ride_b.virtual_stop_id],
                vehicle.id,
            )
        db.commit()
        db.close()


def _notification_count(db, user_id, notification_type):
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.notification_type == notification_type,
    ).count()


def test_repeated_accept_does_not_resurrect_a_dropped_off_rider():
    """Accept stays retry-safe: riders already past it are left alone."""
    db = SessionLocal()
    persisted = None
    try:
        driver, rider_a, rider_b, vehicle, ride_a, ride_b, persisted = _two_rider_route(db)
        route_id = persisted.route_id
        accept_route(route_id=route_id, db=db, current_user=driver)
        _board_rider(db, route_id, driver, rider_a, ride_a)
        depart_carpool_route(route_id=route_id, db=db, current_user=driver)
        confirm_carpool_dropoff(route_id=route_id, ride_id=ride_a.id, db=db, current_user=driver)
        db.refresh(ride_a)
        assert ride_a.carpool_status == "dropped_off"
        accepted_before = _notification_count(db, rider_a.id, "carpool_driver_accepted")

        # A client retry of the same POST must not walk rider A backwards.
        accept_route(route_id=route_id, db=db, current_user=driver)

        db.refresh(ride_a)
        assert ride_a.carpool_status == "dropped_off"
        assert ride_a.status == "completed"
        assert _notification_count(db, rider_a.id, "carpool_driver_accepted") == accepted_before
        db.refresh(ride_b)
        assert ride_b.carpool_status == "driver_accepted"
    finally:
        if persisted is not None:
            _cleanup(
                db,
                persisted,
                [r.id for r in (ride_a, ride_b)],
                [ride_a.virtual_stop_id, ride_b.virtual_stop_id],
                vehicle.id,
            )
        db.close()


def test_a_co_passenger_cancellation_does_not_lock_out_the_remaining_riders():
    """A cancellation rewrites the plan to needs_reoptimization; the driver can
    still finish the riders already on board and get their vehicle back."""
    db = SessionLocal()
    persisted = None
    try:
        driver, rider_a, rider_b, vehicle, ride_a, ride_b, persisted = _two_rider_route(db)
        route_id = persisted.route_id
        accept_route(route_id=route_id, db=db, current_user=driver)
        _board_rider(db, route_id, driver, rider_a, ride_a)
        depart_carpool_route(route_id=route_id, db=db, current_user=driver)

        cancel_ride_request(ride_id=ride_b.id, db=db, current_user=rider_b)
        db.refresh(persisted.route_plan)
        assert persisted.route_plan.status == "needs_reoptimization"

        confirm_carpool_dropoff(route_id=route_id, ride_id=ride_a.id, db=db, current_user=driver)
        complete_carpool_route(route_id=route_id, db=db, current_user=driver)

        db.refresh(persisted.route_plan)
        db.refresh(vehicle)
        db.refresh(ride_a)
        assert persisted.route_plan.status == "completed"
        assert vehicle.status == "idle"
        assert vehicle.assigned_route_id is None
        assert ride_a.carpool_status == "completed"
    finally:
        if persisted is not None:
            _cleanup(
                db,
                persisted,
                [r.id for r in (ride_a, ride_b)],
                [ride_a.virtual_stop_id, ride_b.virtual_stop_id],
                vehicle.id,
            )
        db.close()


def test_depart_requires_someone_to_have_boarded():
    db = SessionLocal()
    persisted = None
    try:
        driver, rider_a, rider_b, vehicle, ride_a, ride_b, persisted = _two_rider_route(db)
        accept_route(route_id=persisted.route_id, db=db, current_user=driver)

        with pytest.raises(HTTPException) as refused:
            depart_carpool_route(route_id=persisted.route_id, db=db, current_user=driver)
        assert refused.value.status_code == 409
    finally:
        if persisted is not None:
            _cleanup(
                db,
                persisted,
                [r.id for r in (ride_a, ride_b)],
                [ride_a.virtual_stop_id, ride_b.virtual_stop_id],
                vehicle.id,
            )
        db.close()


def test_only_the_assigned_driver_can_patch_a_riders_status():
    """A second driver must not be able to complete another driver's rider,
    which would close that run, release its vehicle and notify its riders."""
    db = SessionLocal()
    persisted = None
    try:
        driver, rider_a, rider_b, vehicle, ride_a, ride_b, persisted = _two_rider_route(db)
        route_id = persisted.route_id
        owner = _user(db, "carpool_owner_driver@example.com", role="driver")
        stranger = _user(db, "carpool_stranger_driver@example.com", role="driver")
        vehicle.driver_user_id = owner.id
        db.commit()

        accept_route(route_id=route_id, db=db, current_user=driver)
        _board_rider(db, route_id, driver, rider_a, ride_a)

        accepted_before = _notification_count(db, rider_a.id, "carpool_route_completed")

        with pytest.raises(HTTPException) as refused:
            update_ride_request_status(
                ride_id=ride_a.id,
                status_update=RideRequestStatusUpdate(status="completed"),
                db=db,
                current_user=stranger,
            )
        assert refused.value.status_code == 403

        db.refresh(ride_a)
        db.refresh(persisted.route_plan)
        db.refresh(vehicle)
        assert ride_a.carpool_status == "boarded"
        assert persisted.route_plan.status == "solved"
        assert vehicle.assigned_route_id == route_id
        assert _notification_count(db, rider_a.id, "carpool_route_completed") == accepted_before

        # The driver who actually holds the run is not affected.
        update_ride_request_status(
            ride_id=ride_a.id,
            status_update=RideRequestStatusUpdate(status="completed"),
            db=db,
            current_user=owner,
        )
        db.refresh(ride_a)
        assert ride_a.carpool_status == "completed"
    finally:
        if persisted is not None:
            _cleanup(
                db,
                persisted,
                [r.id for r in (ride_a, ride_b)],
                [ride_a.virtual_stop_id, ride_b.virtual_stop_id],
                vehicle.id,
            )
        db.close()


def test_private_rides_stay_off_the_carpool_axis():
    private = RideRequest(
        user_id=1,
        pickup_lat=DEPOT_LAT,
        pickup_lng=DEPOT_LNG,
        dest_lat=DEPOT_LAT,
        dest_lng=DEPOT_LNG,
        status="pending",
        is_shared=False,
    )

    set_carpool_stage(private, CARPOOL_ASSIGNED)
    assert private.carpool_status is None
    assert private.status == "pending"

    private.status = "arriving"
    sync_carpool_from_status(private)
    assert private.carpool_status is None

    pooled = RideRequest(
        user_id=1,
        pickup_lat=DEPOT_LAT,
        pickup_lng=DEPOT_LNG,
        dest_lat=DEPOT_LAT,
        dest_lng=DEPOT_LNG,
        status="pending",
        is_shared=True,
    )
    set_carpool_stage(pooled, CARPOOL_ASSIGNED)
    assert pooled.carpool_status == CARPOOL_ASSIGNED
    assert pooled.status == "assigned"
