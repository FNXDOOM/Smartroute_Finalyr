"""Pooled shared-ride routing: one pickup+destination route per vehicle, owned by the optimize endpoint and the dispatch job so they can't drift."""

from dataclasses import dataclass, field
from itertools import permutations
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from config import STADIA_API_KEY
from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.route_waypoint import RouteWaypointRecord
from models.vehicle import Vehicle
from services import route_plan_meta
from services.routing import vrp_solver
from services.routing.vrp_solver import solve_shared_ride_pdp
from services.stadia_client import extract_route_details, route_many
from utils.carpool_status import CARPOOL_ASSIGNED, set_carpool_stage
from utils.carpool_policy import (
    MIN_CARPOOL_PASSENGERS, MAX_CARPOOL_PASSENGERS,
    MAX_CARPOOL_DETOUR_METERS, MAX_CARPOOL_DETOUR_RATIO,
)
from utils.geo import haversine_meters
from utils.ride_scope import LIVE_MODE
from utils.ride_states import RIDE_ASSIGNED, ROUTE_SOLVED, VEHICLE_ACTIVE


# Valhalla caps locations per request, so long routes are enriched in overlapping windows (one leg per consecutive pair).
ROUTE_LOCATION_WINDOW = 24
# Bound the upstream work one lazy resolution may trigger.
MAX_ENRICHMENT_CHUNKS = 6
# ~30 km/h, used when the router returns no duration.
FALLBACK_METRES_PER_SECOND = 8.33


@dataclass
class BuiltRoute:
    """A solved pooled route, ready to persist or to enrich on demand."""

    vehicle_index: int
    depot_lat: float
    depot_lng: float
    waypoints: List[Dict] = field(default_factory=list)
    ride_ids: List[int] = field(default_factory=list)
    destination_ride_ids: List[int] = field(default_factory=list)
    stop_ids: List[int] = field(default_factory=list)
    distance_m: float = 0.0
    duration_s: float = 0.0
    geometry: List[List[float]] = field(default_factory=list)
    legs: List[Dict] = field(default_factory=list)
    maneuvers: List[Dict] = field(default_factory=list)
    provider: str = "local-road-matrix"
    problem: str = "pdp"


@dataclass
class PersistedRoute:
    """What a caller needs to notify passengers after persisting a route."""

    route_plan: RoutePlan
    route_id: str
    ride_ids: List[int] = field(default_factory=list)
    passenger_user_ids: List[int] = field(default_factory=list)


def _pooled_requests(stop, statuses: Optional[Iterable[str]]) -> List[RideRequest]:
    """Ride requests of a virtual stop that take part in this pool."""
    if statuses is None:
        requests = list(stop.ride_requests or [])
    else:
        allowed = set(statuses)
        requests = [request for request in (stop.ride_requests or []) if request.status in allowed]
    return sorted(requests, key=lambda request: request.id)


def _merge_route_details(chunks: Sequence[Dict]) -> Dict:
    """Stitch per-window route details into one geometry plus numbered legs."""
    geometry: List[List[float]] = []
    legs: List[Dict] = []
    maneuvers: List[Dict] = []
    for chunk in chunks:
        offset = max(0, len(geometry) - 1)
        for leg in chunk.get("legs") or []:
            leg_geometry = leg.get("geometry") or []
            if len(leg_geometry) < 2:
                continue
            legs.append({
                "index": len(legs),
                "geometry": leg_geometry,
                "distance_meters": float(leg.get("distanceMeters") or 0),
                "duration_seconds": float(leg.get("durationSeconds") or 0),
                "begin_shape_index": offset,
                "end_shape_index": offset + len(leg_geometry) - 1,
            })
            offset += len(leg_geometry) - 1
        chunk_geometry = chunk.get("geometry") or []
        if chunk_geometry:
            geometry.extend(chunk_geometry if not geometry else chunk_geometry[1:])
        maneuvers.extend(chunk.get("maneuvers") or [])
    return {
        "geometry": geometry,
        "legs": legs,
        "maneuvers": maneuvers,
        "distance_meters": sum(leg["distance_meters"] for leg in legs),
        "duration_seconds": sum(leg["duration_seconds"] for leg in legs),
    }


def enrich_route_geometry(points: Sequence[Dict]) -> Optional[Dict]:
    """Road geometry with a per-leg split for ordered waypoints; None if the router is unconfigured, fails, or the route is too long."""
    if not STADIA_API_KEY or len(points) < 2:
        return None
    chunks: List[Dict] = []
    start = 0
    while start < len(points) - 1:
        if len(chunks) >= MAX_ENRICHMENT_CHUNKS:
            return None
        window = list(points[start:start + ROUTE_LOCATION_WINDOW + 1])
        try:
            chunk = extract_route_details(
                route_many([{"lat": point["lat"], "lon": point["lng"]} for point in window])
            )
        except RuntimeError:
            return None
        chunks.append(chunk)
        start += len(window) - 1
    merged = _merge_route_details(chunks)
    return merged if merged["geometry"] else None


def _finalize_route(
    *,
    vehicle_index: int,
    waypoints: List[Dict],
    depot_lat: float,
    depot_lng: float,
    enrich: bool,
    problem: str,
    fallback_distance_m: float = 0.0,
) -> Optional[BuiltRoute]:
    """Ride/dropoff/stop ids derive from the waypoints so solver and private-ride path can't disagree; None if nothing to drive."""
    if len(waypoints) < 2:
        return None

    details = None
    if enrich:
        details = enrich_route_geometry(
            [{"lat": waypoint["lat"], "lng": waypoint["lng"]} for waypoint in waypoints]
        )
    if not fallback_distance_m:
        fallback_distance_m = sum(
            haversine_meters(
                float(previous["lat"]),
                float(previous["lng"]),
                float(current["lat"]),
                float(current["lng"]),
            )
            for previous, current in zip(waypoints, waypoints[1:])
        )
    distance_m = float((details or {}).get("distance_meters") or 0) or float(fallback_distance_m or 0)
    duration_s = float((details or {}).get("duration_seconds") or 0) or (
        distance_m / FALLBACK_METRES_PER_SECOND if distance_m else 0.0
    )

    ride_ids = sorted({
        request_id
        for waypoint in waypoints
        for request_id in waypoint.get("passenger_ids") or []
    })
    destination_ride_ids = [
        waypoint["passenger_ids"][0]
        for waypoint in waypoints
        if waypoint.get("waypoint_type") == "destination" and waypoint.get("passenger_ids")
    ]
    stop_ids = sorted({
        waypoint["stop_id"]
        for waypoint in waypoints
        if waypoint.get("stop_id") is not None
    })

    return BuiltRoute(
        vehicle_index=vehicle_index,
        depot_lat=depot_lat,
        depot_lng=depot_lng,
        waypoints=waypoints,
        ride_ids=ride_ids,
        destination_ride_ids=destination_ride_ids,
        stop_ids=stop_ids,
        distance_m=distance_m,
        duration_s=duration_s,
        geometry=(details or {}).get("geometry") or [],
        legs=(details or {}).get("legs") or [],
        maneuvers=(details or {}).get("maneuvers") or [],
        provider="stadia" if details else "local-road-matrix",
        problem=problem,
    )


def build_shared_routes(
    *,
    vehicles: Sequence[Vehicle],
    virtual_stops: Sequence,
    depot_lat: float,
    depot_lng: float,
    request_statuses: Optional[Iterable[str]] = None,
    enrich: bool = True,
) -> List[BuiltRoute]:
    """Solve routes over these virtual stops; request_statuses picks the pool (None = all at a stop, dispatch passes clustered)."""
    vehicles = list(vehicles or [])
    if not vehicles:
        return []

    pooled: List[Tuple[object, List[RideRequest]]] = []
    for stop in sorted(virtual_stops or [], key=lambda candidate: candidate.id):
        requests = _pooled_requests(stop, request_statuses)
        if requests:
            pooled.append((stop, requests))
    if not pooled:
        return []

    def _is_private(requests: List[RideRequest]) -> bool:
        # Default True mirrors the is_shared column default: a request without the flag is shared.
        return all(getattr(request, "is_shared", True) is False for request in requests)

    private_pooled = [(stop, requests) for stop, requests in pooled if _is_private(requests)]
    # Corridor matches make one stop per rider on purpose, so pool on total shared riders for the route, never a stop's own request count.
    shared_pooled = [
        (stop, requests)
        for stop, requests in pooled
        if not _is_private(requests)
    ]
    shared_passenger_count = sum(len(requests) for _, requests in shared_pooled)

    # One vehicle per private ride; extras stay clustered for a later dispatch rather than being pooled onto someone else's route.
    reserved_private = private_pooled[:len(vehicles)]
    vehicle_offset = len(reserved_private)
    remaining_vehicles = vehicles[vehicle_offset:]

    built_routes: List[BuiltRoute] = []
    for vehicle_index, (stop, requests) in enumerate(reserved_private):
        waypoints: List[Dict] = [{
            "stop_id": stop.id,
            "lat": float(stop.lat),
            "lng": float(stop.lng),
            "waypoint_type": "pickup",
            "passenger_ids": [request.id for request in requests],
        }]
        for request in requests:
            waypoints.append({
                "stop_id": None,
                "lat": float(request.dest_lat),
                "lng": float(request.dest_lng),
                "waypoint_type": "destination",
                "passenger_ids": [request.id],
            })
        # Private routes skip PDP, but must not skip road reachability checks.
        matrix = vrp_solver.build_stadia_distance_matrix(waypoints)
        if matrix is None:
            matrix = vrp_solver.build_road_distance_matrix(waypoints)
        if matrix is None:
            continue
        route = _finalize_route(
            vehicle_index=vehicle_index,
            waypoints=waypoints,
            depot_lat=depot_lat,
            depot_lng=depot_lng,
            enrich=enrich,
            problem="pdp",
            fallback_distance_m=sum(matrix[i][i + 1] for i in range(len(waypoints) - 1)),
        )
        if route is not None:
            built_routes.append(route)

    if (
        not shared_pooled
        or shared_passenger_count < MIN_CARPOOL_PASSENGERS
        or not remaining_vehicles
    ):
        return built_routes

    # Carpool policy is stricter than physical vehicle capacity: three passengers per shared run.
    capacities = [min(MAX_CARPOOL_PASSENGERS, max(1, int(vehicle.capacity or 1))) for vehicle in remaining_vehicles]
    smallest_capacity = min(capacities)

    # Depot, one boarding node per pooled stop, one destination per request.
    node_meta: List[Dict] = [{"kind": "depot", "stop": None, "requests": []}]
    nodes: List[Dict] = [{"lat": depot_lat, "lng": depot_lng, "kind": "depot", "demand": 0}]
    for stop, requests in shared_pooled:
        pickup_index = len(nodes)
        nodes.append({
            "lat": float(stop.lat),
            "lng": float(stop.lng),
            "kind": "pickup",
            "demand": len(requests),
        })
        node_meta.append({"kind": "pickup", "stop": stop, "requests": requests})
        for request in requests:
            nodes.append({
                "lat": float(request.dest_lat),
                "lng": float(request.dest_lng),
                "kind": "destination",
                "demand": 1,
                "pair_index": pickup_index,
            })
            node_meta.append({"kind": "destination", "stop": None, "requests": [request]})

    problem = "pdp"
    solve_options = dict(
        nodes=nodes,
        num_vehicles=len(remaining_vehicles),
        vehicle_capacity=smallest_capacity,
        vehicle_capacities=capacities,
        min_passengers_per_vehicle=MIN_CARPOOL_PASSENGERS,
        max_passengers_per_vehicle=MAX_CARPOOL_PASSENGERS,
    )
    # With enough vehicles, require all riders first. Making every node optional
    # up front lets a heuristic settle on 3 + an unserved singleton instead of 2+2.
    needs_partial = shared_passenger_count > MAX_CARPOOL_PASSENGERS * len(remaining_vehicles)
    solution = solve_shared_ride_pdp(**solve_options, allow_unserved=needs_partial)
    if solution.get("status") != ROUTE_SOLVED and not needs_partial:
        solution = solve_shared_ride_pdp(**solve_options, allow_unserved=True)
    if solution.get("status") != ROUTE_SOLVED:
        # A pickup-only route has no drop-off waypoint and would falsely mark riders assigned; leave the pool clustered to retry.
        return built_routes

    for route_data in solution.get("routes", []):
        vehicle_index = int(route_data["vehicle_idx"])
        if vehicle_index >= len(remaining_vehicles):
            continue

        waypoints: List[Dict] = []
        # Index 0 is the depot every route starts from.
        for node_index in route_data["stop_indices"][1:]:
            if node_index >= len(node_meta):
                continue
            meta = node_meta[node_index]
            if meta["kind"] == "pickup":
                waypoints.append({
                    "stop_id": meta["stop"].id,
                    "lat": float(meta["stop"].lat),
                    "lng": float(meta["stop"].lng),
                    "waypoint_type": "pickup",
                    "passenger_ids": [request.id for request in meta["requests"]],
                })
            elif meta["kind"] == "destination":
                request = meta["requests"][0]
                waypoints.append({
                    "stop_id": None,
                    "lat": float(request.dest_lat),
                    "lng": float(request.dest_lng),
                    "waypoint_type": "destination",
                    "passenger_ids": [request.id],
                })

        route = _finalize_route(
            # Offset past the vehicles reserved for private rides so the caller's own vehicle indexing still lines up.
            vehicle_index=vehicle_index + vehicle_offset,
            waypoints=waypoints,
            depot_lat=depot_lat,
            depot_lng=depot_lng,
            enrich=enrich,
            problem=problem,
            fallback_distance_m=float(route_data.get("distance_m") or 0),
        )
        if route is not None:
            built_routes.append(route)

    return built_routes


def _dispatch_pool_order(waypoints, pairs, depot_lat, depot_lng, capacity):
    """Exact search for one already-matched pool (at most six stops)."""
    points = [*waypoints, {"lat": depot_lat, "lng": depot_lng}]
    distances = vrp_solver.build_stadia_distance_matrix(points)
    if distances is None:
        distances = vrp_solver.build_road_distance_matrix(points)
    if distances is None:
        return None
    limits = [
        min(distances[p][d] + MAX_CARPOOL_DETOUR_METERS,
            max(1, distances[p][d]) * MAX_CARPOOL_DETOUR_RATIO)
        for p, d in pairs
    ]
    best = None
    for order in permutations(range(len(waypoints))):
        positions = {node: index for index, node in enumerate(order)}
        spans = [(positions[p], positions[d]) for p, d in pairs]
        if any(p >= d for p, d in spans):
            continue
        if any(sum(p <= index < d for p, d in spans) > capacity for index in range(len(order))):
            continue
        travelled = [0]
        for a, b in zip(order, order[1:]):
            travelled.append(travelled[-1] + distances[a][b])
        if any(travelled[d] - travelled[p] > limit for (p, d), limit in zip(spans, limits)):
            continue
        if any(not any(
            i != j and travelled[min(d, other_d)] - travelled[max(p, other_p)] > 1
            for j, (other_p, other_d) in enumerate(spans)
        ) for i, (p, d) in enumerate(spans)):
            continue
        cost = distances[-1][order[0]] + travelled[-1]
        if best is None or cost < best[0]:
            best = (cost, order)
    return best


def build_dispatch_routes(*, vehicles, virtual_stops, depot_lat, depot_lng, request_statuses):
    """Dispatch verified pools independently so a bad pool cannot block another."""
    groups = {}
    for stop in sorted(virtual_stops, key=lambda item: item.id):
        for ride in _pooled_requests(stop, request_statuses):
            if ride.is_shared:
                # Old stops can have no cluster ID. Do not accidentally pool
                # unrelated stops merely because both IDs are missing.
                key = ("pool", stop.cluster_id) if stop.cluster_id is not None else ("stop", stop.id)
            else:
                key = ("private", ride.id)
            groups.setdefault(key, []).append((stop, ride))

    available = list(enumerate(vehicles))
    built = []
    for key, members in groups.items():
        if not available:
            break
        private = key[0] == "private"
        count = len(members)
        if not private and not MIN_CARPOOL_PASSENGERS <= count <= MAX_CARPOOL_PASSENGERS:
            continue
        # Preserve the smallest adequate vehicle for each pool. A 3-rider
        # corridor may use a 2-seat car if the exact order permits seat reuse.
        candidates = [(index, vehicle) for index, vehicle in available
                      if private or int(vehicle.capacity or 1) >= MIN_CARPOOL_PASSENGERS]
        if not candidates:
            continue
        candidates.sort(key=lambda item: (int(item[1].capacity or 1), item[0]))
        pickups = [{
            "stop_id": stop.id, "lat": float(stop.lat), "lng": float(stop.lng),
            "waypoint_type": "pickup", "passenger_ids": [ride.id],
        } for stop, ride in members]
        destinations = [{
            "stop_id": None, "lat": float(ride.dest_lat), "lng": float(ride.dest_lng),
            "waypoint_type": "destination", "passenger_ids": [ride.id],
        } for _, ride in members]
        waypoints = pickups + destinations
        if private:
            matrix = vrp_solver.build_stadia_distance_matrix(waypoints)
            if matrix is None:
                matrix = vrp_solver.build_road_distance_matrix(waypoints)
            if matrix is None:
                continue
            index, _ = candidates[0]
            distance = matrix[0][1]
        else:
            pairs = [(i, count + i) for i in range(count)]
            # Solve once with the largest available capacity, then prefer the
            # smallest vehicle that can carry the chosen order.
            max_capacity = min(count, int(candidates[-1][1].capacity or 1))
            best = _dispatch_pool_order(waypoints, pairs, depot_lat, depot_lng, max_capacity)
            if best is None:
                continue
            distance, order = best
            index_at = {node: i for i, node in enumerate(order)}
            peak = max(sum(index_at[p] <= i < index_at[d] for p, d in pairs) for i in range(len(order)))
            index, _ = next(item for item in candidates if int(item[1].capacity or 1) >= peak)
            waypoints = [waypoints[node] for node in order]
        route = _finalize_route(
            vehicle_index=index, waypoints=waypoints, depot_lat=depot_lat, depot_lng=depot_lng,
            enrich=False, problem="pdp", fallback_distance_m=distance,
        )
        if route is not None:
            available = [item for item in available if item[0] != index]
            built.append(route)
    return built


def persist_shared_route(
    db: Session,
    built: BuiltRoute,
    *,
    vehicle: Vehicle,
    mode: str = LIVE_MODE,
    created_by_user_id: Optional[int] = None,
    source_cluster_run_id: Optional[int] = None,
    demo_run_id: Optional[str] = None,
    assign_statuses: Optional[Iterable[str]] = None,
) -> PersistedRoute:
    """Persist one pooled route and hand its passengers over as assigned."""
    route_id = f"route-{vehicle.id}-{uuid4().hex[:8]}"
    route_requests = db.query(RideRequest).filter(RideRequest.id.in_(built.ride_ids)).all()
    vehicle.assigned_route_id = route_id
    vehicle.status = VEHICLE_ACTIVE

    route_plan = RoutePlan(
        route_id=route_id,
        vehicle_id=vehicle.id,
        source_cluster_run_id=source_cluster_run_id,
        status=ROUTE_SOLVED,
        mode=mode,
        demo_run_id=demo_run_id,
        depot_lat=built.depot_lat,
        depot_lng=built.depot_lng,
        total_distance_meters=float(built.distance_m),
        estimated_duration_seconds=float(built.duration_s),
        created_by_user_id=created_by_user_id,
        route_metadata={
            "vehicle_capacity": vehicle.capacity,
            "assigned_stop_ids": built.stop_ids,
            "assigned_dropoff_request_ids": built.destination_ride_ids,
            # Assignment and driver acceptance are separate events; nothing moves until the driver accepts in the app.
            "driver_accepted": False,
            "driver_accepted_at": None,
            "carpool_run": any(getattr(request, "is_shared", False) for request in route_requests),
            "source_cluster_run_id": source_cluster_run_id,
            "geometry": built.geometry,
            "legs": built.legs,
            "maneuvers": built.maneuvers,
            "routing_provider": built.provider,
            "problem": built.problem,
            "return_to_depot": False,
            "geometry_resolved": bool(built.geometry),
        },
    )
    db.add(route_plan)
    db.flush()

    for sequence, waypoint in enumerate(built.waypoints):
        db.add(RouteWaypointRecord(
            route_plan_id=route_plan.id,
            sequence=sequence,
            stop_id=waypoint["stop_id"],
            lat=waypoint["lat"],
            lng=waypoint["lng"],
            waypoint_type=waypoint["waypoint_type"],
            passenger_ids=waypoint["passenger_ids"],
        ))

    allowed = None if assign_statuses is None else set(assign_statuses)
    ride_ids: List[int] = []
    passenger_user_ids: List[int] = []
    for ride_id in built.ride_ids:
        ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
        if not ride:
            continue
        if allowed is None or ride.status in allowed:
            # Shared rides also carry the finer carpool stage so the passenger sees it; private rides only have the coarse status.
            if getattr(ride, "is_shared", False):
                set_carpool_stage(ride, CARPOOL_ASSIGNED)
            else:
                ride.status = RIDE_ASSIGNED
        ride_ids.append(ride.id)
        passenger_user_ids.append(ride.user_id)

    return PersistedRoute(
        route_plan=route_plan,
        route_id=route_id,
        ride_ids=ride_ids,
        passenger_user_ids=sorted(set(passenger_user_ids)),
    )


def resolve_route_geometry(db: Session, route_plan: RoutePlan) -> Optional[Dict]:
    """Route geometry resolved once on first read; successes and failures are both cached so polling clients can't hammer the router."""
    geometry = route_plan_meta.geometry(route_plan)
    if geometry:
        return {
            "geometry": geometry,
            "legs": route_plan_meta.legs(route_plan),
            "provider": route_plan_meta.routing_provider(route_plan),
        }
    if route_plan_meta.is_geometry_resolved(route_plan):
        return None

    waypoints = sorted(route_plan.waypoints or [], key=lambda waypoint: waypoint.sequence)
    details = enrich_route_geometry([
        {"lat": float(waypoint.lat), "lng": float(waypoint.lng)} for waypoint in waypoints
    ])

    route_plan_meta.record_geometry_resolved(route_plan)
    if details and details.get("geometry"):
        route_plan_meta.record_geometry(
            route_plan,
            geometry=details["geometry"],
            legs=details.get("legs") or [],
            maneuvers=details.get("maneuvers") or [],
            provider="stadia",
        )
    db.commit()

    if not details or not details.get("geometry"):
        return None
    return {
        "geometry": details["geometry"],
        "legs": details.get("legs") or [],
        "provider": "stadia",
    }
