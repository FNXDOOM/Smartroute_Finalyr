"""Carpool matching rules (who may pool with whom, along which corridor); pure predicates, so they run without the scheduler."""

import math
from typing import List, Set, Tuple

from sqlalchemy.orm import Session

from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.vehicle import Vehicle
from models.virtual_stop import VirtualStop
from services import route_plan_meta
from services.carpool_lifecycle import run_is_open_to_riders
from services.notifications import create_notification
from services.routing.shared_route_builder import build_shared_routes, persist_shared_route
from utils.carpool_status import CARPOOL_CLUSTERED, set_carpool_stage
from utils.geo import haversine_meters as _haversine_meters
from utils.ride_scope import PRESENTATION_DEMO_MODE
from utils.ride_states import (
    RIDE_ARRIVING,
    RIDE_ASSIGNED,
    RIDE_BOUND_STATUSES,
    RIDE_CLUSTERED,
    ROUTE_SOLVED,
    ROUTE_SUPERSEDED,
    vehicle_is_dispatchable,
)

# Pickup clustering alone would pool far-apart destinations, so each pool also stays inside one corridor.
MAX_DESTINATION_SPREAD_METERS = 7000
MAX_CARPOOL_DETOUR_METERS = 5000
MAX_CARPOOL_DETOUR_RATIO = 1.45
MIN_CARPOOL_PASSENGERS = 2
MAX_CARPOOL_PASSENGERS = 3
MAX_PICKUP_WALK_METERS = 150


def point_to_segment_meters(
    lat: float,
    lng: float,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
) -> float:
    """Approximate distance from a coordinate to a coordinate segment."""
    scale = 111_000.0
    cos_lat = max(0.2, abs(math.cos(lat * math.pi / 180)))
    px, py = lng * scale * cos_lat, lat * scale
    ax, ay = start_lng * scale * cos_lat, start_lat * scale
    bx, by = end_lng * scale * cos_lat, end_lat * scale
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    nearest_x, nearest_y = ax + t * dx, ay + t * dy
    return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5


def pickup_corridor_distance_meters(request: RideRequest, other: RideRequest) -> float:
    """Return the nearer directional pickup-to-destination corridor distance."""
    request_to_other_route = point_to_segment_meters(
        request.pickup_lat,
        request.pickup_lng,
        other.pickup_lat,
        other.pickup_lng,
        other.dest_lat,
        other.dest_lng,
    )
    other_to_request_route = point_to_segment_meters(
        other.pickup_lat,
        other.pickup_lng,
        request.pickup_lat,
        request.pickup_lng,
        request.dest_lat,
        request.dest_lng,
    )
    return min(request_to_other_route, other_to_request_route)


def split_compatible_shared_group(requests: List[RideRequest]) -> List[List[RideRequest]]:
    """Split a pickup cluster into destination-compatible pools; HDBSCAN only sees pickup density."""
    groups: List[List[RideRequest]] = []
    for request in sorted(requests, key=lambda item: (item.request_time, item.id)):
        placed = False
        for group in groups:
            if len(group) >= MAX_CARPOOL_PASSENGERS:
                continue
            candidate_group = [*group, request]
            pickup_centre = (
                sum(item.pickup_lat for item in candidate_group) / len(candidate_group),
                sum(item.pickup_lng for item in candidate_group) / len(candidate_group),
            )
            destination_centre = (
                sum(item.dest_lat for item in candidate_group) / len(candidate_group),
                sum(item.dest_lng for item in candidate_group) / len(candidate_group),
            )
            destinations_close = all(
                _haversine_meters(
                    request.dest_lat,
                    request.dest_lng,
                    other.dest_lat,
                    other.dest_lng,
                ) <= MAX_DESTINATION_SPREAD_METERS
                for other in group
            )
            pickup_walk_ok = all(
                _haversine_meters(item.pickup_lat, item.pickup_lng, *pickup_centre)
                <= MAX_PICKUP_WALK_METERS
                for item in candidate_group
            )
            shared_distance = (
                _haversine_meters(request.pickup_lat, request.pickup_lng, *pickup_centre)
                + _haversine_meters(*pickup_centre, *destination_centre)
                + _haversine_meters(request.dest_lat, request.dest_lng, *destination_centre)
            )
            direct_distance = max(
                1.0,
                _haversine_meters(
                    request.pickup_lat,
                    request.pickup_lng,
                    request.dest_lat,
                    request.dest_lng,
                ),
            )
            detour_ok = (
                shared_distance - direct_distance <= MAX_CARPOOL_DETOUR_METERS
                and shared_distance / direct_distance <= MAX_CARPOOL_DETOUR_RATIO
            )
            if pickup_walk_ok and destinations_close and detour_ok:
                group.append(request)
                placed = True
                break
        if not placed:
            groups.append([request])
    return groups


def find_cross_cell_corridor_groups(
    requests: List[RideRequest],
) -> Tuple[List[List[RideRequest]], Set[int]]:
    """Corridor pass over riders H3 left out: H3 is a spatial pre-filter, not a carpool boundary, so nearby cells can still pool."""
    groups: List[List[RideRequest]] = []
    matched_ids: Set[int] = set()
    for request in sorted(requests, key=lambda item: (item.request_time, item.id)):
        if request.id in matched_ids:
            continue
        for group in groups:
            if len(group) >= MAX_CARPOOL_PASSENGERS:
                continue
            destinations_close = all(
                _haversine_meters(
                    request.dest_lat,
                    request.dest_lng,
                    other.dest_lat,
                    other.dest_lng,
                ) <= MAX_DESTINATION_SPREAD_METERS
                for other in group
            )
            corridor_ok = all(
                pickup_corridor_distance_meters(request, other) <= MAX_PICKUP_WALK_METERS
                for other in group
            )
            if destinations_close and corridor_ok:
                group.append(request)
                matched_ids.add(request.id)
                break
        else:
            groups.append([request])

    qualified_groups = [group for group in groups if len(group) >= MIN_CARPOOL_PASSENGERS]
    qualified_ids = {request.id for group in qualified_groups for request in group}
    return qualified_groups, qualified_ids


def attach_to_existing_run(
    db: Session,
    request: RideRequest,
    *,
    mode: str,
    demo_run_id: str | None,
) -> bool:
    """Insert a rider into an unstarted run, then rebuild it as a PDP so the driver gets a real itinerary, not an appended waypoint."""
    plans_query = db.query(RoutePlan).filter(
        RoutePlan.mode == mode,
        RoutePlan.status == ROUTE_SOLVED,
    )
    if mode == PRESENTATION_DEMO_MODE:
        plans_query = plans_query.filter(RoutePlan.demo_run_id == demo_run_id)

    for route_plan in plans_query.order_by(RoutePlan.created_at.desc()).all():
        if route_plan_meta.problem(route_plan) != "pdp":
            continue
        # Riders join only before driver acceptance; after that they wait for another route instead of rewriting a live itinerary.
        if not run_is_open_to_riders(route_plan):
            continue
        vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
        if not vehicle or not vehicle_is_dispatchable(vehicle.status):
            continue
        capacity = min(MAX_CARPOOL_PASSENGERS, max(1, int(vehicle.capacity or 1)))
        passenger_ids = sorted({
            passenger_id
            for waypoint in route_plan.waypoints or []
            for passenger_id in (waypoint.passenger_ids or [])
        })
        if len(passenger_ids) < MIN_CARPOOL_PASSENGERS or len(passenger_ids) >= capacity:
            continue

        active_requests = db.query(RideRequest).filter(
            RideRequest.id.in_(passenger_ids),
            RideRequest.status.in_(RIDE_BOUND_STATUSES),
        ).all()
        if len(active_requests) != len(passenger_ids):
            # A run that started or has stale ids must not be rewritten.
            continue

        pickup_waypoints = [
            waypoint for waypoint in route_plan.waypoints or []
            if waypoint.waypoint_type == "pickup" and waypoint.stop_id is not None
        ]
        if not pickup_waypoints:
            continue

        ordered_waypoints = sorted(route_plan.waypoints or [], key=lambda waypoint: waypoint.sequence)
        corridor_distance = min(
            point_to_segment_meters(
                request.pickup_lat,
                request.pickup_lng,
                start.lat,
                start.lng,
                end.lat,
                end.lng,
            )
            for start, end in zip(ordered_waypoints, ordered_waypoints[1:])
        )
        if corridor_distance > MAX_PICKUP_WALK_METERS:
            continue

        nearest_destination_meters = min(
            _haversine_meters(
                request.dest_lat,
                request.dest_lng,
                existing.dest_lat,
                existing.dest_lng,
            )
            for existing in active_requests
        )
        if nearest_destination_meters > MAX_DESTINATION_SPREAD_METERS:
            continue

        pickup_waypoint = min(
            pickup_waypoints,
            key=lambda waypoint: _haversine_meters(
                request.pickup_lat,
                request.pickup_lng,
                waypoint.lat,
                waypoint.lng,
            ),
        )
        existing_stop = db.query(VirtualStop).filter(VirtualStop.id == pickup_waypoint.stop_id).first()
        existing_walk_meters = (
            _haversine_meters(request.pickup_lat, request.pickup_lng, existing_stop.lat, existing_stop.lng)
            if existing_stop else float("inf")
        )
        new_stop = None
        if existing_stop and existing_walk_meters <= MAX_PICKUP_WALK_METERS:
            stop = existing_stop
            walk_meters = existing_walk_meters
        else:
            # On the corridor but not at an existing curb: give it a dedicated stop and let PDP place it.
            new_stop = VirtualStop(
                cluster_id=(db.query(VirtualStop.cluster_id).order_by(VirtualStop.cluster_id.desc()).first() or (0,))[0] + 1,
                mode=mode,
                demo_run_id=demo_run_id,
                h3_index=request.h3_index,
                lat=request.pickup_lat,
                lng=request.pickup_lng,
                snapped_node_id="route-insertion",
                passenger_count=0,
            )
            db.add(new_stop)
            db.flush()
            stop = new_stop
            walk_meters = 0.0

        active_stop_ids = {active.virtual_stop_id for active in active_requests if active.virtual_stop_id}
        active_stop_ids.add(stop.id)
        stops = db.query(VirtualStop).filter(VirtualStop.id.in_(active_stop_ids)).all()

        original_status = request.status
        original_carpool_status = request.carpool_status
        request.cluster_id = stop.cluster_id
        request.virtual_stop_id = stop.id
        set_carpool_stage(request, CARPOOL_CLUSTERED)
        stop.passenger_count = int(stop.passenger_count or 0) + 1

        rebuilt = build_shared_routes(
            vehicles=[vehicle],
            virtual_stops=stops,
            depot_lat=route_plan.depot_lat,
            depot_lng=route_plan.depot_lng,
            request_statuses=(RIDE_CLUSTERED, RIDE_ASSIGNED, RIDE_ARRIVING),
            enrich=True,
        )
        if not rebuilt or not rebuilt[0].ride_ids or request.id not in rebuilt[0].ride_ids:
            request.status = original_status
            request.carpool_status = original_carpool_status
            request.cluster_id = None
            request.virtual_stop_id = None
            if new_stop:
                db.delete(new_stop)
            else:
                stop.passenger_count = max(0, int(stop.passenger_count or 0) - 1)
            continue

        # Re-read after the slow rebuild: a driver who accepted meanwhile must not find their run superseded underneath them.
        db.refresh(route_plan)
        if not run_is_open_to_riders(route_plan):
            request.status = original_status
            request.carpool_status = original_carpool_status
            request.cluster_id = None
            request.virtual_stop_id = None
            if new_stop:
                db.delete(new_stop)
            else:
                stop.passenger_count = max(0, int(stop.passenger_count or 0) - 1)
            continue

        route_plan.status = ROUTE_SUPERSEDED
        persisted = persist_shared_route(
            db,
            rebuilt[0],
            vehicle=vehicle,
            mode=mode,
            created_by_user_id=None,
            source_cluster_run_id=route_plan.source_cluster_run_id,
            demo_run_id=demo_run_id,
            assign_statuses=(RIDE_CLUSTERED, RIDE_ASSIGNED, RIDE_ARRIVING),
        )
        create_notification(
            db,
            user_id=request.user_id,
            notification_type="route_assigned",
            title="You joined a carpool route",
            message=f"Walk about {round(walk_meters)} m to the shared pickup stop.",
            related_entity_type="route_plan",
            related_entity_id=persisted.route_plan.id,
            metadata={
                "route_id": persisted.route_id,
                "vehicle_id": vehicle.id,
                "walk_meters": round(walk_meters, 1),
            },
        )
        return True

    return False
