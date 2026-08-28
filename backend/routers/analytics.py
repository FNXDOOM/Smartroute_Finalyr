from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.cluster_run import ClusterRun
from models.route_plan import RoutePlan
from models.tracking_event import TrackingEvent
from models.user import User
from models.vehicle import Vehicle
from models.ride_request import RideRequest
from models.virtual_stop import VirtualStop
from schemas.analytics import AnalyticsDailyPoint, AnalyticsDailyResponse, AnalyticsOverviewResponse
from utils.auth_utils import get_current_user
from utils.geo import haversine_meters
from utils.ride_scope import LIVE_MODE

router = APIRouter()


def _require_admin_or_driver(current_user: User) -> None:
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view analytics",
        )


def _route_passenger_count(route: RoutePlan, stops_by_id: Dict[int, VirtualStop]) -> int:
    assigned_stop_ids = []
    if route.route_metadata and isinstance(route.route_metadata, dict):
        assigned_stop_ids = route.route_metadata.get("assigned_stop_ids", []) or []
    total = 0
    for stop_id in assigned_stop_ids:
        stop = stops_by_id.get(stop_id)
        if stop:
            total += int(stop.passenger_count or 0)
    return total


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_or_driver(current_user)

    # Use aggregation queries instead of loading entire tables into memory
    total_rides = db.query(func.count(RideRequest.id)).filter(RideRequest.mode == LIVE_MODE).scalar() or 0
    total_vehicles = db.query(func.count(Vehicle.id)).filter(Vehicle.mode == LIVE_MODE).scalar() or 0
    total_virtual_stops = db.query(func.count(VirtualStop.id)).filter(VirtualStop.mode == LIVE_MODE).scalar() or 0
    total_cluster_runs = db.query(func.count(ClusterRun.id)).filter(ClusterRun.mode == LIVE_MODE).scalar() or 0
    total_route_plans = db.query(func.count(RoutePlan.id)).filter(RoutePlan.mode == LIVE_MODE).scalar() or 0
    total_tracking_events = db.query(func.count(TrackingEvent.id)).scalar() or 0

    # Status breakdown via GROUP BY
    status_rows = (
        db.query(RideRequest.status, func.count(RideRequest.id))
        .filter(RideRequest.mode == LIVE_MODE)
        .group_by(RideRequest.status)
        .all()
    )
    rides_by_status = {row[0]: row[1] for row in status_rows}

    # Vehicle idle/active counts via GROUP BY
    vehicle_status_rows = (
        db.query(Vehicle.status, func.count(Vehicle.id))
        .filter(Vehicle.mode == LIVE_MODE)
        .group_by(Vehicle.status)
        .all()
    )
    idle_vehicles = 0
    active_vehicles = 0
    for vst, cnt in vehicle_status_rows:
        if vst == "idle":
            idle_vehicles = cnt
        else:
            active_vehicles += cnt

    # Average passengers per virtual stop
    avg_passengers_row = db.query(func.avg(VirtualStop.passenger_count)).filter(VirtualStop.mode == LIVE_MODE).scalar()
    avg_passengers_per_virtual_stop = round(float(avg_passengers_row or 0.0), 2)

    # Average route distance
    avg_route_dist_row = db.query(func.avg(RoutePlan.total_distance_meters)).filter(RoutePlan.mode == LIVE_MODE).scalar()
    avg_route_distance_meters = round(float(avg_route_dist_row or 0.0), 2)

    # Average trip distance — computed over a capped sample to stay memory-safe
    SAMPLE_LIMIT = 1000
    ride_sample = (
        db.query(
            RideRequest.pickup_lat,
            RideRequest.pickup_lng,
            RideRequest.dest_lat,
            RideRequest.dest_lng,
        )
        .filter(RideRequest.mode == LIVE_MODE)
        .limit(SAMPLE_LIMIT)
        .all()
    )
    avg_trip_distance_meters = 0.0
    if ride_sample:
        total_dist = sum(
            haversine_meters(r.pickup_lat, r.pickup_lng, r.dest_lat, r.dest_lng)
            for r in ride_sample
        )
        avg_trip_distance_meters = round(total_dist / len(ride_sample), 2)

    # Route utilisation — aggregate stop passenger counts for assigned stops
    route_meta_rows = (
        db.query(RoutePlan.route_metadata)
        .filter(RoutePlan.mode == LIVE_MODE)
        .limit(500)
    )
    total_passengers_assigned = 0
    all_stop_ids: List[int] = []
    for (meta,) in route_meta_rows:
        if meta and isinstance(meta, dict):
            all_stop_ids.extend(meta.get("assigned_stop_ids", []) or [])

    if all_stop_ids:
        stop_passenger_rows = (
            db.query(VirtualStop.id, VirtualStop.passenger_count)
            .filter(VirtualStop.id.in_(set(all_stop_ids)))
            .all()
        )
        stop_map = {sid: (pc or 0) for sid, pc in stop_passenger_rows}
        total_passengers_assigned = sum(stop_map.get(sid, 0) for sid in all_stop_ids)

    total_vehicle_capacity_row = db.query(func.sum(Vehicle.capacity)).filter(Vehicle.mode == LIVE_MODE).scalar()
    total_vehicle_capacity = int(total_vehicle_capacity_row or 0)
    route_utilization_percent = (
        round((total_passengers_assigned / total_vehicle_capacity) * 100.0, 2)
        if total_vehicle_capacity
        else 0.0
    )

    return AnalyticsOverviewResponse(
        status="ok",
        generated_at=datetime.now(timezone.utc),
        total_rides=total_rides,
        rides_by_status=rides_by_status,
        total_vehicles=total_vehicles,
        idle_vehicles=idle_vehicles,
        active_vehicles=active_vehicles,
        total_virtual_stops=total_virtual_stops,
        total_cluster_runs=total_cluster_runs,
        total_route_plans=total_route_plans,
        total_tracking_events=total_tracking_events,
        avg_passengers_per_virtual_stop=avg_passengers_per_virtual_stop,
        avg_route_distance_meters=avg_route_distance_meters,
        avg_trip_distance_meters=avg_trip_distance_meters,
        route_utilization_percent=route_utilization_percent,
    )


@router.get("/daily", response_model=AnalyticsDailyResponse)
def get_analytics_daily(
    days: int = 14,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_or_driver(current_user)

    if days < 1 or days > 90:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="days must be between 1 and 90",
        )

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)
    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)

    # Only fetch rides within the requested window
    rides = (
        db.query(RideRequest)
        .filter(RideRequest.request_time >= start_dt, RideRequest.mode == LIVE_MODE)
        .all()
    )
    route_plans = (
        db.query(RoutePlan)
        .filter(RoutePlan.created_at >= start_dt, RoutePlan.mode == LIVE_MODE)
        .all()
    )

    points_by_day: Dict[date, AnalyticsDailyPoint] = {}
    for offset in range(days):
        day_value = start_date + timedelta(days=offset)
        points_by_day[day_value] = AnalyticsDailyPoint(
            day=day_value,
            ride_requests=0,
            clustered_rides=0,
            completed_rides=0,
            cancelled_rides=0,
            route_plans=0,
        )

    for ride in rides:
        if not ride.request_time:
            continue
        ride_day = ride.request_time.date()
        point = points_by_day.get(ride_day)
        if not point:
            continue
        point.ride_requests += 1
        if ride.status == "clustered":
            point.clustered_rides += 1
        elif ride.status == "completed":
            point.completed_rides += 1
        elif ride.status == "cancelled":
            point.cancelled_rides += 1

    for route in route_plans:
        if not route.created_at:
            continue
        route_day = route.created_at.date()
        point = points_by_day.get(route_day)
        if point:
            point.route_plans += 1

    return AnalyticsDailyResponse(
        status="ok",
        start_date=start_date,
        end_date=end_date,
        points=list(points_by_day.values()),
    )
