from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class RouteWaypoint(BaseModel):
    stop_id: Optional[int] = None
    lat: float
    lng: float
    waypoint_type: str  # pickup | dropoff | depot
    passenger_ids: List[int] = Field(default_factory=list)


class VRPRequest(BaseModel):
    vehicle_ids: List[int]
    virtual_stop_ids: List[int]
    depot_lat: float
    depot_lng: float
    source_cluster_run_id: Optional[int] = None


class RouteSolution(BaseModel):
    route_id: str
    vehicle_id: int
    waypoints: List[RouteWaypoint]
    total_distance_meters: float
    estimated_duration_seconds: float


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
