from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session, load_only

from database import SessionLocal
from config import AUTO_DISPATCH_INTERVAL_SECONDS
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
    get_h3_center,
    get_h3_index,
    neighbouring_h3_cells,
    partition_requests,
)
from services.clustering.hdbscan_clusterer import cluster_passengers, get_cluster_groups
from services.prediction.demand_model import count_requests_by_h3, predict_zone_demands
from services.stops.road_snapper import build_road_graph, snap_to_road
from services.stops.virtual_stop_generator import generate_virtual_stops
from services.routing.shared_route_builder import build_shared_routes, persist_shared_route
from services.routing.vrp_solver import shared_ride_solver_time_limit
from services.notifications import create_notification, create_notifications_for_users
from services import job_runs, route_plan_meta
from services.carpool_matching import (
    MAX_PICKUP_WALK_METERS,
    MIN_CARPOOL_PASSENGERS,
    attach_to_existing_run,
    find_cross_cell_corridor_groups,
    split_compatible_shared_group,
    road_matching_batch,
    road_matching_diagnostics,
)
from utils.carpool_status import (
    CARPOOL_CLUSTERED,
    CARPOOL_SEARCHING,
    set_carpool_stage,
)
from utils.geo import haversine_meters as _haversine_meters
from utils.ride_scope import LIVE_MODE, PRESENTATION_DEMO_MODE, apply_ride_scope, validate_ride_mode
from utils.ride_states import (
    RIDE_ARRIVING,
    RIDE_ASSIGNED,
    RIDE_CLUSTERED,
    RIDE_COMPLETED,
    RIDE_IN_PROGRESS,
    RIDE_PENDING,
    RIDE_SERVING_STATUSES,
    ROUTE_CANCELLED,
    ROUTE_SOLVED,
    VEHICLE_IDLE,
    is_terminal_ride,
)

logger = logging.getLogger(__name__)

CLUSTER_INTERVAL_SECONDS = AUTO_DISPATCH_INTERVAL_SECONDS
DEMAND_INTERVAL_SECONDS = 300
REBALANCE_INTERVAL_SECONDS = 300
SIMULATE_DISPATCH_INTERVAL_SECONDS = 5
DRIVER_PRESENCE_TIMEOUT_SECONDS = 90
OPTIMIZE_JOB_POLL_SECONDS = 2

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




def _create_clustered_stop(
    db: Session,
    members: List[RideRequest],
    *,
    h3_index: str,
    cluster_id: int,
    resolution: int,
    mode: str,
    demo_run_id: Optional[str],
    exact_pickup: bool = False,
) -> Dict:
    """One virtual stop for a group of rides, marked clustered; shared by HDBSCAN groups and private singletons so they can't drift."""
    centroid_lat = sum(req.pickup_lat for req in members) / len(members)
    centroid_lng = sum(req.pickup_lng for req in members) / len(members)
    if exact_pickup or all(not request.is_shared for request in members):
        if len(members) != 1:
            raise ValueError("Private rides must have an exclusive pickup")
        snapped_lat, snapped_lng, snapped_node_id = members[0].pickup_lat, members[0].pickup_lng, "requested-pickup"
    else:
        candidate_stops = generate_virtual_stops(members, n_stops=1)
        stop_lat, stop_lng = candidate_stops[0]
        road_graph = build_road_graph(centroid_lat, centroid_lng, dist=2500)
        snapped_lat, snapped_lng, snapped_node_id = snap_to_road(road_graph, stop_lat, stop_lng)
    max_walk_meters = max(
        _haversine_meters(request.pickup_lat, request.pickup_lng, snapped_lat, snapped_lng)
        for request in members
    )
    if max_walk_meters > MAX_PICKUP_WALK_METERS:
        # Never snap a rider further than they agreed to walk; fall back to the exact requested pickup.
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
            request.status = RIDE_CLUSTERED
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
    """One stop per rider under a shared cluster id: each walks to its own curb and PDP orders them onto one route."""
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
                exact_pickup=True,
            )
        )
    return payloads


def pending_rides_query(db: Session, mode: str, demo_run_id: Optional[str]):
    """Pending rides scoped by mode, used by the clustering job and EXPLAIN script."""
    return apply_ride_scope(db.query(RideRequest), mode, demo_run_id).filter(
        RideRequest.status == RIDE_PENDING
    ).order_by(RideRequest.request_time.asc())


@road_matching_batch()
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
    started = time.monotonic()
    try:
        mode = validate_ride_mode(mode)
        ride_query = apply_ride_scope(db.query(RideRequest), mode, demo_run_id)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    with job_runs.running(
        db, "cluster_pending_rides", triggered_by_user_id=triggered_by_user_id, is_scheduled=is_scheduled
    ) as job_run:
        requests = pending_rides_query(db, mode, demo_run_id).all()
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
            job_runs.finish(
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

        # Existing runs get first refusal, so carpooling is continuous rather than per-tick; unmatched shared rides show "searching" while still "pending".
        for request in requests:
            if request.is_shared:
                set_carpool_stage(request, CARPOOL_SEARCHING)
        unmatched_requests = []
        for request in requests:
            if request.is_shared and attach_to_existing_run(
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

        # Private rides never pool: pull them from HDBSCAN and give each a singleton stop so dispatch still assigns it a vehicle.
        shared_requests = [request for request in requests if request.is_shared]
        private_requests = [request for request in requests if not request.is_shared]

        buckets = partition_requests(shared_requests, resolution=resolution)
        next_cluster_id = (db.query(VirtualStop.cluster_id).order_by(VirtualStop.cluster_id.desc()).first() or (0,))[0]
        next_cluster_id += 1
        cluster_groups_payload: List[Dict] = []
        noise_count = 0
        clusters_formed = 0
        clustered_shared_ids: set[int] = set()

        # Ordering: the fast local H3 pass runs first; the corridor pass below only sees requests it left unmatched.

        for bucket_h3_index in sorted(buckets):
            # Candidates are this cell plus neighbours, minus riders already placed, so edge riders can pool across cells.
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
                for compatible_members in split_compatible_shared_group(members):
                    # A carpool needs two compatible riders; keep singletons pending for a later pass.
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
        corridor_groups, _ = find_cross_cell_corridor_groups(unmatched_shared_requests)
        for corridor_group in corridor_groups:
            # One cluster id per corridor pool, one stop per rider; a per-rider id split them into single-passenger routes, so no carpool formed.
            cluster_groups_payload.extend(
                _create_per_rider_stops(
                    db,
                    corridor_group,
                    cluster_id=next_cluster_id,
                    resolution=resolution,
                    mode=mode,
                    demo_run_id=demo_run_id,
                )
            )
            clusters_formed += 1
            next_cluster_id += 1

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

        diagnostics = road_matching_diagnostics()
        diagnostics["clustering_duration_ms"] = round((time.monotonic() - started) * 1000)
        job_runs.finish(
            db,
            job_run,
            "partial" if diagnostics.get("routing_failures") else "success",
            {
                "cluster_run_id": cluster_run.id,
                "processed_requests": len(requests),
                "clusters_formed": clusters_formed,
                "noise_requests_count": noise_count,
                **diagnostics,
            },
        )
        db.commit()
        return {
            "job_run_id": job_run.id,
            "cluster_run_id": cluster_run.id,
            "processed_requests": len(requests),
            "clusters_formed": clusters_formed,
            "noise_requests_count": noise_count,
            **diagnostics,
        }

def run_demand_refresh_job(
    db: Session,
    lookback_days: int = 30,
    resolution: int = 9,
    reference_time: Optional[datetime] = None,
    triggered_by_user_id: Optional[int] = None,
    is_scheduled: bool = True,
) -> Dict:
    """Refresh demand forecasts and record the job outcome."""
    with job_runs.running(
        db, "refresh_demand_snapshots", triggered_by_user_id=triggered_by_user_id, is_scheduled=is_scheduled
    ) as job_run:
        ref_time = reference_time or datetime.now(timezone.utc)
        counts_by_h3 = count_requests_by_h3(
            db, reference_time=ref_time, lookback_days=lookback_days, resolution=resolution
        )
        predictions = predict_zone_demands(
            db,
            h3_indexes=counts_by_h3.keys(),
            reference_time=ref_time,
            lookback_days=lookback_days,
            counts_by_h3=counts_by_h3,
        )

        snapshots = []
        for prediction in predictions:
            h3_index = prediction["h3_index"]
            cell_lat, cell_lng = get_h3_center(h3_index)
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

        job_runs.finish(
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

def run_vehicle_rebalance_job(
    db: Session,
    lookback_days: int = 30,
    max_zones: int = 10,
    triggered_by_user_id: Optional[int] = None,
    is_scheduled: bool = True,
) -> Dict:
    """Generate rebalancing suggestions and record the job outcome."""
    with job_runs.running(
        db, "rebalance_idle_vehicles", triggered_by_user_id=triggered_by_user_id, is_scheduled=is_scheduled
    ) as job_run:
        idle_vehicles = db.query(Vehicle).filter(
            Vehicle.mode == LIVE_MODE,
            Vehicle.status == VEHICLE_IDLE,
        ).order_by(Vehicle.id.asc()).all()
        if not idle_vehicles:
            job_runs.finish(
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

        ref_time = datetime.now(timezone.utc)
        demand_cells = count_requests_by_h3(db, reference_time=ref_time, lookback_days=lookback_days)
        predictions = predict_zone_demands(
            db,
            h3_indexes=demand_cells.keys(),
            reference_time=ref_time,
            lookback_days=lookback_days,
            counts_by_h3=demand_cells,
        )
        ranked_cells = []
        for prediction in predictions:
            h3_index = prediction["h3_index"]
            lat, lng = get_h3_center(h3_index)
            ranked_cells.append(
                {
                    "h3_index": h3_index,
                    "lat": lat,
                    "lng": lng,
                    "score": float(prediction["predicted_demand"]),
                    "historical_count": demand_cells.get(h3_index, 0),
                }
            )

        ranked_cells.sort(key=lambda item: item["score"], reverse=True)
        ranked_cells = ranked_cells[:max_zones]
        if not ranked_cells:
            job_runs.finish(
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

        job_runs.finish(
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

@road_matching_batch()
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
    with job_runs.running(
        db, "auto_dispatch_pipeline", triggered_by_user_id=triggered_by_user_id, is_scheduled=is_scheduled
    ) as job_run:
        # Release offers stuck on a driver who went offline before accepting, so another online driver can take them.
        if mode == LIVE_MODE:
            presence_cutoff = datetime.now(timezone.utc) - timedelta(seconds=DRIVER_PRESENCE_TIMEOUT_SECONDS)
            stale_routes = (
                db.query(RoutePlan)
                .join(Vehicle, Vehicle.id == RoutePlan.vehicle_id)
                .join(User, User.id == Vehicle.driver_user_id)
                .filter(
                    RoutePlan.mode == LIVE_MODE,
                    RoutePlan.status == ROUTE_SOLVED,
                    (
                        User.driver_last_seen_at.is_(None)
                        | (User.driver_last_seen_at < presence_cutoff)
                    ),
                )
                .all()
            )
            stale_routes = [
                route for route in stale_routes
                if not route_plan_meta.is_driver_accepted(route)
            ]
            for stale_route in stale_routes:
                ride_ids = {
                    ride_id
                    for waypoint in stale_route.waypoints
                    for ride_id in (waypoint.passenger_ids or [])
                }
                for ride in db.query(RideRequest).filter(RideRequest.id.in_(ride_ids)).all() if ride_ids else []:
                    if not is_terminal_ride(ride.status):
                        if ride.is_shared:
                            set_carpool_stage(ride, CARPOOL_CLUSTERED)
                        else:
                            ride.status = RIDE_CLUSTERED
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
                stale_route.status = ROUTE_CANCELLED
                route_plan_meta.mark_cancelled(stale_route, "driver_offline_before_acceptance")
                vehicle = stale_route.vehicle
                if vehicle and vehicle.assigned_route_id == stale_route.route_id:
                    vehicle.assigned_route_id = None
                    vehicle.status = VEHICLE_IDLE

        cluster_res = run_cluster_job(
            db,
            triggered_by_user_id=triggered_by_user_id,
            is_scheduled=is_scheduled,
            mode=mode,
            demo_run_id=demo_run_id,
        )
        matching_info = {
            **road_matching_diagnostics(),
            "clustering_duration_ms": cluster_res.get("clustering_duration_ms", 0),
        }

        # Clustered stops without active routes.
        clustered_rides = apply_ride_scope(
            db.query(RideRequest), mode, demo_run_id
        ).filter(
            RideRequest.status == RIDE_CLUSTERED,
            RideRequest.virtual_stop_id.isnot(None),
        ).all()

        if not clustered_rides:
            job_runs.finish(db, job_run, "partial" if matching_info["routing_failures"] else "success", {
                "clusters_formed": cluster_res.get("clusters_formed", 0),
                "routes_optimized": 0,
                "assigned_rides": 0,
                "message": ("Road matching incomplete; pending riders will be retried"
                            if matching_info["routing_failures"] else "No unassigned clustered rides to dispatch"),
                **matching_info,
            })
            db.commit()
            return {
                "job_run_id": job_run.id,
                "clusters_formed": cluster_res.get("clusters_formed", 0),
                "routes_optimized": 0,
                "assigned_rides": 0,
                **matching_info,
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
                    status=VEHICLE_IDLE,
                    lat=depot_lat,
                    lng=depot_lng,
                )
                db.add(demo_vehicle)
                db.flush()
            demo_vehicle.status = VEHICLE_IDLE
            demo_vehicle.assigned_route_id = None
            vehicle_scope = vehicle_scope.filter(Vehicle.id == demo_vehicle.id)
        else:
            vehicle_scope = vehicle_scope.filter(Vehicle.mode == LIVE_MODE)
            # Vehicle "idle" alone is no proof anyone can accept; require a driver who recently opened the app.
            presence_cutoff = datetime.now(timezone.utc) - timedelta(seconds=DRIVER_PRESENCE_TIMEOUT_SECONDS)
            vehicle_scope = vehicle_scope.join(User, User.id == Vehicle.driver_user_id).filter(
                User.role == "driver",
                User.driver_status == "active",
                User.driver_last_seen_at.isnot(None),
                User.driver_last_seen_at >= presence_cutoff,
            )
        idle_vehicles = vehicle_scope.filter(
            (Vehicle.status == VEHICLE_IDLE) | (Vehicle.assigned_route_id.is_(None))
        ).order_by(Vehicle.id.asc()).all()

        if not idle_vehicles or not virtual_stops:
            job_runs.finish(db, job_run, "partial" if matching_info["routing_failures"] else "success", {
                "clusters_formed": cluster_res.get("clusters_formed", 0),
                "routes_optimized": 0,
                "idle_vehicles": len(idle_vehicles),
                "message": "No idle vehicles available for dispatch",
                **matching_info,
            })
            db.commit()
            return {
                "job_run_id": job_run.id,
                "clusters_formed": cluster_res.get("clusters_formed", 0),
                "routes_optimized": 0,
                "idle_vehicles": len(idle_vehicles),
                **matching_info,
            }

        built_routes = build_shared_routes(
            vehicles=idle_vehicles,
            virtual_stops=virtual_stops,
            depot_lat=depot_lat,
            depot_lng=depot_lng,
            request_statuses=(RIDE_CLUSTERED,),
        )
        matching_info.update(road_matching_diagnostics())

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
                assign_statuses=(RIDE_CLUSTERED,),
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
                        "carpool_run": route_plan_meta.is_carpool(persisted.route_plan),
                    },
                )
            routes_count += 1

        job_runs.finish(db, job_run, "partial" if matching_info["routing_failures"] else "success", {
            "clusters_formed": cluster_res.get("clusters_formed", 0),
            "routes_optimized": routes_count,
            "assigned_rides": assigned_rides_count,
            **matching_info,
        })
        db.commit()
        return {
            "job_run_id": job_run.id,
            "clusters_formed": cluster_res.get("clusters_formed", 0),
            "routes_optimized": routes_count,
            "assigned_rides": assigned_rides_count,
            **matching_info,
        }

def simulate_rides_query(db: Session):
    """The serving-ride selection used by the simulator and the EXPLAIN script."""
    return db.query(RideRequest).options(
        load_only(
            RideRequest.id,
            RideRequest.user_id,
            RideRequest.is_shared,
            RideRequest.virtual_stop_id,
            RideRequest.status,
        )
    ).filter(
        RideRequest.status.in_(RIDE_SERVING_STATUSES),
        RideRequest.virtual_stop_id.isnot(None),
    )


def run_simulate_ride_dispatch_job(db: Session, is_scheduled: bool = True) -> Dict:
    """Advance pipeline rides for live WS demo."""
    with job_runs.running(db, "simulate_ride_dispatch", is_scheduled=is_scheduled) as job_run:
        active_rides = simulate_rides_query(db).all()

        stop_ids = {ride.virtual_stop_id for ride in active_rides if not ride.is_shared}
        waypoint_by_stop = {}
        if stop_ids:
            for stop_id, route_plan_id in (
                db.query(RouteWaypointRecord.stop_id, RouteWaypointRecord.route_plan_id)
                .filter(RouteWaypointRecord.stop_id.in_(stop_ids))
                .all()
            ):
                waypoint_by_stop.setdefault(stop_id, route_plan_id)

        plan_ids = set(waypoint_by_stop.values())
        plans_by_id = {}
        if plan_ids:
            for plan in (
                db.query(RoutePlan)
                .options(load_only(RoutePlan.id, RoutePlan.status, RoutePlan.vehicle_id, RoutePlan.route_metadata))
                .filter(RoutePlan.id.in_(plan_ids), RoutePlan.status == ROUTE_SOLVED)
                .all()
            ):
                plans_by_id[plan.id] = plan

        vehicle_ids = {plan.vehicle_id for plan in plans_by_id.values() if plan.vehicle_id}
        vehicles_by_id = {}
        if vehicle_ids:
            for vehicle in (
                db.query(Vehicle)
                .options(load_only(Vehicle.id, Vehicle.status, Vehicle.assigned_route_id))
                .filter(Vehicle.id.in_(vehicle_ids))
                .all()
            ):
                vehicles_by_id[vehicle.id] = vehicle

        transitions = {
            RIDE_ASSIGNED: RIDE_ARRIVING,
            RIDE_ARRIVING: RIDE_IN_PROGRESS,
            RIDE_IN_PROGRESS: RIDE_COMPLETED,
        }

        active_counts: dict[int, int] = {}
        for ride in active_rides:
            if not ride.is_shared and ride.virtual_stop_id:
                stop_id = ride.virtual_stop_id
                active_counts[stop_id] = active_counts.get(stop_id, 0) + 1

        updates_count = 0
        for ride in active_rides:
            # Shared rides advance stop-by-stop from the carpool run screen; the generic timer must never simulate those events.
            if ride.is_shared:
                continue
            # A solved route is only an offer: nothing progresses until the assigned driver explicitly accepts.
            route_plan = plans_by_id.get(waypoint_by_stop.get(ride.virtual_stop_id))
            if not route_plan or not route_plan_meta.is_driver_accepted(route_plan):
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

                # If done, free the already-preloaded vehicle if nothing else serves the stop.
                if new_status == RIDE_COMPLETED and ride.virtual_stop_id and route_plan.vehicle_id:
                    veh = vehicles_by_id.get(route_plan.vehicle_id)
                    if veh:
                        other_active = active_counts.get(ride.virtual_stop_id, 0) - 1
                        if other_active <= 0:
                            veh.status = VEHICLE_IDLE
                            veh.assigned_route_id = None

        job_runs.finish(
            db,
            job_run,
            "success",
            {"updates_count": updates_count},
        )
        db.commit()
        return {"job_run_id": job_run.id, "updates_count": updates_count}

def run_scheduled_auto_dispatch_job(db: Session) -> Dict:
    """Run live dispatch from the worker and mark it as scheduled."""
    return run_auto_dispatch_pipeline(db, is_scheduled=True)


def _as_aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _claim_optimize_job(db: Session) -> Optional[JobRun]:
    """Claim one queued optimize job; SKIP LOCKED on Postgres, re-checked update on SQLite."""
    now = datetime.now(timezone.utc)
    running_jobs = (
        db.query(JobRun)
        .filter(JobRun.job_name == "optimize_route", JobRun.status == "running")
        .all()
    )
    changed = False
    for job in running_jobs:
        started = _as_aware(job.started_at)
        if started and started < now - timedelta(seconds=shared_ride_solver_time_limit() + 60):
            job.status = "failed"
            job.error_message = "Optimize worker timed out"
            job.finished_at = now
            changed = True
    if changed:
        db.commit()

    queued = (
        db.query(JobRun)
        .filter(JobRun.job_name == "optimize_route", JobRun.status == "queued")
        .order_by(JobRun.id.asc())
    )
    if db.get_bind().dialect.name == "postgresql":
        job = queued.with_for_update(skip_locked=True).first()
        if job:
            job.status = "running"
            job.started_at = now
            job.finished_at = None
            job.error_message = None
            db.commit()
            db.refresh(job)
        return job

    job = queued.first()
    if not job:
        return None
    claimed = (
        db.query(JobRun)
        .filter(JobRun.id == job.id, JobRun.status == "queued")
        .update(
            {"status": "running", "started_at": now, "finished_at": None, "error_message": None},
            synchronize_session=False,
        )
    )
    db.commit()
    if not claimed:
        return None
    db.refresh(job)
    return job


def run_optimize_jobs(db: Session) -> Dict:
    """Claim and execute one queued /route/optimize/async job."""
    job = _claim_optimize_job(db)
    if job is None:
        return {"processed": 0}
    job_id = job.id
    try:
        from routers.route import run_route_optimization
        from schemas.route import VRPRequest

        request_data = (job.summary or {}).get("request")
        if not request_data:
            raise ValueError("Optimize job is missing its request payload")
        user = db.query(User).filter(User.id == job.triggered_by_user_id).first()
        if user is None:
            raise ValueError("Optimize job owner no longer exists")
        result = run_route_optimization(db, VRPRequest.model_validate(request_data), user)
        job = db.query(JobRun).filter(JobRun.id == job_id).first()
        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = None
        job.summary = {**(job.summary or {}), "result": result.model_dump(mode="json")}
        db.commit()
        return {"processed": 1, "job_id": job_id, "status": "succeeded"}
    except Exception as exc:
        db.rollback()
        job = db.query(JobRun).filter(JobRun.id == job_id).first()
        if job:
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = str(getattr(exc, "detail", exc))[:1000]
            db.commit()
        logger.warning("optimize job %s failed: %s", job_id, exc.__class__.__name__)
        return {"processed": 1, "job_id": job_id, "status": "failed"}


async def _run_periodic(name: str, interval_seconds: int, runner):
    """Run a background job repeatedly at the configured interval."""
    def run_once() -> None:
        # Runners do blocking DB/routing/solver work, so they stay off FastAPI's event loop.
        db = SessionLocal()
        try:
            runner(db)
        finally:
            db.close()

    STATE.active_tasks.append(name)
    try:
        while True:
            tick_started = asyncio.get_running_loop().time()
            try:
                await asyncio.to_thread(run_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Log, don't re-raise: nothing awaits these tasks, so a raise would silently retire the schedule for the worker's lifetime.
                logger.exception("background job %s raised; schedule continues", name)
            now = datetime.now(timezone.utc)
            if name in {"cluster_pending_rides", "auto_dispatch_pipeline"}:
                STATE.last_cluster_run_at = now
            elif name == "refresh_demand_snapshots":
                STATE.last_demand_run_at = now
            elif name == "rebalance_idle_vehicles":
                STATE.last_rebalance_run_at = now
            elif name == "simulate_ride_dispatch":
                STATE.last_dispatch_run_at = now
            # Scheduling is start-to-start, not processing time + another full wait.
            # Awaiting run_once above guarantees no overlapping ticks.
            elapsed = asyncio.get_running_loop().time() - tick_started
            await asyncio.sleep(max(0.1, interval_seconds - elapsed))
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
    # Live rides need the whole chain (cluster -> corridor match -> PDP -> assignment); the standalone cluster job is admin-only.
    _TASKS.append(loop.create_task(_run_periodic("auto_dispatch_pipeline", AUTO_DISPATCH_INTERVAL_SECONDS, run_scheduled_auto_dispatch_job)))
    _TASKS.append(loop.create_task(_run_periodic("refresh_demand_snapshots", DEMAND_INTERVAL_SECONDS, run_demand_refresh_job)))
    _TASKS.append(loop.create_task(_run_periodic("rebalance_idle_vehicles", REBALANCE_INTERVAL_SECONDS, run_vehicle_rebalance_job)))
    _TASKS.append(loop.create_task(_run_periodic("simulate_ride_dispatch", SIMULATE_DISPATCH_INTERVAL_SECONDS, run_simulate_ride_dispatch_job)))
    _TASKS.append(loop.create_task(_run_periodic("optimize_route_jobs", OPTIMIZE_JOB_POLL_SECONDS, run_optimize_jobs)))


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
        "auto_dispatch_interval_seconds": AUTO_DISPATCH_INTERVAL_SECONDS,
        "demand_interval_seconds": DEMAND_INTERVAL_SECONDS,
        "rebalance_interval_seconds": REBALANCE_INTERVAL_SECONDS,
        "simulate_dispatch_interval_seconds": SIMULATE_DISPATCH_INTERVAL_SECONDS,
    }
