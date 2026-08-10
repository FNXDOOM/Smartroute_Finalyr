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
from models.vehicle import Vehicle
from models.vehicle_rebalance_suggestion import VehicleRebalanceSuggestion
from models.virtual_stop import VirtualStop
from services.clustering.h3_partitioner import get_h3_index, partition_requests
from services.clustering.hdbscan_clusterer import cluster_passengers, get_cluster_groups
from services.prediction.demand_model import predict_zone_demand
from services.prediction.feature_engineering import get_h3_center
from services.stops.road_snapper import build_road_graph, snap_to_road
from services.stops.virtual_stop_generator import generate_virtual_stops
from services.notifications import create_notification
from utils.geo import haversine_meters as _haversine_meters

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
) -> Dict:
    job_run = _start_job_run(db, "cluster_pending_rides", triggered_by_user_id, is_scheduled)
    try:
        requests = (
            db.query(RideRequest)
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
        rides = db.query(RideRequest).filter(RideRequest.request_time >= threshold).all()
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
        idle_vehicles = db.query(Vehicle).filter(Vehicle.status == "idle").order_by(Vehicle.id.asc()).all()
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
        rides = db.query(RideRequest).filter(RideRequest.request_time >= threshold).all()
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


def run_simulate_ride_dispatch_job(db: Session, is_scheduled: bool = True) -> Dict:
    """
    Simulates the ride lifecycle (pending -> assigned -> arriving -> in_progress -> completed)
    every few seconds to feed real-time WebSocket events to the frontend.
    """
    job_run = _start_job_run(db, "simulate_ride_dispatch", None, is_scheduled)
    try:
        # We process pending, clustered, assigned, arriving, and in_progress rides.
        # Note: We won't strictly enforce 5s using request_time, we'll just progress them by one state 
        # on each run if they've been in their current state for a few seconds. 
        # For simplicity, we just bump the state of everything that is active.
        active_rides = db.query(RideRequest).filter(
            RideRequest.status.in_(["pending", "clustered", "assigned", "arriving", "in_progress"])
        ).all()

        transitions = {
            "pending": "assigned",
            "clustered": "assigned",
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
                
                # Create a notification to trigger a WebSocket push to the user
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
