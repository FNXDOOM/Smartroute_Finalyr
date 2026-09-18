"""Pooled shared-ride routing: one pickup + destination route per vehicle.

Both the admin/driver optimize endpoint (``routers/route.py``) and the
automatic dispatch job (``services/background_jobs.py``) need the same three
things: turn pooled virtual stops into an optimized route, split that route's
road geometry per leg, and persist it as a ``RoutePlan`` with its passengers
marked as assigned. This module owns that once so the two paths cannot drift.

The pool is a pickup-and-delivery problem, not the pickups-only CVRP it used to
be: every ride request contributes a destination node paired with the boarding
stop its passenger walks to. A destination hands its demand back to the
vehicle, so seats are only occupied between a boarding stop and its drop-off.
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from config import STADIA_API_KEY
from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.route_waypoint import RouteWaypointRecord
from models.vehicle import Vehicle
from services.routing.vrp_solver import solve_shared_ride_pdp, solve_vrp
from services.stadia_client import extract_route_details, route_many
from utils.ride_scope import LIVE_MODE


# Valhalla accepts a bounded number of locations per routing request, so long
# routes are enriched in overlapping windows (one leg per consecutive pair).
ROUTE_LOCATION_WINDOW = 24
# Bound the upstream work a single lazy resolution may trigger.
MAX_ENRICHMENT_CHUNKS = 6
# Fallback speed used when the router returns no duration (~30 km/h).
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
    """Road geometry (with a per-leg split) for an ordered list of waypoints.

    Best effort: returns ``None`` when the router is unconfigured, fails, or the
    route is longer than one enrichment run should attempt.
    """
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


def build_shared_routes(
    *,
    vehicles: Sequence[Vehicle],
    virtual_stops: Sequence,
    depot_lat: float,
    depot_lng: float,
    request_statuses: Optional[Iterable[str]] = None,
    enrich: bool = True,
) -> List[BuiltRoute]:
    """Solve one pooled route per vehicle over the supplied virtual stops.

    ``request_statuses`` selects which requests take part (``None`` pools every
    request at a stop — the manual optimize endpoint's behaviour; the dispatch
    job passes ``("clustered",)``).
    """
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

    capacities = [max(1, int(vehicle.capacity or 1)) for vehicle in vehicles]
    smallest_capacity = min(capacities)

    # Depot, one boarding node per pooled stop, one destination per request.
    node_meta: List[Dict] = [{"kind": "depot", "stop": None, "requests": []}]
    nodes: List[Dict] = [{"lat": depot_lat, "lng": depot_lng, "kind": "depot", "demand": 0}]
    for stop, requests in pooled:
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
    solution = solve_shared_ride_pdp(
        nodes=nodes,
        num_vehicles=len(vehicles),
        vehicle_capacity=smallest_capacity,
        vehicle_capacities=capacities,
    )
    if solution.get("status") != "solved":
        # A pool can be infeasible (fewer seats than riders in one run). Fall
        # back to the pickups-only CVRP this pipeline used before, so dispatch
        # still assigns vehicles instead of silently doing nothing.
        problem = "cvrp"
        nodes = [{"lat": depot_lat, "lng": depot_lng, "demand": 0, "stop_id": None}]
        node_meta = [{"kind": "depot", "stop": None, "requests": []}]
        for stop, requests in pooled:
            nodes.append({
                "lat": float(stop.lat),
                "lng": float(stop.lng),
                "demand": len(requests),
                "stop_id": stop.id,
            })
            node_meta.append({"kind": "pickup", "stop": stop, "requests": requests})
        solution = solve_vrp(
            stops=nodes,
            num_vehicles=len(vehicles),
            vehicle_capacity=smallest_capacity,
            vehicle_capacities=capacities,
        )
        if solution.get("status") != "solved":
            return []

    built_routes: List[BuiltRoute] = []
    for route_data in solution.get("routes", []):
        vehicle_index = int(route_data["vehicle_idx"])
        if vehicle_index >= len(vehicles):
            continue

        waypoints: List[Dict] = []
        ride_ids: List[int] = []
        destination_ride_ids: List[int] = []
        stop_ids: List[int] = []
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
                stop_ids.append(meta["stop"].id)
                ride_ids.extend(request.id for request in meta["requests"])
            elif meta["kind"] == "destination":
                request = meta["requests"][0]
                waypoints.append({
                    "stop_id": None,
                    "lat": float(request.dest_lat),
                    "lng": float(request.dest_lng),
                    "waypoint_type": "destination",
                    "passenger_ids": [request.id],
                })
                destination_ride_ids.append(request.id)

        if problem == "cvrp":
            # The pickups-only fallback keeps the shape it always had: the route
            # closes back at the hub, which is not part of the solver's stops.
            waypoints.append({
                "stop_id": None,
                "lat": depot_lat,
                "lng": depot_lng,
                "waypoint_type": "depot",
                "passenger_ids": [],
            })

        if len(waypoints) < 2:
            continue

        details = None
        if enrich:
            details = enrich_route_geometry(
                [{"lat": waypoint["lat"], "lng": waypoint["lng"]} for waypoint in waypoints]
            )
        distance_m = float((details or {}).get("distance_meters") or 0) or float(route_data.get("distance_m") or 0)
        duration_s = float((details or {}).get("duration_seconds") or 0) or (
            distance_m / FALLBACK_METRES_PER_SECOND if distance_m else 0.0
        )

        built_routes.append(BuiltRoute(
            vehicle_index=vehicle_index,
            depot_lat=depot_lat,
            depot_lng=depot_lng,
            waypoints=waypoints,
            ride_ids=sorted(set(ride_ids)),
            destination_ride_ids=destination_ride_ids,
            stop_ids=sorted(set(stop_ids)),
            distance_m=distance_m,
            duration_s=duration_s,
            geometry=(details or {}).get("geometry") or [],
            legs=(details or {}).get("legs") or [],
            maneuvers=(details or {}).get("maneuvers") or [],
            provider="stadia" if details else "local-road-matrix",
            problem=problem,
        ))

    return built_routes


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
    vehicle.assigned_route_id = route_id
    vehicle.status = "active"

    route_plan = RoutePlan(
        route_id=route_id,
        vehicle_id=vehicle.id,
        source_cluster_run_id=source_cluster_run_id,
        status="solved",
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
            "source_cluster_run_id": source_cluster_run_id,
            "geometry": built.geometry,
            "legs": built.legs,
            "maneuvers": built.maneuvers,
            "routing_provider": built.provider,
            "problem": built.problem,
            "return_to_depot": built.problem == "cvrp",
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
            ride.status = "assigned"
        ride_ids.append(ride.id)
        passenger_user_ids.append(ride.user_id)

    return PersistedRoute(
        route_plan=route_plan,
        route_id=route_id,
        ride_ids=ride_ids,
        passenger_user_ids=sorted(set(passenger_user_ids)),
    )


def resolve_route_geometry(db: Session, route_plan: RoutePlan) -> Optional[Dict]:
    """Road geometry and per-leg split for a route plan, resolving once.

    Route plans written by the automatic dispatch job carry no road geometry,
    so a passenger opening the map is the first chance to fetch it. Both the
    result and a failed attempt are cached on the plan, so a client polling
    every few seconds can never hammer the router.
    """
    metadata = dict(route_plan.route_metadata or {})
    geometry = metadata.get("geometry") or []
    if geometry:
        return {
            "geometry": geometry,
            "legs": metadata.get("legs") or [],
            "provider": metadata.get("routing_provider") or "unknown",
        }
    if metadata.get("geometry_resolved"):
        return None

    waypoints = sorted(route_plan.waypoints or [], key=lambda waypoint: waypoint.sequence)
    details = enrich_route_geometry([
        {"lat": float(waypoint.lat), "lng": float(waypoint.lng)} for waypoint in waypoints
    ])

    metadata["geometry_resolved"] = True
    if details and details.get("geometry"):
        metadata["geometry"] = details["geometry"]
        metadata["legs"] = details.get("legs") or []
        metadata["maneuvers"] = details.get("maneuvers") or []
        metadata["routing_provider"] = "stadia"
    route_plan.route_metadata = metadata
    db.commit()

    if not details or not details.get("geometry"):
        return None
    return {
        "geometry": details["geometry"],
        "legs": details.get("legs") or [],
        "provider": "stadia",
    }
