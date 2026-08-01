from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.cluster_run import ClusterRun
from backend.models.route_plan import RoutePlan
from backend.models.tracking_event import TrackingEvent
from backend.models.user import User
from backend.models.vehicle import Vehicle
from backend.models.ride_request import RideRequest
from backend.models.virtual_stop import VirtualStop
from backend.schemas.analytics import AnalyticsDailyPoint, AnalyticsDailyResponse, AnalyticsOverviewResponse
from backend.utils.auth_utils import get_current_user

router = APIRouter()


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * radius * asin(sqrt(a))


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

    rides = db.query(RideRequest).all()
    vehicles = db.query(Vehicle).all()
    virtual_stops = db.query(VirtualStop).all()
    cluster_runs = db.query(ClusterRun).all()
    route_plans = db.query(RoutePlan).all()
    tracking_events = db.query(TrackingEvent).all()

    rides_by_status = Counter(ride.status for ride in rides)
    total_rides = len(rides)
    total_vehicles = len(vehicles)
    idle_vehicles = sum(1 for vehicle in vehicles if vehicle.status == "idle")
    active_vehicles = sum(1 for vehicle in vehicles if vehicle.status != "idle")
    total_virtual_stops = len(virtual_stops)
    total_cluster_runs = len(cluster_runs)
    total_route_plans = len(route_plans)
    total_tracking_events = len(tracking_events)

    avg_passengers_per_virtual_stop = (
        sum(stop.passenger_count or 0 for stop in virtual_stops) / total_virtual_stops
        if total_virtual_stops
        else 0.0
    )

    avg_route_distance_meters = (
        sum(float(route.total_distance_meters or 0.0) for route in route_plans) / total_route_plans
        if total_route_plans
        else 0.0
    )

    avg_trip_distance_meters = 0.0
    if rides:
        total_trip_distance = 0.0
        for ride in rides:
            total_trip_distance += _haversine_meters(
                ride.pickup_lat,
                ride.pickup_lng,
                ride.dest_lat,
                ride.dest_lng,
            )
        avg_trip_distance_meters = total_trip_distance / total_rides

    stops_by_id = {stop.id: stop for stop in virtual_stops}
    total_passengers_assigned = sum(_route_passenger_count(route, stops_by_id) for route in route_plans)
    total_vehicle_capacity = sum(vehicle.capacity or 0 for vehicle in vehicles)
    route_utilization_percent = (
        (total_passengers_assigned / total_vehicle_capacity) * 100.0
        if total_vehicle_capacity
        else 0.0
    )

    return AnalyticsOverviewResponse(
        status="ok",
        generated_at=datetime.utcnow(),
        total_rides=total_rides,
        rides_by_status=dict(rides_by_status),
        total_vehicles=total_vehicles,
        idle_vehicles=idle_vehicles,
        active_vehicles=active_vehicles,
        total_virtual_stops=total_virtual_stops,
        total_cluster_runs=total_cluster_runs,
        total_route_plans=total_route_plans,
        total_tracking_events=total_tracking_events,
        avg_passengers_per_virtual_stop=round(avg_passengers_per_virtual_stop, 2),
        avg_route_distance_meters=round(avg_route_distance_meters, 2),
        avg_trip_distance_meters=round(avg_trip_distance_meters, 2),
        route_utilization_percent=round(route_utilization_percent, 2),
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

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days - 1)

    rides = db.query(RideRequest).all()
    route_plans = db.query(RoutePlan).all()

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
