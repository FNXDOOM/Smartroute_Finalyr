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
from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.route_waypoint import RouteWaypointRecord
from models.user import User
from models.vehicle import Vehicle
from models.virtual_stop import VirtualStop
from routers.rides import confirm_passenger_pickup, get_ride_route
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
from services.clustering.h3_partitioner import get_h3_index, neighbouring_h3_cells
from services.routing.shared_route_builder import BuiltRoute, persist_shared_route
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


def test_neighbouring_h3_cells_include_the_cell_and_its_ring():
    cell = get_h3_index(12.9719, 77.6412, resolution=9)

    neighbours = neighbouring_h3_cells(cell, k=1)

    assert cell in neighbours
    assert len(neighbours) == 7, "a res-9 cell plus its 6 neighbours"


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

        # The final drop-off closes the run and completes *both* riders.
        confirm_carpool_dropoff(route_id=route_id, ride_id=ride_b.id, db=db, current_user=driver)
        db.refresh(ride_a)
        db.refresh(ride_b)
        assert ride_b.carpool_status == "completed"
        assert ride_a.carpool_status == "completed"
        db.refresh(persisted.route_plan)
        assert persisted.route_plan.status == "completed"

        # Explicit completion is idempotent after the run closed itself.
        result = complete_carpool_route(route_id=route_id, db=db, current_user=driver)
        assert result["status"] == "completed"
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
