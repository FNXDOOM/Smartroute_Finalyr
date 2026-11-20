"""Existing pre-acceptance allocation only; no live dynamic-insertion claims."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local

import pytest

from database import SessionLocal
from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from services import carpool_matching
from services.routing.shared_route_builder import BuiltRoute
from test_carpool_lifecycle import _two_rider_route, _cleanup


@pytest.fixture
def open_run(mock_carpool_roads):
    db = SessionLocal()
    driver, rider_a, rider_b, vehicle, ride_a, ride_b, persisted = _two_rider_route(db)
    stop_ids = [ride_a.virtual_stop_id, ride_b.virtual_stop_id]
    candidates = [
        RideRequest(
            user_id=rider_b.id, pickup_lat=ride_a.pickup_lat, pickup_lng=ride_a.pickup_lng,
            dest_lat=ride_a.dest_lat, dest_lng=ride_a.dest_lng,
            status="pending", carpool_status="pending", is_shared=True,
        )
        for _ in range(2)
    ]
    vehicle.capacity = 3
    db.add_all(candidates)
    db.commit()
    candidate_ids = [ride.id for ride in candidates]
    try:
        yield persisted.route_plan.id, vehicle.id, candidate_ids
    finally:
        stop_ids.extend(
            ride.virtual_stop_id for ride in db.query(RideRequest).filter(RideRequest.id.in_(candidate_ids))
            if ride.virtual_stop_id and ride.virtual_stop_id not in stop_ids
        )
        # Include replacement plans owned by this fixture's vehicle.
        from models.route_waypoint import RouteWaypointRecord
        plans = db.query(RoutePlan).filter(RoutePlan.vehicle_id == vehicle.id).all()
        for plan in plans:
            if plan.id != persisted.route_plan.id:
                db.query(RouteWaypointRecord).filter(
                    RouteWaypointRecord.route_plan_id == plan.id,
                ).delete(synchronize_session=False)
                db.delete(plan)
        db.commit()
        _cleanup(db, persisted, [ride_a.id, ride_b.id, *candidate_ids], stop_ids, vehicle.id)
        db.close()


@pytest.mark.parametrize("reason", ["accepted", "full", "private", "opposite"])
def test_late_rider_must_not_join_unavailable_or_incompatible_run(open_run, reason):
    from models.vehicle import Vehicle
    plan_id, vehicle_id, candidate_ids = open_run
    with SessionLocal() as db:
        plan, vehicle = db.get(RoutePlan, plan_id), db.get(Vehicle, vehicle_id)
        request = db.get(RideRequest, candidate_ids[0])
        if reason == "accepted":
            plan.route_metadata = {**plan.route_metadata, "driver_accepted": True}
        elif reason == "full":
            vehicle.capacity = 2
        elif reason == "private":
            request.is_shared = False
        else:
            request.pickup_lat, request.dest_lat = request.dest_lat, request.pickup_lat
            request.pickup_lng, request.dest_lng = request.dest_lng, request.pickup_lng
            # Continue beyond the original pickup: unlike a tiny reversal, this
            # cannot be inserted within every passenger's 45% detour budget.
            request.dest_lng += .03
        db.commit()
        assert not carpool_matching.attach_to_existing_run(db, request, mode="live", demo_run_id=None)
        assert request.status == "pending"
        assert request.virtual_stop_id is None


def test_curved_road_candidate_not_rejected_by_150m_straight_line(open_run, mock_road_matrix):
    _, _, candidate_ids = open_run
    with SessionLocal() as db:
        request = db.get(RideRequest, candidate_ids[0])
        request.pickup_lat, request.pickup_lng = 12.9800, 77.6330
        db.commit()
        assert carpool_matching.attach_to_existing_run(db, request, mode="live", demo_run_id=None)
        db.commit()
        assert request.status == "assigned"


def test_compatible_rider_can_take_last_seat_before_acceptance(open_run, mock_road_matrix):
    _, _, candidate_ids = open_run
    with SessionLocal() as db:
        request = db.get(RideRequest, candidate_ids[0])
        attached = carpool_matching.attach_to_existing_run(db, request, mode="live", demo_run_id=None)
        db.commit()
        assert attached
        db.refresh(request)
        assert request.status == "assigned"


@pytest.mark.parametrize("iteration", range(5))
@pytest.mark.parametrize("duplicate", [False, True])
def test_simultaneous_last_seat_requests_have_exactly_one_winner(open_run, monkeypatch, iteration, duplicate):
    plan_id, vehicle_id, candidate_ids = open_run
    barrier = Barrier(2, timeout=15)
    context = local()

    def synchronized_route_builder(**kwargs):
        # Deterministic routing mock: both workers reach the same decision
        # boundary after reading the old plan, before either commits a booking.
        db, request_id = context.db, context.request_id
        old_plan = db.get(RoutePlan, plan_id)
        waypoints = [{
            "stop_id": waypoint.stop_id, "lat": waypoint.lat, "lng": waypoint.lng,
            "waypoint_type": waypoint.waypoint_type, "passenger_ids": list(waypoint.passenger_ids),
        } for waypoint in old_plan.waypoints]
        pickup = next(waypoint for waypoint in waypoints if waypoint["waypoint_type"] == "pickup")
        pickup["passenger_ids"].append(request_id)
        waypoints.append({
            "stop_id": None, "lat": 12.9756, "lng": 77.6066,
            "waypoint_type": "destination", "passenger_ids": [request_id],
        })
        ride_ids = sorted({ride_id for waypoint in waypoints for ride_id in waypoint["passenger_ids"]})
        barrier.wait()
        return [BuiltRoute(
            vehicle_index=0, depot_lat=old_plan.depot_lat, depot_lng=old_plan.depot_lng,
            waypoints=waypoints, ride_ids=ride_ids, destination_ride_ids=ride_ids,
            stop_ids=sorted({waypoint["stop_id"] for waypoint in waypoints if waypoint["stop_id"]}),
            distance_m=4200, duration_s=480,
        )]

    monkeypatch.setattr(carpool_matching, "build_shared_routes", synchronized_route_builder)

    def book(request_id):
        with SessionLocal() as db:
            context.db, context.request_id = db, request_id
            request = db.get(RideRequest, request_id)
            attached = carpool_matching.attach_to_existing_run(db, request, mode="live", demo_run_id=None)
            db.commit()
            return attached

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(book, [candidate_ids[0]] * 2 if duplicate else candidate_ids))
    assert sorted(results) == [False, True]
    with SessionLocal() as db:
        live_plans = db.query(RoutePlan).filter(
            RoutePlan.vehicle_id == vehicle_id, RoutePlan.status == "solved",
        ).all()
        assert len(live_plans) == 1
        roster = {ride_id for waypoint in live_plans[0].waypoints for ride_id in waypoint.passenger_ids}
        assert len(roster) == 3
        assigned = db.query(RideRequest).filter(
            RideRequest.id.in_(candidate_ids), RideRequest.status == "assigned",
        ).all()
        assert len(assigned) == 1
        from models.virtual_stop import VirtualStop
        for waypoint in live_plans[0].waypoints:
            if waypoint.waypoint_type == "pickup":
                assert db.get(VirtualStop, waypoint.stop_id).passenger_count == len(waypoint.passenger_ids)


def test_retry_of_allocated_request_does_not_reserve_again(open_run, mock_road_matrix):
    _, vehicle_id, candidate_ids = open_run
    with SessionLocal() as db:
        request = db.get(RideRequest, candidate_ids[0])
        assert carpool_matching.attach_to_existing_run(db, request, mode="live", demo_run_id=None)
        db.commit()
        original_stop_id = request.virtual_stop_id
        assert not carpool_matching.attach_to_existing_run(db, request, mode="live", demo_run_id=None)
        db.commit()
        db.refresh(request)
        assert request.status == "assigned"
        assert request.virtual_stop_id == original_stop_id
        assert db.query(RoutePlan).filter(
            RoutePlan.vehicle_id == vehicle_id, RoutePlan.status == "solved",
        ).count() == 1


def test_failed_confirmation_rolls_back_plan_claim_and_reservation(open_run, mock_road_matrix, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    plan_id, vehicle_id, candidate_ids = open_run

    def fail_persistence(db, *args, **kwargs):
        # Trigger an actual database constraint failure after the source-plan
        # claim, not just a Python exception standing in for a database error.
        db.execute(text(
            "INSERT INTO route_plans (route_id, vehicle_id, depot_lat, depot_lng) "
            "VALUES (NULL, :vehicle_id, 0, 0)"
        ), {"vehicle_id": vehicle_id})

    monkeypatch.setattr(carpool_matching, "persist_shared_route", fail_persistence)
    with SessionLocal() as db:
        request = db.get(RideRequest, candidate_ids[0])
        with pytest.raises(IntegrityError):
            carpool_matching.attach_to_existing_run(db, request, mode="live", demo_run_id=None)
        db.rollback()
    with SessionLocal() as db:
        request = db.get(RideRequest, candidate_ids[0])
        assert request.status == "pending"
        assert request.virtual_stop_id is None
        assert db.get(RoutePlan, plan_id).status == "solved"
        assert db.query(RoutePlan).filter(RoutePlan.vehicle_id == vehicle_id).count() == 1
