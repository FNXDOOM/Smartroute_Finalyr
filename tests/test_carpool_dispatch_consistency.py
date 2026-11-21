"""Exercise the same roster decisions worker, driver and passenger depend on."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from database import SessionLocal
from models.ride_request import RideRequest
from routers.rides import get_ride_vehicle, list_ride_requests
from routers.route import accept_route, list_routes
from services import carpool_matching
from services.routing import shared_route_builder as builder
from test_carpool_lifecycle import _cleanup, _two_rider_route


@pytest.mark.parametrize("pool_count", [1, 2, 4, 12])
@pytest.mark.parametrize("vehicle_count", [1, 2, 5])
@pytest.mark.parametrize("riders_per_pool", [2, 3])
def test_dispatch_keeps_prechecked_pools_intact_without_global_solver(
    monkeypatch, mock_road_matrix, pool_count, vehicle_count, riders_per_pool
):
    def unexpected(*args, **kwargs):
        pytest.fail("Automatic dispatch must not run a fleet-wide solver")

    monkeypatch.setattr(builder, "solve_shared_ride_pdp", unexpected)
    stops = []
    for pool in range(pool_count):
        for member in range(riders_per_pool):
            # All endpoints are similar enough that a global solver could mix clusters.
            ride_id = (pool_count - pool) * 10 + member
            stops.append(SimpleNamespace(
                id=len(stops) + 1, cluster_id=pool + 1, lat=13, lng=77.60,
                ride_requests=[SimpleNamespace(
                    id=ride_id, is_shared=True, status="clustered", dest_lat=13, dest_lng=77.64,
                )],
            ))
    routes = builder.build_dispatch_routes(
        vehicles=[SimpleNamespace(capacity=3) for _ in range(vehicle_count)],
        virtual_stops=stops[::-1], depot_lat=13, depot_lng=77.60,
        request_statuses=("clustered",),
    )
    assert len(routes) == min(pool_count, vehicle_count)
    assert len({route.vehicle_index for route in routes}) == len(routes)
    for route in routes:
        assert len(route.ride_ids) == riders_per_pool
        assert len({ride_id // 10 for ride_id in route.ride_ids}) == 1
        assert route.geometry == []  # Geometry is fetched only when displayed.


@pytest.mark.parametrize("mode", ["unroutable", "singleton", "over_capacity"])
def test_bad_pool_does_not_block_later_valid_pool(monkeypatch, mode):
    from services.routing import vrp_solver

    def matrix(points):
        if any(p["lat"] == 14 for p in points):
            return None
        return vrp_solver.build_distance_matrix(points)

    monkeypatch.setattr(vrp_solver, "build_stadia_distance_matrix", matrix)
    monkeypatch.setattr(vrp_solver, "build_road_distance_matrix", lambda _: None)
    bad_count = {"unroutable": 2, "singleton": 1, "over_capacity": 4}[mode]
    stops = [SimpleNamespace(
        id=i, cluster_id=1 if i <= bad_count else 2,
        lat=14 if i <= bad_count else 13, lng=77.60,
        ride_requests=[SimpleNamespace(id=i, is_shared=True, status="clustered", dest_lat=13, dest_lng=77.64)],
    ) for i in range(1, bad_count + 3)]
    routes = builder.build_dispatch_routes(
        vehicles=[SimpleNamespace(capacity=3)], virtual_stops=stops,
        depot_lat=13, depot_lng=77.60, request_statuses=("clustered",),
    )
    assert [route.ride_ids for route in routes] == [[bad_count + 1, bad_count + 2]]


def test_greedy_pair_is_repaired_when_two_pairs_serve_everyone(monkeypatch):
    rides = [SimpleNamespace(
        id=i, request_time=datetime(2026, 1, 1, tzinfo=timezone.utc), is_shared=True,
        pickup_lat=13, pickup_lng=77.60, dest_lat=13, dest_lng=77.64,
    ) for i in range(1, 5)]
    allowed = {frozenset(pair) for pair in [(1, 2), (1, 3), (2, 4)]}
    monkeypatch.setattr(carpool_matching, "road_detour_compatible",
                        lambda group: frozenset(ride.id for ride in group) in allowed)
    groups, ids = carpool_matching.find_cross_cell_corridor_groups(rides)
    assert {frozenset(ride.id for ride in group) for group in groups} == allowed - {frozenset({1, 2})}
    assert ids == {1, 2, 3, 4}


@pytest.mark.parametrize("status,reserved,visible", [
    ("solved", True, True), ("needs_reoptimization", True, True),
    ("solved", False, False), ("needs_reoptimization", False, False),
    ("cancelled", True, False), ("completed", True, False), ("superseded", True, False),
])
def test_driver_and_passenger_agree_on_current_carpool(status, reserved, visible):
    with SessionLocal() as db:
        driver, rider_a, _, vehicle, a, b, persisted = _two_rider_route(db)
        extra = RideRequest(
            user_id=rider_a.id, pickup_lat=a.pickup_lat, pickup_lng=a.pickup_lng,
            dest_lat=a.dest_lat, dest_lng=a.dest_lng, status="pending", is_shared=True,
        )
        db.add(extra)
        actor = SimpleNamespace(id=driver.id, role="driver", driver_status="active")
        vehicle.driver_user_id = actor.id
        vehicle.assigned_route_id = persisted.route_id if reserved else None
        persisted.route_plan.status = status
        db.commit()
        try:
            listed = list_ride_requests(
                db=db, current_user=actor, ride_status=None, mode="live",
                demo_run_id=None, h3_index=None, limit=50, offset=0,
            )
            assert extra.id not in {ride.id for ride in listed}
            assert (a.id in {ride.id for ride in listed}) == visible
            assert any(route.route_id == persisted.route_id for route in list_routes(20, db, actor).routes) == visible
            assert (get_ride_vehicle(a.id, db, rider_a) is not None) == visible
            if status in ("solved", "needs_reoptimization") and not reserved:
                with pytest.raises(HTTPException) as error:
                    accept_route(persisted.route_id, db, actor)
                assert error.value.status_code == 409
        finally:
            _cleanup(db, persisted, [a.id, b.id, extra.id], [a.virtual_stop_id, b.virtual_stop_id], vehicle.id)


def test_matrix_denial_cools_down_across_ticks_but_can_recover(monkeypatch):
    from services import stadia_client

    current = [100]
    calls = []
    monkeypatch.setattr(stadia_client.time, "monotonic", lambda: current[0])
    monkeypatch.setattr(stadia_client, "_matrix_denied_until", 0)
    monkeypatch.setattr(stadia_client, "STADIA_CACHE_ENABLED", False)

    def upstream(url, *, body):
        calls.append(url)
        if len(calls) == 1:
            raise stadia_client.StadiaHTTPError(403)
        return {"sources_to_targets": []}

    monkeypatch.setattr(stadia_client, "_request_json", upstream)
    for offset in (0, 5, 55):
        current[0] = 100 + offset
        with pytest.raises(stadia_client.StadiaHTTPError):
            stadia_client.matrix([], [])
        assert len(calls) == 1
    current[0] = 160
    assert stadia_client.matrix([], []) == {"sources_to_targets": []}
    assert len(calls) == 2


@pytest.mark.parametrize("capacity,stops,expected", [
    (1, [(0, 4), (0, 4)], False),     # No second seat.
    (2, [(0, 4), (0, 4), (0, 4)], False),  # All three need seats simultaneously.
    (3, [(0, 4), (0, 4), (0, 4)], True),
    (2, [(0, 4), (3, 8), (7, 10)], True),  # Sequential pickups reuse a seat.
    (2, [(0, 2), (2, 0)], False),   # A zero-length overlap isn't a shared ride.
    (2, [(0, 2), (4, 6)], False),   # Separate trips cannot be served as one pool.
])
def test_exact_dispatch_rechecks_seats_and_real_shared_travel(mock_road_matrix, capacity, stops, expected):
    virtual_stops = [SimpleNamespace(
        id=i, cluster_id=1, lat=13, lng=77 + pickup / 110,
        ride_requests=[SimpleNamespace(
            id=i, is_shared=True, status="clustered", dest_lat=13, dest_lng=77 + dropoff / 110,
        )],
    ) for i, (pickup, dropoff) in enumerate(stops, 1)]
    routes = builder.build_dispatch_routes(
        vehicles=[SimpleNamespace(capacity=capacity)], virtual_stops=virtual_stops,
        depot_lat=13, depot_lng=77, request_statuses=("clustered",),
    )
    assert bool(routes) == expected


@pytest.mark.parametrize("new_partner", [False, True])
def test_orphaned_clustered_rider_can_search_again(new_partner):
    from routers.rides import cancel_ride_request
    from services.background_jobs import run_cluster_job

    with SessionLocal() as db:
        _, rider_a, rider_b, vehicle, a, b, persisted = _two_rider_route(db)
        original_stops = [a.virtual_stop_id, b.virtual_stop_id]
        cancel_ride_request(b.id, db, rider_b)
        persisted.route_plan.status = "cancelled"
        vehicle.assigned_route_id = None
        rides = [a, b]
        if new_partner:
            partner = RideRequest(
                user_id=rider_a.id, is_shared=True, status="pending",
                pickup_lat=a.pickup_lat, pickup_lng=a.pickup_lng, dest_lat=a.dest_lat, dest_lng=a.dest_lng,
            )
            db.add(partner)
            rides.append(partner)
        db.commit()
        try:
            result = run_cluster_job(db, is_scheduled=False)
            db.refresh(a)
            assert result["requeued_singleton_rides"] == 1
            if new_partner:
                db.refresh(partner)
                assert a.status == partner.status == "clustered"
                assert a.cluster_id == partner.cluster_id
                assert a.virtual_stop_id != original_stops[0]
            else:
                assert a.status == "pending"
                assert a.carpool_status == "searching"
                assert a.virtual_stop_id is None
        finally:
            stops = set(original_stops) | {ride.virtual_stop_id for ride in rides if ride.virtual_stop_id}
            _cleanup(db, persisted, [ride.id for ride in rides], stops, vehicle.id)
