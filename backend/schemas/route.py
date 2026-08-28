from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class RouteWaypoint(BaseModel):
    stop_id: Optional[int] = None
    lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False)
    waypoint_type: str = Field(..., min_length=1, max_length=20)  # pickup | dropoff | depot
    passenger_ids: List[int] = Field(default_factory=list, max_length=100)


class VRPRequest(BaseModel):
    vehicle_ids: List[int] = Field(..., min_length=1, max_length=100)
    virtual_stop_ids: List[int] = Field(..., max_length=500)
    depot_lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    depot_lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False)
    source_cluster_run_id: Optional[int] = None


class RouteSolution(BaseModel):
    route_id: str
    vehicle_id: int
    waypoints: List[RouteWaypoint]
    total_distance_meters: float
    estimated_duration_seconds: float
    geometry: List[List[float]] = Field(default_factory=list)
    maneuvers: List[dict] = Field(default_factory=list)


class OptimizedRouteResponse(BaseModel):
    status: str
    routes: List[RouteSolution]
    unassigned_stops: List[int] = Field(default_factory=list)


class RouteWaypointRecordResponse(BaseModel):
    id: int
    sequence: int
    stop_id: Optional[int] = None
    lat: float
    lng: float
    waypoint_type: str
    passenger_ids: List[int] = Field(default_factory=list)
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RoutePlanResponse(BaseModel):
    id: int
    route_id: str
    vehicle_id: int
    source_cluster_run_id: Optional[int] = None
    status: str
    depot_lat: float
    depot_lng: float
    total_distance_meters: float
    estimated_duration_seconds: float
    route_metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    waypoints: List[RouteWaypointRecordResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RouteHistoryResponse(BaseModel):
    status: str
    routes: List[RoutePlanResponse]
