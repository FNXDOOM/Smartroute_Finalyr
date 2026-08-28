from __future__ import annotations

import asyncio
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
from models.vehicle import Vehicle
from models.vehicle_rebalance_suggestion import VehicleRebalanceSuggestion
from models.virtual_stop import VirtualStop
from services.clustering.h3_partitioner import get_h3_index, partition_requests
from services.clustering.hdbscan_clusterer import cluster_passengers, get_cluster_groups
from services.prediction.demand_model import predict_zone_demand
from services.prediction.feature_engineering import get_h3_center
from services.stops.road_snapper import build_road_graph, snap_to_road
from services.stops.virtual_stop_generator import generate_virtual_stops
from services.routing.vrp_solver import solve_vrp
from services.notifications import create_notification, create_notifications_for_users
from utils.geo import haversine_meters as _haversine_meters
from utils.ride_scope import LIVE_MODE, PRESENTATION_DEMO_MODE, apply_ride_scope, validate_ride_mode

CLUSTER_INTERVAL_SECONDS = 60
DEMAND_INTERVAL_SECONDS = 300
REBALANCE_INTERVAL_SECONDS = 300
SIMULATE_DISPATCH_INTERVAL_SECONDS = 5


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
    job_run.status = status
    job_run.summary = summary
    job_run.error_message = error_message
    job_run.finished_at = datetime.now(timezone.utc)
    db.add(job_run)


def run_cluster_job(
    db: Session,
    resolution: int = 9,
    min_cluster_size: int = 2,
    triggered_by_user_id: Optional[int] = None,
    is_scheduled: bool = True,
    mode: str = LIVE_MODE,
    demo_run_id: Optional[str] = None,
) -> Dict:
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

        for request in requests:
            if not request.h3_index:
                request.h3_index = get_h3_index(request.pickup_lat, request.pickup_lng, resolution=resolution)

        buckets = partition_requests(requests, resolution=resolution)
        next_cluster_id = (db.query(VirtualStop.cluster_id).order_by(VirtualStop.cluster_id.desc()).first() or (0,))[0]
        next_cluster_id += 1
        cluster_groups_payload: List[Dict] = []
        noise_count = 0
        clusters_formed = 0

        for bucket_h3_index, bucket_requests in buckets.items():
            labels = cluster_passengers(bucket_requests, min_cluster_size=min_cluster_size)
            noise_count += int((labels == -1).sum())
            grouped_requests = get_cluster_groups(bucket_requests, labels)

            for _, members in grouped_requests.items():
                centroid_lat = sum(req.pickup_lat for req in members) / len(members)
                centroid_lng = sum(req.pickup_lng for req in members) / len(members)
                candidate_stops = generate_virtual_stops(members, n_stops=1)
                stop_lat, stop_lng = candidate_stops[0]
                road_graph = build_road_graph(centroid_lat, centroid_lng, dist=2500)
                snapped_lat, snapped_lng, snapped_node_id = snap_to_road(road_graph, stop_lat, stop_lng)

                virtual_stop = VirtualStop(
                    cluster_id=next_cluster_id,
                    mode=mode,
                    demo_run_id=demo_run_id,
                    h3_index=bucket_h3_index,
                    lat=snapped_lat,
                    lng=snapped_lng,
                    snapped_node_id=snapped_node_id,
                    passenger_count=len(members),
                )
                db.add(virtual_stop)
                db.flush()

                ride_ids: List[int] = []
                for request in members:
                    request.cluster_id = next_cluster_id
                    request.virtual_stop_id = virtual_stop.id
                    request.status = "clustered"
                    ride_ids.append(request.id)

                cluster_groups_payload.append(
                    {
                        "cluster_id": next_cluster_id,
                        "h3_index": bucket_h3_index,
                        "ride_request_ids": ride_ids,
                        "virtual_stop_id": virtual_stop.id,
                        "virtual_stop_lat": virtual_stop.lat,
                        "virtual_stop_lng": virtual_stop.lng,
                        "passenger_count": len(members),
                        "snapped_node_id": snapped_node_id,
                    }
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
    """
    Runs the full end-to-end AI Dispatch Pipeline:
    1. Clusters pending requests into virtual stops using HDBSCAN & K-Medoids + road snapping.
    2. Gathers clustered virtual stops and idle vehicles.
    3. Optimizes multi-passenger routes using Google OR-Tools CVRP solver.
    4. Dynamically assigns vehicles using Hungarian matching and updates ride status to 'assigned'.
    """
    mode = validate_ride_mode(mode)
    if mode == PRESENTATION_DEMO_MODE and not demo_run_id:
        raise ValueError("demo_run_id is required for presentation_demo mode")
    job_run = _start_job_run(db, "auto_dispatch_pipeline", triggered_by_user_id, is_scheduled)
    try:
        # Step 1: Run clustering on any pending requests
        cluster_res = run_cluster_job(
            db,
            triggered_by_user_id=triggered_by_user_id,
            is_scheduled=is_scheduled,
            mode=mode,
            demo_run_id=demo_run_id,
        )

        # Step 2: Find all clustered virtual stops that do not have an active route plan
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

        capacities = [v.capacity for v in idle_vehicles]
        stops = [{"lat": depot_lat, "lng": depot_lng, "demand": 0, "stop_id": None}]
        for vs in virtual_stops:
            stops.append({
                "lat": vs.lat,
                "lng": vs.lng,
                "demand": max(1, int(vs.passenger_count)),
                "stop_id": vs.id,
            })

        solution = solve_vrp(
            stops=stops,
            num_vehicles=len(idle_vehicles),
            vehicle_capacity=min(capacities) if capacities else 4,
            vehicle_capacities=capacities,
        )

        routes_count = 0
        assigned_rides_count = 0
        stop_lookup = {idx: stop for idx, stop in enumerate(stops)}

        for route_data in solution.get("routes", []):
            vehicle_idx = route_data["vehicle_idx"]
            if vehicle_idx >= len(idle_vehicles):
                continue
            actual_vehicle = idle_vehicles[vehicle_idx]
            route_id = f"route-{actual_vehicle.id}-{uuid4().hex[:8]}"

            waypoint_payloads = [{
                "stop_id": None,
                "lat": depot_lat,
                "lng": depot_lng,
                "waypoint_type": "depot",
                "passenger_ids": [],
            }]

            for stop_index in route_data["stop_indices"][1:]:
                stop = stop_lookup.get(stop_index)
                if not stop or stop.get("stop_id") is None:
                    continue
                vs_match = next((v for v in virtual_stops if v.id == stop["stop_id"]), None)
                if not vs_match:
                    continue
                passenger_ids = [req.id for req in vs_match.ride_requests if req.status == "clustered"]
                waypoint_payloads.append({
                    "stop_id": vs_match.id,
                    "lat": vs_match.lat,
                    "lng": vs_match.lng,
                    "waypoint_type": "pickup",
                    "passenger_ids": passenger_ids,
                })

            waypoint_payloads.append({
                "stop_id": None,
                "lat": depot_lat,
                "lng": depot_lng,
                "waypoint_type": "depot",
                "passenger_ids": [],
            })

            actual_vehicle.assigned_route_id = route_id
            actual_vehicle.status = "active"

            route_plan = RoutePlan(
                route_id=route_id,
                vehicle_id=actual_vehicle.id,
                source_cluster_run_id=cluster_res.get("cluster_run_id"),
                status="solved",
                depot_lat=depot_lat,
                depot_lng=depot_lng,
                total_distance_meters=float(route_data.get("distance_m", 0)),
                estimated_duration_seconds=float(route_data.get("distance_m", 0)) / 8.33,
                created_by_user_id=triggered_by_user_id,
                mode=mode,
                demo_run_id=demo_run_id,
                route_metadata={
                    "vehicle_capacity": actual_vehicle.capacity,
                    "assigned_stop_ids": [wp["stop_id"] for wp in waypoint_payloads if wp["stop_id"] is not None],
                    "routing_provider": "local-road-matrix",
                },
            )
            db.add(route_plan)
            db.flush()

            for sequence, waypoint in enumerate(waypoint_payloads):
                db.add(
                    RouteWaypointRecord(
                        route_plan_id=route_plan.id,
                        sequence=sequence,
                        stop_id=waypoint["stop_id"],
                        lat=waypoint["lat"],
                        lng=waypoint["lng"],
                        waypoint_type=waypoint["waypoint_type"],
                        passenger_ids=waypoint["passenger_ids"],
                    )
                )

            # Update all member ride requests to assigned
            passenger_user_ids = []
            for wp in waypoint_payloads:
                if wp["stop_id"]:
                    vs_item = next((v for v in virtual_stops if v.id == wp["stop_id"]), None)
                    if vs_item:
                        for req in vs_item.ride_requests:
                            if req.status == "clustered":
                                req.status = "assigned"
                                assigned_rides_count += 1
                                passenger_user_ids.append(req.user_id)

            passenger_user_ids = sorted(set(passenger_user_ids))
            if passenger_user_ids:
                create_notifications_for_users(
                    db,
                    user_ids=passenger_user_ids,
                    notification_type="route_assigned",
                    title="Your route has been optimized",
                    message=f"Your shared ride has been assigned to vehicle {actual_vehicle.license_plate}.",
                    related_entity_type="route_plan",
                    related_entity_id=route_plan.id,
                    metadata={"route_id": route_id, "vehicle_id": actual_vehicle.id},
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
    """
    Simulates the active ride lifecycle (assigned -> arriving -> in_progress -> completed)
    every few seconds to feed real-time WebSocket events to the frontend.
    """
    job_run = _start_job_run(db, "simulate_ride_dispatch", None, is_scheduled)
    try:
        active_rides = db.query(RideRequest).filter(
            RideRequest.status.in_(["assigned", "arriving", "in_progress"])
        ).all()

        transitions = {
            "assigned": "arriving",
            "arriving": "in_progress",
            "in_progress": "completed",
        }

        updates_count = 0
        for ride in active_rides:
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

                # If completed, check if vehicle can return to idle
                if new_status == "completed" and ride.virtual_stop_id:
                    waypoint = db.query(RouteWaypointRecord).filter(
                        RouteWaypointRecord.stop_id == ride.virtual_stop_id
                    ).first()
                    if waypoint:
                        route_plan = db.query(RoutePlan).filter(RoutePlan.id == waypoint.route_plan_id).first()
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


async def _run_periodic(name: str, interval_seconds: int, runner):
    STATE.active_tasks.append(name)
    try:
        while True:
            db = SessionLocal()
            try:
                # All job runners accept db as the first positional argument
                runner(db)
                now = datetime.now(timezone.utc)
                if name == "cluster_pending_rides":
                    STATE.last_cluster_run_at = now
                elif name == "refresh_demand_snapshots":
                    STATE.last_demand_run_at = now
                elif name == "rebalance_idle_vehicles":
                    STATE.last_rebalance_run_at = now
                elif name == "simulate_ride_dispatch":
                    STATE.last_dispatch_run_at = now
            finally:
                db.close()
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        pass
    finally:
        if name in STATE.active_tasks:
            STATE.active_tasks.remove(name)


def start_background_jobs() -> None:
    if STATE.running:
        return

    STATE.running = True
    loop = asyncio.get_running_loop()
    _TASKS.clear()
    _TASKS.append(loop.create_task(_run_periodic("cluster_pending_rides", CLUSTER_INTERVAL_SECONDS, run_cluster_job)))
    _TASKS.append(loop.create_task(_run_periodic("refresh_demand_snapshots", DEMAND_INTERVAL_SECONDS, run_demand_refresh_job)))
    _TASKS.append(loop.create_task(_run_periodic("rebalance_idle_vehicles", REBALANCE_INTERVAL_SECONDS, run_vehicle_rebalance_job)))
    _TASKS.append(loop.create_task(_run_periodic("simulate_ride_dispatch", SIMULATE_DISPATCH_INTERVAL_SECONDS, run_simulate_ride_dispatch_job)))


async def stop_background_jobs() -> None:
    if not _TASKS:
        STATE.running = False
        return
    for task in list(_TASKS):
        task.cancel()
    await asyncio.gather(*_TASKS, return_exceptions=True)
    _TASKS.clear()
    STATE.running = False


def get_background_job_state() -> Dict:
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
