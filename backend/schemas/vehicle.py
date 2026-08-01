from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class VehicleBase(BaseModel):
    license_plate: str
    capacity: int = Field(..., gt=0, description="Seating capacity of vehicle")
    status: Optional[str] = "idle"  # idle | active | en_route | offline
    lat: Optional[float] = None
    lng: Optional[float] = None


class VehicleCreate(VehicleBase):
    pass


class VehicleUpdate(BaseModel):
    status: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    assigned_route_id: Optional[str] = None


class VehicleLocationUpdate(BaseModel):
    lat: float
    lng: float


class VehicleResponse(VehicleBase):
    id: int
    assigned_route_id: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VehicleAssignmentCandidate(BaseModel):
    id: int
    lat: float
    lng: float
    capacity: int


class RouteAssignmentCandidate(BaseModel):
    route_id: str
    lat: float
    lng: float
    passenger_count: int = 0


class VehicleAssignmentRequest(BaseModel):
    vehicle_ids: Optional[List[int]] = None
    route_candidates: List[RouteAssignmentCandidate]


class VehicleAssignmentItem(BaseModel):
    vehicle_id: int
    route_id: str
    cost_meters: int


class VehicleAssignmentResponse(BaseModel):
    status: str
    assignments: List[VehicleAssignmentItem]
    unassigned_vehicle_ids: List[int] = Field(default_factory=list)
    unassigned_route_ids: List[str] = Field(default_factory=list)
