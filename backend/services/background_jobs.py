from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from database import SessionLocal
from models.cluster_run import ClusterRun
from models.demand_snapshot import DemandSnapshot
from models.job_run import JobRun
from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.route_waypoint import RouteWaypointRecord
from models.user import User
from models.vehicle import Vehicle
from models.vehicle_rebalance_suggestion import VehicleRebalanceSuggestion
from models.virtual_stop import VirtualStop
from services.clustering.h3_partitioner import (
    get_h3_index,
    neighbouring_h3_cells,
    partition_requests,
)
from services.clustering.hdbscan_clusterer import cluster_passengers, get_cluster_groups
from services.prediction.demand_model import predict_zone_demand
from services.prediction.feature_engineering import get_h3_center
from services.stops.road_snapper import build_road_graph, snap_to_road
from services.stops.virtual_stop_generator import generate_virtual_stops
from services.routing.shared_route_builder import build_shared_routes, persist_shared_route
from services.notifications import create_notification, create_notifications_for_users
from utils.carpool_status import (
    CARPOOL_CLUSTERED,
    CARPOOL_SEARCHING,
    set_carpool_stage,
)
from utils.geo import haversine_meters as _haversine_meters
from utils.ride_scope import LIVE_MODE, PRESENTATION_DEMO_MODE, apply_ride_scope, validate_ride_mode

CLUSTER_INTERVAL_SECONDS = 60
AUTO_DISPATCH_INTERVAL_SECONDS = 60
DEMAND_INTERVAL_SECONDS = 300
REBALANCE_INTERVAL_SECONDS = 300
SIMULATE_DISPATCH_INTERVAL_SECONDS = 5
DRIVER_PRESENCE_TIMEOUT_SECONDS = 90

# Pickup clustering is only the first gate. Keep riders with destinations in
# the same corridor so the PDP solver does not create unreasonable detours.
MAX_DESTINATION_SPREAD_METERS = 7000
MAX_CARPOOL_DETOUR_METERS = 5000
MAX_CARPOOL_DETOUR_RATIO = 1.45
MIN_CARPOOL_PASSENGERS = 2
MAX_CARPOOL_PASSENGERS = 3
MAX_PICKUP_WALK_METERS = 150


class _WalkLimitExceeded(Exception):
    """A shared stop cannot serve every rider within the walking limit."""


def _split_compatible_shared_group(requests: List[RideRequest]) -> List[List[RideRequest]]:
    """Split a pickup cluster into destination-compatible carpool pools.

    HDBSCAN deliberately only knows about pickup density. This second, small
    greedy pass keeps destinations close enough that the resulting route is a
    plausible shared trip while preserving deterministic request ordering.
    """
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


def _point_to_segment_coords_meters(
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


def _pickup_corridor_distance_meters(request: RideRequest, other: RideRequest) -> float:
    """Return the nearer directional pickup-to-destination corridor distance."""
    request_to_other_route = _point_to_segment_coords_meters(
        request.pickup_lat,
        request.pickup_lng,
        other.pickup_lat,
        other.pickup_lng,
        other.dest_lat,
        other.dest_lng,
    )
    other_to_request_route = _point_to_segment_coords_meters(
        other.pickup_lat,
        other.pickup_lng,
        request.pickup_lat,
        request.pickup_lng,
        request.dest_lat,
        request.dest_lng,
    )
    return min(request_to_other_route, other_to_request_route)


def _find_cross_cell_corridor_groups(
    requests: List[RideRequest],
) -> tuple[List[List[RideRequest]], set[int]]:
    """Find shared riders whose pickups lie along one another's route corridor.

    H3 is intentionally a fast spatial pre-filter, not a hard carpool boundary.
    This pass runs over the remaining shared requests so a rider in a nearby
    cell can join when their pickup lies within the 150 m corridor of another
    rider's pickup-to-destination route.
    """
    groups: List[List[RideRequest]] = []
    matched_ids: set[int] = set()
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
                _pickup_corridor_distance_meters(request, other) <= MAX_PICKUP_WALK_METERS
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


def _point_to_segment_meters(lat: float, lng: float, start, end) -> float:
    """Approximate distance from a GPS point to a route segment in meters."""
    scale = 111_000.0
    cos_lat = max(0.2, abs(math.cos(lat * math.pi / 180)))
    px, py = lng * scale * cos_lat, lat * scale
    ax, ay = start.lng * scale * cos_lat, start.lat * scale
    bx, by = end.lng * scale * cos_lat, end.lat * scale
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    nearest_x, nearest_y = ax + t * dx, ay + t * dy
    return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5


def _try_attach_to_existing_carpool_route(
    db: Session,
    request: RideRequest,
    *,
    mode: str,
    demo_run_id: Optional[str],
) -> bool:
    """Insert a new request into an unstarted carpool route when safe.

    The request must be close to an existing pickup stop, have a destination
    in the same corridor, and leave the route at three or fewer passengers.
    The route is then rebuilt as a pickup-and-delivery problem so the driver
    receives a real ordered itinerary instead of an appended JSON waypoint.
    """
    plans_query = db.query(RoutePlan).filter(
        RoutePlan.mode == mode,
        RoutePlan.status == "solved",
    )
    if mode == PRESENTATION_DEMO_MODE:
        plans_query = plans_query.filter(RoutePlan.demo_run_id == demo_run_id)

    for route_plan in plans_query.order_by(RoutePlan.created_at.desc()).all():
        if str((route_plan.route_metadata or {}).get("problem") or "pdp") != "pdp":
            continue
        metadata = route_plan.route_metadata or {}
        # A rider may join a route only before the driver has accepted (or
        # started/finished) it. Once accepted, the rider must wait for another
        # compatible route rather than silently changing a live itinerary.
        if metadata.get("driver_accepted") or metadata.get("carpool_run_status") in {"accepted", "completed"}:
            continue
        vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
        if not vehicle or vehicle.status not in {"active", "en_route", "idle"}:
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
            RideRequest.status.in_(["assigned", "arriving"]),
        ).all()
        if len(active_requests) != len(passenger_ids):
            # Do not rewrite a route that has already started or contains stale
            # passenger assignments.
            continue

        pickup_waypoints = [
            waypoint for waypoint in route_plan.waypoints or []
            if waypoint.waypoint_type == "pickup" and waypoint.stop_id is not None
        ]
        if not pickup_waypoints:
            continue

        ordered_waypoints = sorted(route_plan.waypoints or [], key=lambda waypoint: waypoint.sequence)
        corridor_distance = min(
            _point_to_segment_meters(
                request.pickup_lat,
                request.pickup_lng,
                start,
                end,
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
            # The request is on the route corridor but not at an existing curb;
            # add a dedicated road stop and let PDP place it in the itinerary.
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
            request_statuses=("clustered", "assigned", "arriving"),
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

        route_plan.status = "superseded"
        persisted = persist_shared_route(
            db,
            rebuilt[0],
            vehicle=vehicle,
            mode=mode,
            created_by_user_id=None,
            source_cluster_run_id=route_plan.source_cluster_run_id,
            demo_run_id=demo_run_id,
            assign_statuses=("clustered", "assigned", "arriving"),
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


@dataclass
class SchedulerState:
    running: bool = False
    last_cluster_run_at: Optional[datetime] = None
    last_demand_run_at: Optional[datetime] = None
    last_rebalance_run_at: Optional[datetime] = None
    last_dispatch_run_at: Optional[datetime] = None
    active_tasks: List[str] = None


STATE = SchedulerState(active_tasks=[])
_TASKS: List[asyncio.Task] = []




def _start_job_run(db: Session, job_name: str, triggered_by_user_id: Optional[int], is_scheduled: bool = True) -> JobRun:
    """Create and persist a running background-job record."""
    job_run = JobRun(
        job_name=job_name,
        status="running",
        triggered_by_user_id=triggered_by_user_id,
        is_scheduled=is_scheduled,
        summary={},
    )
    db.add(job_run)
    db.flush()
    return job_run


def _finish_job_run(db: Session, job_run: JobRun, status: str, summary: Dict, error_message: Optional[str] = None) -> None:
    """Finalize a background-job record with its outcome."""
    job_run.status = status
    job_run.summary = summary
    job_run.error_message = error_message
    job_run.finished_at = datetime.now(timezone.utc)
    db.add(job_run)


def _create_clustered_stop(
    db: Session,
    members: List[RideRequest],
    *,
    h3_index: str,
    cluster_id: int,
    resolution: int,
    mode: str,
    demo_run_id: Optional[str],
) -> Dict:
    """Create one virtual stop for a group of rides and mark them clustered.

    Shared by the HDBSCAN groups and by the private-ride singletons, so the two
    paths cannot drift on stop generation, road snapping or status handling.
    """
    centroid_lat = sum(req.pickup_lat for req in members) / len(members)
    centroid_lng = sum(req.pickup_lng for req in members) / len(members)
    candidate_stops = generate_virtual_stops(members, n_stops=1)
    stop_lat, stop_lng = candidate_stops[0]
    road_graph = build_road_graph(centroid_lat, centroid_lng, dist=2500)
    snapped_lat, snapped_lng, snapped_node_id = snap_to_road(road_graph, stop_lat, stop_lng)
    max_walk_meters = max(
        _haversine_meters(request.pickup_lat, request.pickup_lng, snapped_lat, snapped_lng)
        for request in members
    )
    if max_walk_meters > MAX_PICKUP_WALK_METERS:
        if len(members) > 1:
            raise _WalkLimitExceeded
        # A private ride should never force a passenger to walk to a distant
        # shared curb. Keep the exact requested point as the safe fallback.
        snapped_lat, snapped_lng, snapped_node_id = members[0].pickup_lat, members[0].pickup_lng, "requested-pickup"

    virtual_stop = VirtualStop(
        cluster_id=cluster_id,
        mode=mode,
        demo_run_id=demo_run_id,
        h3_index=h3_index,
        lat=snapped_lat,
        lng=snapped_lng,
        snapped_node_id=snapped_node_id,
        passenger_count=len(members),
    )
    db.add(virtual_stop)
    db.flush()

    ride_ids: List[int] = []
    for request in members:
        request.cluster_id = cluster_id
        request.virtual_stop_id = virtual_stop.id
        if getattr(request, "is_shared", False):
            set_carpool_stage(request, CARPOOL_CLUSTERED)
        else:
            request.status = "clustered"
        ride_ids.append(request.id)

    return {
        "cluster_id": cluster_id,
        "h3_index": h3_index,
        "ride_request_ids": ride_ids,
        "virtual_stop_id": virtual_stop.id,
        "virtual_stop_lat": virtual_stop.lat,
        "virtual_stop_lng": virtual_stop.lng,
        "passenger_count": len(members),
        "snapped_node_id": snapped_node_id,
    }


def _create_per_rider_stops(
    db: Session,
    members: List[RideRequest],
    *,
    cluster_id: int,
    resolution: int,
    mode: str,
    demo_run_id: Optional[str],
) -> List[Dict]:
    """One dedicated pickup stop per rider, all sharing one cluster id.

    Riders pooled onto the same route do not have to share a curb: each one gets
    its own stop within the walking limit of its own pickup (falling back to the
    exact pickup when road snapping would exceed it). The PDP solver then orders
    those stops onto the single route.
    """
    payloads: List[Dict] = []
    for member in members:
        member_cell = member.h3_index or get_h3_index(
            member.pickup_lat, member.pickup_lng, resolution=resolution
        )
        payloads.append(
            _create_clustered_stop(
                db,
                [member],
                h3_index=member_cell,
                cluster_id=cluster_id,
                resolution=resolution,
                mode=mode,
                demo_run_id=demo_run_id,
            )
        )
    return payloads


def run_cluster_job(
    db: Session,
    resolution: int = 9,
    min_cluster_size: int = 2,
    triggered_by_user_id: Optional[int] = None,
    is_scheduled: bool = True,
    mode: str = LIVE_MODE,
    demo_run_id: Optional[str] = None,
) -> Dict:
    """Execute clustering and record the background-job outcome."""
    try:
        mode = validate_ride_mode(mode)
        ride_query = apply_ride_scope(db.query(RideRequest), mode, demo_run_id)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    job_run = _start_job_run(db, "cluster_pending_rides", triggered_by_user_id, is_scheduled)
    try:
        requests = (
            ride_query
            .filter(RideRequest.status == "pending")
            .order_by(RideRequest.request_time.asc())
            .all()
        )
        if not requests:
            cluster_run = ClusterRun(
                run_uuid=str(uuid4()),
                resolution=resolution,
                min_cluster_size=min_cluster_size,
                status="no_pending_requests",
                total_processed_requests=0,
                clusters_formed=0,
                noise_requests_count=0,
                created_by_user_id=triggered_by_user_id,
                mode=mode,
                demo_run_id=demo_run_id,
                cluster_summary=[],
            )
            db.add(cluster_run)
            db.flush()
            _finish_job_run(
                db,
                job_run,
                "success",
                {
                    "cluster_run_id": cluster_run.id,
                    "processed_requests": 0,
                    "clusters_formed": 0,
                    "noise_requests_count": 0,
                },
            )
            db.commit()
            return {
                "job_run_id": job_run.id,
                "cluster_run_id": cluster_run.id,
                "processed_requests": 0,
                "clusters_formed": 0,
                "noise_requests_count": 0,
            }

        # Give a new carpool request first chance to join an existing route.
        # This is what makes carpooling continuous instead of batching only
        # requests that arrived in the same clustering tick.
        #
        # A shared request that has not been pooled yet is actively being
        # matched, so its fine carpool stage says "searching" while the coarse
        # status stays "pending" for older clients.
        for request in requests:
            if request.is_shared:
                set_carpool_stage(request, CARPOOL_SEARCHING)
        unmatched_requests = []
        for request in requests:
            if request.is_shared and _try_attach_to_existing_carpool_route(
                db,
                request,
                mode=mode,
                demo_run_id=demo_run_id,
            ):
                continue
            unmatched_requests.append(request)
        requests = unmatched_requests

        for request in requests:
            if not request.h3_index:
                request.h3_index = get_h3_index(request.pickup_lat, request.pickup_lng, resolution=resolution)

        # Private rides are never pooled with anyone: pull them out of the
        # HDBSCAN pool and give each its own singleton stop, so the normal
        # dispatch step still assigns it a vehicle (a private ride for one).
        shared_requests = [request for request in requests if request.is_shared]
        private_requests = [request for request in requests if not request.is_shared]

        buckets = partition_requests(shared_requests, resolution=resolution)
        next_cluster_id = (db.query(VirtualStop.cluster_id).order_by(VirtualStop.cluster_id.desc()).first() or (0,))[0]
        next_cluster_id += 1
        cluster_groups_payload: List[Dict] = []
        noise_count = 0
        clusters_formed = 0
        clustered_shared_ids: set[int] = set()

        # H3 keeps the normal clustering pass fast, but neighboring H3 cells
        # must not be a hard boundary. The local H3 pass runs first; the
        # corridor pass below only sees requests that did not form a local
        # compatible group.

        for bucket_h3_index in sorted(buckets):
            # H3 is a fast spatial pre-filter, not a hard boundary. Build the
            # candidate set from this cell plus its immediate neighbours, and
            # skip riders a previous bucket already placed, so a rider near a
            # cell edge can still pool with someone on the other side.
            bucket_requests = [
                request
                for cell in sorted(neighbouring_h3_cells(bucket_h3_index))
                for request in buckets.get(cell, [])
                if request.id not in clustered_shared_ids
            ]
            if not bucket_requests:
                continue

            labels = cluster_passengers(bucket_requests, min_cluster_size=min_cluster_size)
            noise_count += int((labels == -1).sum())
            grouped_requests = get_cluster_groups(bucket_requests, labels)

            for _, members in grouped_requests.items():
                for compatible_members in _split_compatible_shared_group(members):
                    # A carpool is only dispatched once at least two compatible
                    # riders are available. Keep a singleton pending so it can
                    # be matched by a later clustering/attachment pass.
                    if len(compatible_members) < MIN_CARPOOL_PASSENGERS:
                        continue
                    # One dedicated stop per rider, all under one cluster id.
                    created_payloads = _create_per_rider_stops(
                        db,
                        compatible_members,
                        cluster_id=next_cluster_id,
                        resolution=resolution,
                        mode=mode,
                        demo_run_id=demo_run_id,
                    )

                    cluster_groups_payload.extend(created_payloads)
                    clustered_shared_ids.update(request.id for request in compatible_members)
                    clusters_formed += 1
                    next_cluster_id += 1

        unmatched_shared_requests = [
            request for request in shared_requests if request.id not in clustered_shared_ids
        ]
        corridor_groups, _ = _find_cross_cell_corridor_groups(unmatched_shared_requests)
        for corridor_group in corridor_groups:
            for request in corridor_group:
                h3_index = request.h3_index or get_h3_index(
                    request.pickup_lat, request.pickup_lng, resolution=resolution
                )
                cluster_groups_payload.append(
                    _create_clustered_stop(
                        db,
                        [request],
                        h3_index=h3_index,
                        cluster_id=next_cluster_id,
                        resolution=resolution,
                        mode=mode,
                        demo_run_id=demo_run_id,
                    )
                )
                next_cluster_id += 1
            clusters_formed += 1

        for request in private_requests:
            h3_index = request.h3_index or get_h3_index(
                request.pickup_lat, request.pickup_lng, resolution=resolution
            )
            cluster_groups_payload.append(
                _create_clustered_stop(
                    db,
                    [request],
                    h3_index=h3_index,
                    cluster_id=next_cluster_id,
                    resolution=resolution,
                    mode=mode,
                    demo_run_id=demo_run_id,
                )
            )
            clusters_formed += 1
            next_cluster_id += 1

        cluster_run = ClusterRun(
            run_uuid=str(uuid4()),
            resolution=resolution,
            min_cluster_size=min_cluster_size,
            status="clustered",
            total_processed_requests=len(requests),
            clusters_formed=clusters_formed,
            noise_requests_count=noise_count,
            created_by_user_id=triggered_by_user_id,
            mode=mode,
            demo_run_id=demo_run_id,
            cluster_summary=cluster_groups_payload,
        )
        db.add(cluster_run)
        db.flush()

        _finish_job_run(
            db,
            job_run,
            "success",
            {
                "cluster_run_id": cluster_run.id,
                "processed_requests": len(requests),
                "clusters_formed": clusters_formed,
                "noise_requests_count": noise_count,
            },
        )
        db.commit()
        return {
            "job_run_id": job_run.id,
            "cluster_run_id": cluster_run.id,
            "processed_requests": len(requests),
            "clusters_formed": clusters_formed,
            "noise_requests_count": noise_count,
        }
    except Exception as exc:
        db.rollback()
        job_run = db.merge(job_run)
        _finish_job_run(db, job_run, "failed", {}, error_message=str(exc))
        db.commit()
        raise


def run_demand_refresh_job(
    db: Session,
    lookback_days: int = 30,
    resolution: int = 9,
    reference_time: Optional[datetime] = None,
    triggered_by_user_id: Optional[int] = None,
    is_scheduled: bool = True,
) -> Dict:
    """Refresh demand forecasts and record the job outcome."""
    job_run = _start_job_run(db, "refresh_demand_snapshots", triggered_by_user_id, is_scheduled)
    try:
        ref_time = reference_time or datetime.now(timezone.utc)
        threshold = ref_time - timedelta(days=lookback_days)
        rides = db.query(RideRequest).filter(
            RideRequest.request_time >= threshold,
            RideRequest.mode == LIVE_MODE,
        ).all()
        h3_indexes = set()
        for ride in rides:
            h3_indexes.add(ride.h3_index or get_h3_index(ride.pickup_lat, ride.pickup_lng, resolution=resolution))

        snapshots = []
        for h3_index in sorted(h3_indexes):
            cell_lat, cell_lng = get_h3_center(h3_index)
            prediction = predict_zone_demand(
                db,
                h3_index=h3_index,
                reference_time=ref_time,
                lookback_days=lookback_days,
            )
            snapshot = DemandSnapshot(
                job_run_id=job_run.id,
                h3_index=h3_index,
                lat=cell_lat,
                lng=cell_lng,
                lookback_days=lookback_days,
                historical_request_count=prediction["historical_request_count"],
                predicted_demand=prediction["predicted_demand"],
                model_name=prediction["model_name"],
                method=prediction["method"],
            )
            db.add(snapshot)
            snapshots.append(snapshot)

        _finish_job_run(
            db,
            job_run,
            "success",
            {
                "snapshots_created": len(snapshots),
                "lookback_days": lookback_days,
            },
        )
        db.commit()
        return {
            "job_run_id": job_run.id,
            "snapshots_created": len(snapshots),
            "lookback_days": lookback_days,
        }
    except Exception as exc:
        db.rollback()
        job_run = db.merge(job_run)
        _finish_job_run(db, job_run, "failed", {}, error_message=str(exc))
        db.commit()
        raise


def run_vehicle_rebalance_job(
    db: Session,
    lookback_days: int = 30,
    max_zones: int = 10,
    triggered_by_user_id: Optional[int] = None,
    is_scheduled: bool = True,
) -> Dict:
    """Generate rebalancing suggestions and record the job outcome."""
    job_run = _start_job_run(db, "rebalance_idle_vehicles", triggered_by_user_id, is_scheduled)
    try:
        idle_vehicles = db.query(Vehicle).filter(
            Vehicle.mode == LIVE_MODE,
            Vehicle.status == "idle",
        ).order_by(Vehicle.id.asc()).all()
        if not idle_vehicles:
            _finish_job_run(
                db,
                job_run,
                "success",
                {"suggestions_created": 0, "idle_vehicles": 0},
            )
            db.commit()
            return {
                "job_run_id": job_run.id,
                "suggestions_created": 0,
                "idle_vehicles": 0,
            }

        threshold = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        rides = db.query(RideRequest).filter(
            RideRequest.request_time >= threshold,
            RideRequest.mode == LIVE_MODE,
        ).all()
        demand_cells = {}
        for ride in rides:
            h3_index = ride.h3_index or get_h3_index(ride.pickup_lat, ride.pickup_lng)
            demand_cells.setdefault(h3_index, 0)
            demand_cells[h3_index] += 1

        ranked_cells = []
        for h3_index, count in demand_cells.items():
            prediction = predict_zone_demand(
                db,
                h3_index=h3_index,
                reference_time=datetime.now(timezone.utc),
                lookback_days=lookback_days,
            )
            lat, lng = get_h3_center(h3_index)
            ranked_cells.append(
                {
                    "h3_index": h3_index,
                    "lat": lat,
                    "lng": lng,
                    "score": float(prediction["predicted_demand"]),
                    "historical_count": count,
                }
            )

        ranked_cells.sort(key=lambda item: item["score"], reverse=True)
        ranked_cells = ranked_cells[:max_zones]
        if not ranked_cells:
            _finish_job_run(
                db,
                job_run,
                "success",
                {"suggestions_created": 0, "idle_vehicles": len(idle_vehicles)},
            )
            db.commit()
            return {
                "job_run_id": job_run.id,
                "suggestions_created": 0,
                "idle_vehicles": len(idle_vehicles),
            }

        suggestions = []
        for vehicle in idle_vehicles:
            best_cell = min(
                ranked_cells,
                key=lambda cell: _haversine_meters(vehicle.lat or cell["lat"], vehicle.lng or cell["lng"], cell["lat"], cell["lng"]),
            )
            suggestion = VehicleRebalanceSuggestion(
                job_run_id=job_run.id,
                vehicle_id=vehicle.id,
                target_h3_index=best_cell["h3_index"],
                target_lat=best_cell["lat"],
                target_lng=best_cell["lng"],
                score=best_cell["score"],
                reason="highest predicted demand zone among recent hotspots",
            )
            db.add(suggestion)
            suggestions.append(suggestion)

        _finish_job_run(
            db,
            job_run,
            "success",
            {
                "suggestions_created": len(suggestions),
                "idle_vehicles": len(idle_vehicles),
                "candidate_zones": len(ranked_cells),
            },
        )
        db.commit()
        return {
            "job_run_id": job_run.id,
            "suggestions_created": len(suggestions),
            "idle_vehicles": len(idle_vehicles),
            "candidate_zones": len(ranked_cells),
        }
    except Exception as exc:
        db.rollback()
        job_run = db.merge(job_run)
        _finish_job_run(db, job_run, "failed", {}, error_message=str(exc))
        db.commit()
        raise


def run_auto_dispatch_pipeline(
    db: Session,
    triggered_by_user_id: Optional[int] = None,
    is_scheduled: bool = False,
    depot_lat: float = 12.9784,
    depot_lng: float = 77.6408,
    mode: str = LIVE_MODE,
    demo_run_id: Optional[str] = None,
) -> Dict:
    """Run full dispatch: cluster, route, assign."""
    mode = validate_ride_mode(mode)
    if mode == PRESENTATION_DEMO_MODE and not demo_run_id:
        raise ValueError("demo_run_id is required for presentation_demo mode")
    job_run = _start_job_run(db, "auto_dispatch_pipeline", triggered_by_user_id, is_scheduled)
    try:
        # Do not leave rides stranded on a route whose driver went offline
        # before accepting it. Release those offers before building the next
        # dispatch plan so another online driver can receive them.
        if mode == LIVE_MODE:
            presence_cutoff = datetime.now(timezone.utc) - timedelta(seconds=DRIVER_PRESENCE_TIMEOUT_SECONDS)
            stale_routes = (
                db.query(RoutePlan)
                .join(Vehicle, Vehicle.id == RoutePlan.vehicle_id)
                .join(User, User.id == Vehicle.driver_user_id)
                .filter(
                    RoutePlan.mode == LIVE_MODE,
                    RoutePlan.status == "solved",
                    (
                        User.driver_last_seen_at.is_(None)
                        | (User.driver_last_seen_at < presence_cutoff)
                    ),
                )
                .all()
            )
            stale_routes = [
                route for route in stale_routes
                if not (route.route_metadata or {}).get("driver_accepted", False)
            ]
            for stale_route in stale_routes:
                ride_ids = {
                    ride_id
                    for waypoint in stale_route.waypoints
                    for ride_id in (waypoint.passenger_ids or [])
                }
                for ride in db.query(RideRequest).filter(RideRequest.id.in_(ride_ids)).all() if ride_ids else []:
                    if ride.status not in {"completed", "cancelled"}:
                        if ride.is_shared:
                            set_carpool_stage(ride, CARPOOL_CLUSTERED)
                        else:
                            ride.status = "clustered"
                        if ride.user_id:
                            create_notification(
                                db,
                                user_id=ride.user_id,
                                notification_type="route_reassigned",
                                title="Finding an available driver",
                                message="Your previous driver was unavailable. We are assigning your ride to an available driver.",
                                related_entity_type="ride_request",
                                related_entity_id=ride.id,
                                metadata={"previous_route_id": stale_route.route_id},
                            )
                stale_route.status = "cancelled"
                metadata = dict(stale_route.route_metadata or {})
                metadata["cancelled_reason"] = "driver_offline_before_acceptance"
                stale_route.route_metadata = metadata
                vehicle = stale_route.vehicle
                if vehicle and vehicle.assigned_route_id == stale_route.route_id:
                    vehicle.assigned_route_id = None
                    vehicle.status = "idle"

        # Step 1: cluster pending requests
        cluster_res = run_cluster_job(
            db,
            triggered_by_user_id=triggered_by_user_id,
            is_scheduled=is_scheduled,
            mode=mode,
            demo_run_id=demo_run_id,
        )

        # Clustered stops without active routes.
        clustered_rides = apply_ride_scope(
            db.query(RideRequest), mode, demo_run_id
        ).filter(
            RideRequest.status == "clustered",
            RideRequest.virtual_stop_id.isnot(None),
        ).all()

        if not clustered_rides:
            _finish_job_run(db, job_run, "success", {
                "clusters_formed": cluster_res.get("clusters_formed", 0),
                "routes_optimized": 0,
                "assigned_rides": 0,
                "message": "No unassigned clustered rides to dispatch",
            })
            db.commit()
            return {
                "job_run_id": job_run.id,
                "clusters_formed": cluster_res.get("clusters_formed", 0),
                "routes_optimized": 0,
                "assigned_rides": 0,
            }

        virtual_stop_ids = sorted({r.virtual_stop_id for r in clustered_rides if r.virtual_stop_id})
        virtual_stop_query = db.query(VirtualStop).filter(
            VirtualStop.id.in_(virtual_stop_ids),
            VirtualStop.mode == mode,
        )
        if mode == PRESENTATION_DEMO_MODE:
            virtual_stop_query = virtual_stop_query.filter(VirtualStop.demo_run_id == demo_run_id)
        virtual_stops = virtual_stop_query.all()

        vehicle_scope = db.query(Vehicle)
        if mode == PRESENTATION_DEMO_MODE:
            demo_vehicle = vehicle_scope.filter(
                Vehicle.mode == PRESENTATION_DEMO_MODE,
                Vehicle.license_plate == "DEMO-PRESENTATION-01",
            ).first()
            if not demo_vehicle:
                demo_vehicle = Vehicle(
                    license_plate="DEMO-PRESENTATION-01",
                    capacity=4,
                    mode=PRESENTATION_DEMO_MODE,
                    status="idle",
                    lat=depot_lat,
                    lng=depot_lng,
                )
                db.add(demo_vehicle)
                db.flush()
            demo_vehicle.status = "idle"
            demo_vehicle.assigned_route_id = None
            vehicle_scope = vehicle_scope.filter(Vehicle.id == demo_vehicle.id)
        else:
            vehicle_scope = vehicle_scope.filter(Vehicle.mode == LIVE_MODE)
            # A vehicle is dispatchable only when its assigned driver has
            # recently opened the driver app. Vehicle ``idle`` alone is not
            # proof that anyone is available to accept the route.
            presence_cutoff = datetime.now(timezone.utc) - timedelta(seconds=DRIVER_PRESENCE_TIMEOUT_SECONDS)
            vehicle_scope = vehicle_scope.join(User, User.id == Vehicle.driver_user_id).filter(
                User.role == "driver",
                User.driver_status == "active",
                User.driver_last_seen_at.isnot(None),
                User.driver_last_seen_at >= presence_cutoff,
            )
        idle_vehicles = vehicle_scope.filter(
            (Vehicle.status == "idle") | (Vehicle.assigned_route_id.is_(None))
        ).order_by(Vehicle.id.asc()).all()

        if not idle_vehicles or not virtual_stops:
            _finish_job_run(db, job_run, "success", {
                "clusters_formed": cluster_res.get("clusters_formed", 0),
                "routes_optimized": 0,
                "idle_vehicles": len(idle_vehicles),
                "message": "No idle vehicles available for dispatch",
            })
            db.commit()
            return {
                "job_run_id": job_run.id,
                "clusters_formed": cluster_res.get("clusters_formed", 0),
                "routes_optimized": 0,
                "idle_vehicles": len(idle_vehicles),
            }

        built_routes = build_shared_routes(
            vehicles=idle_vehicles,
            virtual_stops=virtual_stops,
            depot_lat=depot_lat,
            depot_lng=depot_lng,
            request_statuses=("clustered",),
        )

        routes_count = 0
        assigned_rides_count = 0

        for built in built_routes:
            if built.vehicle_index >= len(idle_vehicles):
                continue
            actual_vehicle = idle_vehicles[built.vehicle_index]
            persisted = persist_shared_route(
                db,
                built,
                vehicle=actual_vehicle,
                mode=mode,
                created_by_user_id=triggered_by_user_id,
                source_cluster_run_id=cluster_res.get("cluster_run_id"),
                demo_run_id=demo_run_id,
                assign_statuses=("clustered",),
            )
            assigned_rides_count += len(persisted.ride_ids)

            passenger_user_ids = persisted.passenger_user_ids
            if passenger_user_ids:
                create_notifications_for_users(
                    db,
                    user_ids=passenger_user_ids,
                    notification_type="route_assigned",
                    title="Your route has been optimized",
                    message=f"Your shared ride has been assigned to vehicle {actual_vehicle.license_plate}.",
                    related_entity_type="route_plan",
                    related_entity_id=persisted.route_plan.id,
                    metadata={"route_id": persisted.route_id, "vehicle_id": actual_vehicle.id},
                )
            if actual_vehicle.driver_user_id:
                create_notification(
                    db,
                    user_id=actual_vehicle.driver_user_id,
                    notification_type="route_assigned",
                    title="New route assigned",
                    message=(
                        f"Carpool run {persisted.route_id} is ready for your vehicle "
                        f"{actual_vehicle.license_plate}. Open Carpool Run to accept it."
                    ),
                    related_entity_type="route_plan",
                    related_entity_id=persisted.route_plan.id,
                    metadata={
                        "route_id": persisted.route_id,
                        "vehicle_id": actual_vehicle.id,
                        "carpool_run": bool((persisted.route_plan.route_metadata or {}).get("carpool_run")),
                    },
                )
            routes_count += 1

        _finish_job_run(db, job_run, "success", {
            "clusters_formed": cluster_res.get("clusters_formed", 0),
            "routes_optimized": routes_count,
            "assigned_rides": assigned_rides_count,
        })
        db.commit()
        return {
            "job_run_id": job_run.id,
            "clusters_formed": cluster_res.get("clusters_formed", 0),
            "routes_optimized": routes_count,
            "assigned_rides": assigned_rides_count,
        }
    except Exception as exc:
        db.rollback()
        job_run = db.merge(job_run)
        _finish_job_run(db, job_run, "failed", {}, error_message=str(exc))
        db.commit()
        raise


def run_simulate_ride_dispatch_job(db: Session, is_scheduled: bool = True) -> Dict:
    """Advance pipeline rides for live WS demo."""
    job_run = _start_job_run(db, "simulate_ride_dispatch", None, is_scheduled)
    try:
        active_rides = db.query(RideRequest).filter(
            RideRequest.status.in_(["assigned", "arriving", "in_progress"]),
            RideRequest.virtual_stop_id.isnot(None),
        ).all()

        transitions = {
            "assigned": "arriving",
            "arriving": "in_progress",
            "in_progress": "completed",
        }

        updates_count = 0
        for ride in active_rides:
            # Shared routes are controlled stop-by-stop from the carpool run
            # screen. Passenger readiness and driver pickup/drop-off events
            # must never be simulated by the generic timer.
            if ride.is_shared:
                continue
            # A solved route is only an offer to the driver. Do not simulate
            # arrival, trip progress, or completion until the assigned driver
            # explicitly accepts the route.
            waypoint = db.query(RouteWaypointRecord).filter(
                RouteWaypointRecord.stop_id == ride.virtual_stop_id
            ).first()
            route_plan = None
            if waypoint:
                route_plan = db.query(RoutePlan).filter(
                    RoutePlan.id == waypoint.route_plan_id,
                    RoutePlan.status == "solved",
                ).first()
            if not route_plan or not (route_plan.route_metadata or {}).get("driver_accepted", False):
                continue

            old_status = ride.status
            new_status = transitions.get(old_status)
            if new_status:
                ride.status = new_status

                create_notification(
                    db,
                    user_id=ride.user_id,
                    notification_type="ride_status_updated",
                    title="Ride status updated",
                    message=f"Your ride request #{ride.id} changed from {old_status} to {new_status}.",
                    related_entity_type="ride_request",
                    related_entity_id=ride.id,
                    metadata={"old_status": old_status, "new_status": new_status, "ride_id": ride.id},
                )
                updates_count += 1

                # If done, free vehicle if idle
                if new_status == "completed" and ride.virtual_stop_id:
                    if waypoint:
                        if route_plan and route_plan.vehicle_id:
                            veh = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
                            if veh:
                                other_active = db.query(RideRequest).filter(
                                    RideRequest.status.in_(["assigned", "arriving", "in_progress"]),
                                    RideRequest.virtual_stop_id == ride.virtual_stop_id,
                                ).count()
                                if other_active == 0:
                                    veh.status = "idle"
                                    veh.assigned_route_id = None

        _finish_job_run(
            db,
            job_run,
            "success",
            {"updates_count": updates_count},
        )
        db.commit()
        return {"job_run_id": job_run.id, "updates_count": updates_count}
    except Exception as exc:
        db.rollback()
        job_run = db.merge(job_run)
        _finish_job_run(db, job_run, "failed", {}, error_message=str(exc))
        db.commit()
        raise


def run_scheduled_auto_dispatch_job(db: Session) -> Dict:
    """Run live dispatch from the worker and mark it as scheduled."""
    return run_auto_dispatch_pipeline(db, is_scheduled=True)


async def _run_periodic(name: str, interval_seconds: int, runner):
    """Run a background job repeatedly at the configured interval."""
    def run_once() -> None:
        # Job runners are synchronous and can perform database, routing, and
        # solver work. Keep them off FastAPI's event loop so auth/profile and
        # passenger requests remain responsive while auto-dispatch runs.
        db = SessionLocal()
        try:
            runner(db)
        finally:
            db.close()

    STATE.active_tasks.append(name)
    try:
        while True:
            await asyncio.to_thread(run_once)
            now = datetime.now(timezone.utc)
            if name in {"cluster_pending_rides", "auto_dispatch_pipeline"}:
                STATE.last_cluster_run_at = now
            elif name == "refresh_demand_snapshots":
                STATE.last_demand_run_at = now
            elif name == "rebalance_idle_vehicles":
                STATE.last_rebalance_run_at = now
            elif name == "simulate_ride_dispatch":
                STATE.last_dispatch_run_at = now
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        pass
    finally:
        if name in STATE.active_tasks:
            STATE.active_tasks.remove(name)


def start_background_jobs() -> None:
    """Start the periodic background-job tasks."""
    if STATE.running:
        return

    STATE.running = True
    loop = asyncio.get_running_loop()
    _TASKS.clear()
    # Live rides must progress through the complete pipeline automatically:
    # cluster -> corridor match -> PDP route -> idle vehicle assignment.
    # Keep the standalone clustering endpoint for manual/admin diagnostics,
    # but do not leave production rides stranded in `clustered`.
    _TASKS.append(loop.create_task(_run_periodic("auto_dispatch_pipeline", AUTO_DISPATCH_INTERVAL_SECONDS, run_scheduled_auto_dispatch_job)))
    _TASKS.append(loop.create_task(_run_periodic("refresh_demand_snapshots", DEMAND_INTERVAL_SECONDS, run_demand_refresh_job)))
    _TASKS.append(loop.create_task(_run_periodic("rebalance_idle_vehicles", REBALANCE_INTERVAL_SECONDS, run_vehicle_rebalance_job)))
    _TASKS.append(loop.create_task(_run_periodic("simulate_ride_dispatch", SIMULATE_DISPATCH_INTERVAL_SECONDS, run_simulate_ride_dispatch_job)))


async def stop_background_jobs() -> None:
    """Cancel the running periodic background-job tasks."""
    if not _TASKS:
        STATE.running = False
        return
    for task in list(_TASKS):
        task.cancel()
    await asyncio.gather(*_TASKS, return_exceptions=True)
    _TASKS.clear()
    STATE.running = False


def get_background_job_state() -> Dict:
    """Return scheduler state for each background job."""
    return {
        "running": STATE.running,
        "last_cluster_run_at": STATE.last_cluster_run_at,
        "last_demand_run_at": STATE.last_demand_run_at,
        "last_rebalance_run_at": STATE.last_rebalance_run_at,
        "last_dispatch_run_at": STATE.last_dispatch_run_at,
        "active_tasks": list(STATE.active_tasks),
        "cluster_interval_seconds": CLUSTER_INTERVAL_SECONDS,
        "demand_interval_seconds": DEMAND_INTERVAL_SECONDS,
        "rebalance_interval_seconds": REBALANCE_INTERVAL_SECONDS,
        "simulate_dispatch_interval_seconds": SIMULATE_DISPATCH_INTERVAL_SECONDS,
    }
