"""Deterministic component probes, not live Bengaluru road/provider tests."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from schemas.ride_request import RideRequestCreate
from services.carpool_lifecycle import run_is_open_to_riders
from services.routing import vrp_solver


@pytest.mark.parametrize("field,value", [
    ("pickup_lat", 91), ("pickup_lng", 181),
    ("dest_lat", -91), ("dest_lng", -181),
    ("pickup_lat", float("nan")), ("dest_lng", float("inf")),
])
def test_tc17_invalid_coordinates_are_rejected(field, value):
    data = dict(pickup_lat=13.0, pickup_lng=77.6, dest_lat=13.1, dest_lng=77.8)
    data[field] = value
    with pytest.raises(ValidationError):
        RideRequestCreate(**data)


def test_mid_run_insertion_is_explicitly_not_implemented():
    plan = SimpleNamespace(route_metadata={"driver_accepted": True})
    assert not run_is_open_to_riders(plan)


def _nodes():
    # Synthetic A -> B -> C -> D corridor, no named geographic claims.
    return [
        dict(lat=13, lng=77.60, kind="depot", demand=0),
        dict(lat=13, lng=77.60, kind="pickup", demand=2),
        dict(lat=13, lng=77.62, kind="destination", demand=1, pair_index=1),
        dict(lat=13, lng=77.61, kind="destination", demand=1, pair_index=1),
        dict(lat=13, lng=77.61, kind="pickup", demand=1),
        dict(lat=13, lng=77.63, kind="destination", demand=1, pair_index=4),
    ]


def test_tc32_segment_capacity_and_tc15_future_seat_reuse(monkeypatch):
    nodes = _nodes()
    monkeypatch.setattr(vrp_solver, "build_stadia_distance_matrix",
                        lambda points: vrp_solver.build_distance_matrix(points))
    result = vrp_solver.solve_shared_ride_pdp(nodes, 1, vehicle_capacity=2, time_limit_seconds=1)
    assert result["status"] == "solved"
    route = result["routes"][0]["stop_indices"]
    load = 0
    for index in route:
        node = nodes[index]
        if node["kind"] == "pickup":
            load += node["demand"]
        elif node["kind"] == "destination":
            assert route.index(node["pair_index"]) < route.index(index)
            load -= node["demand"]
        assert 0 <= load <= 2
    assert load == 0
    assert route.index(3) < route.index(4)


def test_tc07_solver_rejects_oversized_simultaneous_pickup(monkeypatch):
    nodes = _nodes()[:4]
    nodes[1]["demand"] = 3
    nodes[2]["demand"] = 2
    monkeypatch.setattr(vrp_solver, "build_stadia_distance_matrix",
                        lambda points: vrp_solver.build_distance_matrix(points))
    result = vrp_solver.solve_shared_ride_pdp(nodes, 1, vehicle_capacity=2, time_limit_seconds=1)
    assert result["status"] == "no_solution"


def test_tc22_routing_outage_must_not_solve_unverified_pool(monkeypatch):
    monkeypatch.setattr(vrp_solver, "build_stadia_distance_matrix", lambda points: None)
    monkeypatch.setattr(vrp_solver, "build_road_graph", lambda *args, **kwargs: None)
    result = vrp_solver.solve_shared_ride_pdp(_nodes(), 1, vehicle_capacity=2, time_limit_seconds=1)
    assert result == {"status": "routing_unavailable", "routes": [], "total_distance_m": 0}


@pytest.mark.parametrize("is_shared", [True, False])
def test_routing_outage_builds_no_passenger_route(monkeypatch, is_shared):
    from services.routing.shared_route_builder import build_shared_routes

    monkeypatch.setattr(vrp_solver, "build_stadia_distance_matrix", lambda points: None)
    monkeypatch.setattr(vrp_solver, "build_road_graph", lambda *args, **kwargs: None)
    requests = [SimpleNamespace(
        id=index, is_shared=is_shared, status="clustered", dest_lat=13, dest_lng=77.63,
    ) for index in (1, 2)]
    stops = [SimpleNamespace(id=1, lat=13, lng=77.60, ride_requests=requests)]
    routes = build_shared_routes(
        vehicles=[SimpleNamespace(id=1, capacity=3)], virtual_stops=stops,
        depot_lat=13, depot_lng=77.60, enrich=False,
    )
    assert routes == []


@pytest.mark.parametrize("target", ["arriving", "ready_for_pickup", "in_progress", "completed"])
@pytest.mark.parametrize("role", ["driver", "admin"])
def test_tc28_generic_patch_must_not_bypass_shared_lifecycle(target, role):
    from database import SessionLocal
    from routers.rides import update_ride_request_status
    from schemas.ride_request import RideRequestStatusUpdate
    from fastapi import HTTPException
    from test_carpool_lifecycle import _two_rider_route, _cleanup

    db = SessionLocal()
    persisted = None
    try:
        driver, _, _, vehicle, ride_a, ride_b, persisted = _two_rider_route(db)
        original_role, original_driver_status = driver.role, driver.driver_status
        vehicle.driver_user_id = driver.id
        driver.role = role
        driver.driver_status = "active"
        db.commit()
        original_status, original_stage = ride_a.status, ride_a.carpool_status
        with pytest.raises(HTTPException) as refused:
            update_ride_request_status(
                ride_id=ride_a.id, status_update=RideRequestStatusUpdate(status=target),
                db=db, current_user=driver,
            )
        assert refused.value.status_code == 409
        assert "carpool lifecycle" in refused.value.detail
        db.refresh(ride_a)
        db.refresh(persisted.route_plan)
        assert (ride_a.status, ride_a.carpool_status) == (original_status, original_stage)
        assert not persisted.route_plan.route_metadata["driver_accepted"]
    finally:
        if persisted is not None:
            driver.role = original_role
            driver.driver_status = original_driver_status
            db.commit()
            _cleanup(db, persisted, [ride_a.id, ride_b.id],
                     [ride_a.virtual_stop_id, ride_b.virtual_stop_id], vehicle.id)
        db.close()
