"""Carpool matching rules (who may pool with whom, along which corridor); pure predicates, so they run without the scheduler."""

import math
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from itertools import combinations, permutations
from typing import List, Set, Tuple

from sqlalchemy.orm import Session

from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.vehicle import Vehicle
from models.virtual_stop import VirtualStop
from services import route_plan_meta
from services.stadia_client import matrix, route
from services.carpool_lifecycle import run_is_open_to_riders
from services.notifications import create_notification
from services.routing.shared_route_builder import build_shared_routes, persist_shared_route
from utils.carpool_status import CARPOOL_CLUSTERED, set_carpool_stage
from utils.carpool_policy import (
    MAX_CARPOOL_DETOUR_METERS,
    MAX_CARPOOL_DETOUR_RATIO, MIN_CARPOOL_PASSENGERS,
    MAX_CARPOOL_PASSENGERS, MAX_PICKUP_WALK_METERS,
)
from utils.geo import haversine_meters as _haversine_meters
from utils.ride_scope import PRESENTATION_DEMO_MODE
from utils.ride_states import (
    RIDE_ARRIVING,
    RIDE_ASSIGNED,
    RIDE_BOUND_STATUSES,
    RIDE_CLUSTERED,
    RIDE_PENDING,
    ROUTE_SOLVED,
    ROUTE_SUPERSEDED,
    vehicle_is_dispatchable,
)

logger = logging.getLogger(__name__)
_matching_batch = ContextVar("road_matching_batch", default=None)


@contextmanager
def road_matching_batch():
    """One tick's directed-distance cache and diagnostics; never shared across DB threads."""
    current = _matching_batch.get()
    if current is not None:
        yield current["stats"]
        return
    state = {
        "edges": {}, "failed_edges": set(), "matrix_unavailable": False, "decisions": {},
        "stats": {"routing_failures": 0, "matrix_attempts": 0, "route_attempts": 0},
    }
    token = _matching_batch.set(state)
    try:
        yield state["stats"]
    finally:
        _matching_batch.reset(token)


def road_matching_diagnostics():
    state = _matching_batch.get()
    return dict(state["stats"]) if state else {}


def _route_edge(key):
    data = route(*key, costing="auto")
    if not isinstance(data, dict) or not isinstance(data.get("trip"), dict):
        raise ValueError("Invalid road route")
    trip = data["trip"]
    if trip.get("status", 0) != 0 or trip.get("units") != "kilometers":
        raise ValueError("Invalid road route")
    distance = float(trip["summary"]["length"]) * 1000
    if not math.isfinite(distance) or distance < 0:
        raise ValueError("Invalid road distance")
    return distance


def _road_distances(points):
    """Matrix first, then at most four concurrent road requests; reuse directed edges."""
    if _matching_batch.get() is None:
        with road_matching_batch():
            return _road_distances(points)
    state = _matching_batch.get()
    cache, stats = state["edges"], state["stats"]
    keys = [[(a["lat"], a["lon"], b["lat"], b["lon"]) for b in points] for a in points]
    for row in keys:
        for key in row:
            if key[:2] == key[2:]:
                cache[key] = 0.0
    missing = {key for row in keys for key in row if key not in cache}
    try:
        if missing & state["failed_edges"]:
            raise RuntimeError("Road edges unavailable in this batch")
        if missing and not state["matrix_unavailable"]:
            try:
                stats["matrix_attempts"] += 1
                data = matrix(points, points, costing="auto")
                if not isinstance(data, dict):
                    raise ValueError("Invalid matrix response")
                if data.get("units", "kilometers") != "kilometers":
                    raise ValueError("Invalid matrix units")
                rows = data["sources_to_targets"]
                if not isinstance(rows, list) or len(rows) != len(points) or any(
                    not isinstance(row, list) or len(row) != len(points) for row in rows
                ):
                    raise ValueError("Invalid matrix dimensions")
                parsed = [[float(cell["distance"]) * 1000 for cell in row] for row in rows]
                if any(not math.isfinite(d) or d < 0 for row in parsed for d in row):
                    raise ValueError("Invalid matrix distances")
                for row_keys, row in zip(keys, parsed):
                    cache.update(zip(row_keys, row))
                missing = set()
            except (RuntimeError, KeyError, TypeError, ValueError, IndexError) as exc:
                state["matrix_unavailable"] = True
                if isinstance(exc, RuntimeError) and "not configured" in str(exc):
                    state["failed_edges"].update(missing)
                    raise
                logger.warning("Carpool matrix unavailable; trying standard road routes")
        if missing:
            ordered = sorted(missing)
            stats["route_attempts"] += len(ordered)
            with ThreadPoolExecutor(max_workers=4) as workers:
                futures = {key: workers.submit(_route_edge, key) for key in ordered}
                for key, future in futures.items():
                    try:
                        cache[key] = future.result()
                    except (RuntimeError, KeyError, TypeError, ValueError, IndexError):
                        state["failed_edges"].add(key)
                if any(key not in cache for key in ordered):
                    raise RuntimeError("Road edges unavailable")
    except (RuntimeError, KeyError, TypeError, ValueError, IndexError):
        stats["routing_failures"] += 1
        raise RuntimeError(
            "Carpool road-distance services unavailable; matching could not be evaluated"
        ) from None
    return [[cache[key] for key in row] for row in keys]


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
    """HDBSCAN supplies candidates, not a different compatibility policy."""
    return _compatible_groups(requests)


def road_detour_compatible(requests: List[RideRequest]) -> bool:
    """Require a feasible road itinerary within every rider's detour budget.

    Pickups remain individual stops; the pedestrian walking limit is not a
    vehicle corridor width. Routing failures propagate rather than reject riders.
    """
    count = len(requests)
    if not MIN_CARPOOL_PASSENGERS <= count <= MAX_CARPOOL_PASSENGERS:
        return False
    if any(getattr(item, "is_shared", True) is False for item in requests):
        return False
    # Identical trips have zero additional detour regardless of road shape.
    # Dispatch still independently verifies road reachability before assignment.
    if len({(r.pickup_lat, r.pickup_lng, r.dest_lat, r.dest_lng) for r in requests}) == 1:
        return True
    points = [
        {"lat": item.pickup_lat, "lon": item.pickup_lng} for item in requests
    ] + [
        {"lat": item.dest_lat, "lon": item.dest_lng} for item in requests
    ]
    try:
        distances = _road_distances(points)
        if len(distances) != count * 2 or any(len(row) != count * 2 for row in distances):
            return False
        direct = [distances[i][count + i] for i in range(count)]
        if any(not math.isfinite(value) or value < 0 for value in direct):
            return False
        # At most three riders => only 720 orders. Permit interleaved drop-offs,
        # but require every rider to actually share a segment with someone else.
        for order in permutations(range(count * 2)):
            positions = {stop: index for index, stop in enumerate(order)}
            if any(positions[i] >= positions[count + i] for i in range(count)):
                continue
            if not all(any(
                i != j and max(positions[i], positions[j])
                < min(positions[count + i], positions[count + j])
                for j in range(count)
            ) for i in range(count)):
                continue
            travelled = [0.0]
            for start, end in zip(order, order[1:]):
                travelled.append(travelled[-1] + distances[start][end])
            if not math.isfinite(travelled[-1]):
                continue
            if not all(any(
                i != j and travelled[min(positions[count + i], positions[count + j])]
                - travelled[max(positions[i], positions[j])] > 1.0
                for j in range(count)
            ) for i in range(count)):
                # Boarding at another rider's exact drop-off is not shared travel.
                continue
            if all(
                (shared := travelled[positions[count + i]] - travelled[positions[i]])
                <= direct[i] + MAX_CARPOOL_DETOUR_METERS
                and shared <= max(1.0, direct[i]) * MAX_CARPOOL_DETOUR_RATIO
                for i in range(count)
            ):
                return True
    except (KeyError, TypeError, ValueError, IndexError):
        raise RuntimeError("Invalid carpool road-distance data") from None
    return False


def find_cross_cell_corridor_groups(
    requests: List[RideRequest],
) -> Tuple[List[List[RideRequest]], Set[int]]:
    """Corridor pass over riders H3 left out: H3 is a spatial pre-filter, not a carpool boundary, so nearby cells can still pool."""
    groups = _compatible_groups(requests)
    qualified_groups = [group for group in groups if len(group) >= MIN_CARPOOL_PASSENGERS]
    qualified_ids = {request.id for group in qualified_groups for request in group}
    return qualified_groups, qualified_ids


def _compatible_groups(requests):
    if _matching_batch.get() is None:
        with road_matching_batch():
            return _compatible_groups(requests)

    decisions = _matching_batch.get()["decisions"]

    def compatible(group):
        if len(group) > MAX_CARPOOL_PASSENGERS:
            return False
        # Destination separation does not measure detour. A rider can exit early
        # while another continues far along the same road without delaying either.
        key = tuple(sorted((r.id, r.pickup_lat, r.pickup_lng, r.dest_lat, r.dest_lng) for r in group))
        if key in decisions:
            return decisions[key]
        try:
            decisions[key] = road_detour_compatible(group)
            return decisions[key]
        except RuntimeError:
            # Keep unrelated good pools; the caller records incomplete evaluation.
            logger.warning("Carpool road matching unavailable; skipping corridor pool this tick")
            return False

    groups = []
    seen = set()
    for request in sorted(requests, key=lambda item: (item.request_time, item.id)):
        if request.id in seen or getattr(request, "is_shared", True) is False:
            continue
        seen.add(request.id)
        for group in groups:
            if compatible([*group, request]):
                group.append(request)
                break
        else:
            groups.append([request])

    # 3 + 1 is avoidable starvation when both replacement pairs are feasible.
    # Recheck both pairs; never relax detour or destination limits to fill seats.
    for singleton in groups:
        if len(singleton) != 1:
            continue
        for donor in groups:
            if len(donor) != MAX_CARPOOL_PASSENGERS:
                continue
            for member in reversed(donor):
                remaining = [item for item in donor if item.id != member.id]
                if compatible([*singleton, member]) and compatible(remaining):
                    donor.remove(member)
                    singleton.append(member)
                    break
            if len(singleton) > 1:
                break
    # Recover a greedy A-B match when A-C and B-D would serve all four.
    # Try at most the remaining singletons and verified pairs, never triples.
    singletons = [group for group in groups if len(group) == 1]
    pairs = [group for group in groups if len(group) == 2]
    repair_budget = 12
    for left, right in combinations(singletons, 2):
        if not pairs or repair_budget <= 0:
            break
        if len(left) != 1 or len(right) != 1:
            continue
        for pair in pairs:
            if repair_budget <= 0:
                break
            repair_budget -= 1
            a, b = pair
            for first, second in ((a, b), (b, a)):
                if compatible([left[0], first]) and compatible([right[0], second]):
                    left.append(first)
                    right.append(second)
                    groups.remove(pair)
                    pairs.remove(pair)
                    break
            if len(left) == 2:
                break
    return groups


def attach_to_existing_run(
    db: Session,
    request: RideRequest,
    *,
    mode: str,
    demo_run_id: str | None,
) -> bool:
    """Insert a rider into an unstarted run, then rebuild it as a PDP so the driver gets a real itinerary, not an appended waypoint."""
    if not request.is_shared or request.status != RIDE_PENDING:
        return False
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
        if any(not item.is_shared for item in active_requests):
            continue

        pickup_waypoints = [
            waypoint for waypoint in route_plan.waypoints or []
            if waypoint.waypoint_type == "pickup" and waypoint.stop_id is not None
        ]
        if not pickup_waypoints:
            continue

        try:
            if not road_detour_compatible([*active_requests, request]):
                continue
        except RuntimeError:
            logger.warning("Carpool insertion road matching unavailable; retrying next tick")
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
        # autoflush is disabled: assigning only the FK leaves the builder's
        # stop.ride_requests collection unaware of this candidate.
        stop.ride_requests.append(request)
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
        required_ids = {item.id for item in active_requests} | {request.id}
        if not rebuilt or not required_ids.issubset(set(rebuilt[0].ride_ids)):
            request.status = original_status
            request.carpool_status = original_carpool_status
            request.cluster_id = None
            request.virtual_stop_id = None
            request.virtual_stop = None
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
            request.virtual_stop = None
            if new_stop:
                db.delete(new_stop)
            else:
                stop.passenger_count = max(0, int(stop.passenger_count or 0) - 1)
            continue

        # Claim the source plan atomically, not merely by re-reading it. Two
        # solvers may both have read the last seat before either commits.
        claimed = db.query(RoutePlan).filter(
            RoutePlan.id == route_plan.id,
            RoutePlan.status == ROUTE_SOLVED,
            RoutePlan.route_metadata["driver_accepted"].as_boolean().is_not(True),
        ).update({RoutePlan.status: ROUTE_SUPERSEDED}, synchronize_session=False)
        if not claimed:
            request.status = original_status
            request.carpool_status = original_carpool_status
            request.cluster_id = None
            request.virtual_stop_id = None
            request.virtual_stop = None
            if new_stop:
                db.delete(new_stop)
            else:
                # Discard our speculative increment without overwriting the
                # winner's newly committed passenger count.
                db.refresh(stop, attribute_names=["passenger_count"])
            continue
        db.refresh(route_plan)
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
