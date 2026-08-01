from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class AnalyticsOverviewResponse(BaseModel):
    status: str
    generated_at: datetime
    total_rides: int
    rides_by_status: Dict[str, int]
    total_vehicles: int
    idle_vehicles: int
    active_vehicles: int
    total_virtual_stops: int
    total_cluster_runs: int
    total_route_plans: int
    total_tracking_events: int
    avg_passengers_per_virtual_stop: float
    avg_route_distance_meters: float
    avg_trip_distance_meters: float
    route_utilization_percent: float


class AnalyticsDailyPoint(BaseModel):
    day: date
    ride_requests: int
    clustered_rides: int
    completed_rides: int
    cancelled_rides: int
    route_plans: int

    model_config = ConfigDict(from_attributes=True)


class AnalyticsDailyResponse(BaseModel):
    status: str
    start_date: date
    end_date: date
    points: List[AnalyticsDailyPoint]

