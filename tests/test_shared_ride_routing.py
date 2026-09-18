"""Pooled shared-ride routing: leg splitting, the pickup/delivery solver, and
the passenger-visible route endpoint.

The suite follows this repo's convention of exercising services and route
functions directly with a real session, rather than spinning up an HTTP client.
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
from routers.rides import get_ride_route
from routers.route import get_route_history
from services.routing import shared_route_builder
from services.routing.shared_route_builder import (
    BuiltRoute,
    _merge_route_details,
    build_shared_routes,
    persist_shared_route,
)
from services.stadia_client import extract_route_details

DEPOT_LAT, DEPOT_LNG = 12.9784, 77.6408
STOP_LAT, STOP_LNG = 12.9719, 77.6412


def _encode_polyline(lat_lng_pairs, precision=6):
    """Inverse of the backend's polyline decoder (lat then lng per point)."""
    factor = 10 ** precision
    chunks = []
    previous_lat = previous_lng = 0
    for lat, lng in lat_lng_pairs:
        for delta, previous in (
            (int(round(lat * factor)) - previous_lat, previous_lat),
            (int(round(lng * factor)) - previous_lng, previous_lng),
        ):
            value = ~(delta << 1) if delta < 0 else (delta << 1)
            while value >= 0x20:
                chunks.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            chunks.append(chr(value + 63))
        previous_lat = int(round(lat * factor))
        previous_lng = int(round(lng * factor))
    return "".join(chunks)


def _user(db, email):
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(
        clerk_user_id=f"test_shared_route_{email}",
        email=email,
        name="Shared Route Tester",
        password_hash="test_hash",
        role="passenger",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _driver(db, email="shared_route_driver@example.com"):
    user = _user(db, email)
    if user.role != "admin":
        user.role = "admin"
        db.commit()
    return user


def _vehicle(db, license_plate="KA-01-POOL-01"):
    vehicle = db.query(Vehicle).filter(Vehicle.license_plate == license_plate).first()
    if vehicle:
        vehicle.status = "idle"
        vehicle.assigned_route_id = None
        db.commit()
        return vehicle
    vehicle = Vehicle(
        license_plate=license_plate,
        capacity=4,
        status="idle",
        lat=DEPOT_LAT,
        lng=DEPOT_LNG,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


# --- leg splitting -----------------------------------------------------------


def test_extract_route_details_splits_each_leg_and_keeps_the_stitched_geometry():
    leg_one = [(12.9784, 77.6408), (12.9740, 77.6411)]
    leg_two = [(12.9740, 77.6411), (12.9756, 77.6066)]
    payload = {
        "trip": {
            "summary": {"length": 4.2, "time": 480},
            "legs": [
                {
                    "shape": _encode_polyline(leg_one),
                    "summary": {"length": 1.2, "time": 120},
                    "maneuvers": [{"instruction": "Head south", "length": 1.2, "time": 120}],
                },
                {
                    "shape": _encode_polyline(leg_two),
                    "summary": {"length": 3.0, "time": 360},
                    "maneuvers": [{"instruction": "Turn right", "length": 3.0, "time": 360}],
                },
            ],
        }
    }

    details = extract_route_details(payload)

    # The stitched polyline existing callers rely on is unchanged in order...
    assert len(details["geometry"]) == 3
    assert details["geometry"][0] == pytest.approx([77.6408, 12.9784], abs=1e-5)
    assert details["geometry"][-1] == pytest.approx([77.6066, 12.9756], abs=1e-5)

    # ...and each leg now carries its own coordinates, distance and duration.
    assert [leg["index"] for leg in details["legs"]] == [0, 1]
    assert len(details["legs"][0]["geometry"]) == 2
    assert len(details["legs"][1]["geometry"]) == 2
    assert details["legs"][0]["distanceMeters"] == pytest.approx(1200)
    assert details["legs"][1]["durationSeconds"] == pytest.approx(360)
    assert details["legs"][0]["begin_shape_index"] == 0
    assert details["legs"][1]["begin_shape_index"] == 1
    assert len(details["maneuvers"]) == 2


def test_merge_route_details_renumbers_legs_across_windows():
    first = {
        "geometry": [[77.60, 12.97], [77.61, 12.97], [77.62, 12.97]],
        "legs": [
            {"index": 0, "geometry": [[77.60, 12.97], [77.61, 12.97]], "distanceMeters": 100, "durationSeconds": 10},
            {"index": 1, "geometry": [[77.61, 12.97], [77.62, 12.97]], "distanceMeters": 100, "durationSeconds": 10},
        ],
        "maneuvers": [],
    }
    second = {
        "geometry": [[77.62, 12.97], [77.63, 12.97]],
        "legs": [
            {"index": 0, "geometry": [[77.62, 12.97], [77.63, 12.97]], "distanceMeters": 100, "durationSeconds": 10},
        ],
        "maneuvers": [],
    }

    merged = _merge_route_details([first, second])

    assert [leg["index"] for leg in merged["legs"]] == [0, 1, 2]
    assert merged["legs"][2]["begin_shape_index"] == 2
    assert merged["legs"][2]["end_shape_index"] == 3
    assert len(merged["geometry"]) == 4
    assert merged["distance_meters"] == pytest.approx(300)


# --- pickup and delivery solver ---------------------------------------------


def test_pool_solver_boards_before_dropping_and_leaves_the_route_open():
    pytest.importorskip("ortools.constraint_solver")
    from services.routing.vrp_solver import solve_shared_ride_pdp

    nodes = [
        {"lat": DEPOT_LAT, "lng": DEPOT_LNG, "kind": "depot", "demand": 0},
        {"lat": STOP_LAT, "lng": STOP_LNG, "kind": "pickup", "demand": 2},
        {"lat": 12.9756, "lng": 77.6066, "kind": "destination", "demand": 1, "pair_index": 1},
        {"lat": 12.9749, "lng": 77.6080, "kind": "destination", "demand": 1, "pair_index": 1},
    ]

    solution = solve_shared_ride_pdp(nodes, num_vehicles=1, vehicle_capacity=2)

    assert solution["status"] == "solved"
    route = solution["routes"][0]["stop_indices"]
    assert route[0] == 0, "every route starts at the depot"
    assert len(route) == 4, "depot + one boarding stop + two drop-offs"
    assert route.index(1) < route.index(2)
    assert route.index(1) < route.index(3)
    assert route[-1] in (2, 3), "the route ends at a drop-off, not back at the depot"


def test_pool_solver_reuses_a_seat_after_a_drop_off_where_cvrp_cannot():
    pytest.importorskip("ortools.constraint_solver")
    from services.routing.vrp_solver import solve_shared_ride_pdp, solve_vrp

    # Two riders, one seat. Only a model that hands the seat back at a drop-off
    # can serve both, which is exactly what the pickups-only CVRP could not do.
    nodes = [
        {"lat": DEPOT_LAT, "lng": DEPOT_LNG, "kind": "depot", "demand": 0},
        {"lat": 12.9719, "lng": 77.6412, "kind": "pickup", "demand": 1},
        {"lat": 12.9740, "lng": 77.6200, "kind": "destination", "demand": 1, "pair_index": 1},
        {"lat": 12.9760, "lng": 77.6300, "kind": "pickup", "demand": 1},
        {"lat": 12.9730, "lng": 77.6000, "kind": "destination", "demand": 1, "pair_index": 3},
    ]

    solution = solve_shared_ride_pdp(nodes, num_vehicles=1, vehicle_capacity=1)

    assert solution["status"] == "solved"
    route = solution["routes"][0]["stop_indices"]
    assert route.index(2) < route.index(3), "first rider is dropped before the second boards"

    cvrp = solve_vrp(
        stops=[
            {"lat": DEPOT_LAT, "lng": DEPOT_LNG, "demand": 0},
            {"lat": 12.9719, "lng": 77.6412, "demand": 1},
            {"lat": 12.9760, "lng": 77.6300, "demand": 1},
        ],
        num_vehicles=1,
        vehicle_capacity=1,
    )
    assert cvrp["status"] == "no_solution", "pickups-only demand never frees a seat"


# --- shared route builder ----------------------------------------------------


class _StubRequest:
    def __init__(self, request_id, status="clustered"):
        self.id = request_id
        self.status = status
        self.dest_lat = 12.9756
        self.dest_lng = 77.6066


class _StubStop:
    def __init__(self, stop_id, requests):
        self.id = stop_id
        self.lat = STOP_LAT
        self.lng = STOP_LNG
        self.passenger_count = len(requests)
        self.ride_requests = requests


class _StubVehicle:
    def __init__(self, capacity=2):
        self.id = 1
        self.capacity = capacity


def test_builder_uses_the_pool_model_for_a_feasible_pool():
    pytest.importorskip("ortools.constraint_solver")
    stop = _StubStop(7, [_StubRequest(101), _StubRequest(102)])

    routes = build_shared_routes(
        vehicles=[_StubVehicle(capacity=2)],
        virtual_stops=[stop],
        depot_lat=DEPOT_LAT,
        depot_lng=DEPOT_LNG,
        request_statuses=("clustered",),
        enrich=False,
    )

    assert len(routes) == 1
    built = routes[0]
    assert built.problem == "pdp"
    assert [waypoint["waypoint_type"] for waypoint in built.waypoints] == [
        "pickup",
        "destination",
        "destination",
    ]
    assert built.stop_ids == [7]
    assert built.ride_ids == [101, 102]
    assert built.destination_ride_ids == [101, 102]
    assert built.waypoints[0]["passenger_ids"] == [101, 102]
    assert built.waypoints[1]["stop_id"] is None


def test_builder_falls_back_to_pickups_only_when_the_pool_is_infeasible(monkeypatch):
    monkeypatch.setattr(
        shared_route_builder,
        "solve_shared_ride_pdp",
        lambda **kwargs: {"routes": [], "total_distance_m": 0, "status": "no_solution"},
    )
    stop = _StubStop(7, [_StubRequest(101), _StubRequest(102)])

    routes = build_shared_routes(
        vehicles=[_StubVehicle(capacity=4)],
        virtual_stops=[stop],
        depot_lat=DEPOT_LAT,
        depot_lng=DEPOT_LNG,
        request_statuses=("clustered",),
        enrich=False,
    )

    assert len(routes) == 1
    built = routes[0]
    assert built.problem == "cvrp"
    # The old shape: pickups, then the drive back to the hub.
    assert [waypoint["waypoint_type"] for waypoint in built.waypoints] == ["pickup", "depot"]


def test_builder_returns_nothing_when_no_model_can_serve_the_pool():
    pytest.importorskip("ortools.constraint_solver")
    stop = _StubStop(7, [_StubRequest(101), _StubRequest(102), _StubRequest(103)])

    routes = build_shared_routes(
        vehicles=[_StubVehicle(capacity=2)],
        virtual_stops=[stop],
        depot_lat=DEPOT_LAT,
        depot_lng=DEPOT_LNG,
        request_statuses=("clustered",),
        enrich=False,
    )

    assert routes == []


# --- passenger-visible route -------------------------------------------------


def test_route_history_serves_promoted_legs_and_resolves_geometry_once(monkeypatch):
    """A driver's route plan must expose geometry/legs, resolving them once.

    Plans written by the automatic dispatch job carry stops but no road
    geometry, so the first driver view fetches it and every later view is
    served from the cached copy.
    """
    db = SessionLocal()
    created_plan_id = None
    created_ride_id = None
    created_stop_id = None
    try:
        driver = _driver(db)
        vehicle = _vehicle(db, "KA-01-DRIVER-01")
        stop = VirtualStop(cluster_id=1, lat=STOP_LAT, lng=STOP_LNG, passenger_count=2)
        db.add(stop)
        db.flush()
        created_stop_id = stop.id

        ride = RideRequest(
            user_id=driver.id,
            pickup_lat=STOP_LAT,
            pickup_lng=STOP_LNG,
            dest_lat=12.9756,
            dest_lng=77.6066,
            status="assigned",
            virtual_stop_id=stop.id,
        )
        db.add(ride)
        db.commit()
        db.refresh(ride)
        created_ride_id = ride.id

        built = BuiltRoute(
            vehicle_index=0,
            depot_lat=DEPOT_LAT,
            depot_lng=DEPOT_LNG,
            waypoints=[
                {
                    "stop_id": stop.id,
                    "lat": STOP_LAT,
                    "lng": STOP_LNG,
                    "waypoint_type": "pickup",
                    "passenger_ids": [ride.id],
                },
                {
                    "stop_id": None,
                    "lat": 12.9756,
                    "lng": 77.6066,
                    "waypoint_type": "destination",
                    "passenger_ids": [ride.id],
                },
            ],
            ride_ids=[ride.id],
            destination_ride_ids=[ride.id],
            stop_ids=[stop.id],
            distance_m=4200,
            duration_s=480,
            problem="pdp",
        )
        persisted = persist_shared_route(
            db,
            built,
            vehicle=vehicle,
            source_cluster_run_id=None,
        )
        db.commit()
        created_plan_id = persisted.route_plan.id

        resolver_calls = []

        def _fake_enrich(points):
            resolver_calls.append(points)
            return {
                "geometry": [[77.6412, 12.9719], [77.6066, 12.9756]],
                "legs": [{
                    "index": 0,
                    "geometry": [[77.6412, 12.9719], [77.6066, 12.9756]],
                    "distance_meters": 4200,
                    "duration_seconds": 480,
                    "begin_shape_index": 0,
                    "end_shape_index": 1,
                }],
                "maneuvers": [],
                "distance_meters": 4200,
                "duration_seconds": 480,
            }

        monkeypatch.setattr(shared_route_builder, "enrich_route_geometry", _fake_enrich)

        response = get_route_history(
            route_id=persisted.route_id, db=db, current_user=driver
        )

        assert response.problem == "pdp"
        assert len(response.geometry) == 2
        assert len(response.legs) == 1
        assert response.legs[0].distance_meters == pytest.approx(4200)
        assert [waypoint.waypoint_type for waypoint in response.waypoints] == [
            "pickup",
            "destination",
        ]
        assert response.waypoints[0].passenger_ids == [ride.id]
        assert len(resolver_calls) == 1

        # Second view: served from the plan's cached geometry, router untouched.
        again = get_route_history(
            route_id=persisted.route_id, db=db, current_user=driver
        )
        assert len(again.legs) == 1
        assert len(resolver_calls) == 1, "cached geometry must not be re-fetched"
    finally:
        if created_plan_id is not None:
            db.query(RouteWaypointRecord).filter(
                RouteWaypointRecord.route_plan_id == created_plan_id
            ).delete(synchronize_session=False)
            db.query(RoutePlan).filter(RoutePlan.id == created_plan_id).delete(
                synchronize_session=False
            )
        if created_ride_id is not None:
            db.query(RideRequest).filter(RideRequest.id == created_ride_id).delete(
                synchronize_session=False
            )
        if created_stop_id is not None:
            db.query(VirtualStop).filter(VirtualStop.id == created_stop_id).delete(
                synchronize_session=False
            )
        db.commit()
        db.close()


def test_ride_route_endpoint_serves_pooled_legs_without_calling_the_router(monkeypatch):
    db = SessionLocal()
    created_ride_ids = []
    created_stop_ids = []
    created_plan_id = None
    try:
        rider = _user(db, "shared_route_rider@example.com")
        stranger = _user(db, "shared_route_stranger@example.com")
        vehicle = _vehicle(db)

        stop = VirtualStop(cluster_id=1, lat=STOP_LAT, lng=STOP_LNG, passenger_count=2)
        db.add(stop)
        db.flush()
        created_stop_ids.append(stop.id)

        ride = RideRequest(
            user_id=rider.id,
            pickup_lat=STOP_LAT,
            pickup_lng=STOP_LNG,
            dest_lat=12.9756,
            dest_lng=77.6066,
            status="clustered",
            virtual_stop_id=stop.id,
        )
        co_rider = RideRequest(
            user_id=rider.id,
            pickup_lat=STOP_LAT,
            pickup_lng=STOP_LNG,
            dest_lat=12.9749,
            dest_lng=77.6080,
            status="clustered",
            virtual_stop_id=stop.id,
        )
        plain_ride = RideRequest(
            user_id=rider.id,
            pickup_lat=STOP_LAT,
            pickup_lng=STOP_LNG,
            dest_lat=12.9749,
            dest_lng=77.6080,
            status="assigned",
        )
        db.add_all([ride, co_rider, plain_ride])
        db.commit()
        for created in (ride, co_rider, plain_ride):
            db.refresh(created)
            created_ride_ids.append(created.id)

        built = BuiltRoute(
            vehicle_index=0,
            depot_lat=DEPOT_LAT,
            depot_lng=DEPOT_LNG,
            waypoints=[
                {"stop_id": None, "lat": DEPOT_LAT, "lng": DEPOT_LNG, "waypoint_type": "depot", "passenger_ids": []},
                {
                    "stop_id": stop.id,
                    "lat": STOP_LAT,
                    "lng": STOP_LNG,
                    "waypoint_type": "pickup",
                    "passenger_ids": [ride.id, co_rider.id],
                },
                {
                    "stop_id": None,
                    "lat": 12.9756,
                    "lng": 77.6066,
                    "waypoint_type": "destination",
                    "passenger_ids": [ride.id],
                },
                {
                    "stop_id": None,
                    "lat": 12.9749,
                    "lng": 77.6080,
                    "waypoint_type": "destination",
                    "passenger_ids": [co_rider.id],
                },
            ],
            ride_ids=[ride.id, co_rider.id],
            destination_ride_ids=[ride.id, co_rider.id],
            stop_ids=[stop.id],
            distance_m=4200,
            duration_s=480,
            geometry=[[77.6408, 12.9784], [77.6411, 12.974], [77.6066, 12.9756], [77.608, 12.9749]],
            legs=[
                {
                    "index": 0,
                    "geometry": [[77.6408, 12.9784], [77.6411, 12.974]],
                    "distance_meters": 1200,
                    "duration_seconds": 120,
                    "begin_shape_index": 0,
                    "end_shape_index": 1,
                },
                {
                    "index": 1,
                    "geometry": [[77.6411, 12.974], [77.6066, 12.9756]],
                    "distance_meters": 3000,
                    "duration_seconds": 360,
                    "begin_shape_index": 1,
                    "end_shape_index": 2,
                },
                {
                    "index": 2,
                    "geometry": [[77.6066, 12.9756], [77.608, 12.9749]],
                    "distance_meters": 200,
                    "duration_seconds": 60,
                    "begin_shape_index": 2,
                    "end_shape_index": 3,
                },
            ],
            provider="stadia",
            problem="pdp",
        )
        persisted = persist_shared_route(
            db,
            built,
            vehicle=vehicle,
            assign_statuses=("clustered",),
        )
        db.commit()
        created_plan_id = persisted.route_plan.id

        # Geometry is already cached on the plan, so a poll must never reach the
        # routing provider.
        def _explode(*args, **kwargs):
            raise AssertionError("cached route geometry must not hit the router")

        monkeypatch.setattr(shared_route_builder, "enrich_route_geometry", _explode)

        response = get_ride_route(ride_id=ride.id, db=db, current_user=rider)

        assert response is not None
        assert response.route_id == persisted.route_id
        assert response.problem == "pdp"
        assert [stop_row.waypoint_type for stop_row in response.stops] == [
            "depot",
            "pickup",
            "destination",
            "destination",
        ]
        assert [stop_row.is_mine for stop_row in response.stops] == [False, True, True, False]
        assert response.stops[1].passenger_count == 2
        assert response.my_pickup_sequence == 1
        assert response.my_destination_sequence == 2
        assert response.my_leg_indices == [1]
        assert len(response.legs) == 3
        assert response.legs[1].from_sequence == 1
        assert response.legs[1].to_sequence == 2
        assert len(response.legs[1].geometry) == 2

        with pytest.raises(HTTPException) as missing:
            get_ride_route(ride_id=10 ** 9, db=db, current_user=rider)
        assert missing.value.status_code == 404

        with pytest.raises(HTTPException) as denied:
            get_ride_route(ride_id=ride.id, db=db, current_user=stranger)
        assert denied.value.status_code == 403

        # A manual driver accept unlinks the virtual stop: no pool, no route.
        assert get_ride_route(ride_id=plain_ride.id, db=db, current_user=rider) is None
    finally:
        if created_ride_ids:
            db.query(RideRequest).filter(RideRequest.id.in_(created_ride_ids)).delete(
                synchronize_session=False
            )
        if created_plan_id is not None:
            db.query(RouteWaypointRecord).filter(
                RouteWaypointRecord.route_plan_id == created_plan_id
            ).delete(synchronize_session=False)
            db.query(RoutePlan).filter(RoutePlan.id == created_plan_id).delete(
                synchronize_session=False
            )
        if created_stop_ids:
            db.query(VirtualStop).filter(VirtualStop.id.in_(created_stop_ids)).delete(
                synchronize_session=False
            )
        db.commit()
        db.close()
