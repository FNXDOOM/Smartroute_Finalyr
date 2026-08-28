from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class VehicleBase(BaseModel):
    license_plate: str = Field(..., min_length=2, max_length=32)
    capacity: int = Field(..., gt=0, le=100, description="Seating capacity of vehicle")
    status: Optional[Literal["idle", "active", "en_route", "offline"]] = "idle"
    lat: Optional[float] = Field(None, ge=-90, le=90, allow_inf_nan=False)
    lng: Optional[float] = Field(None, ge=-180, le=180, allow_inf_nan=False)


class VehicleCreate(VehicleBase):
    pass


class VehicleUpdate(BaseModel):
    status: Optional[Literal["idle", "active", "en_route", "offline"]] = None
    lat: Optional[float] = Field(None, ge=-90, le=90, allow_inf_nan=False)
    lng: Optional[float] = Field(None, ge=-180, le=180, allow_inf_nan=False)
    assigned_route_id: Optional[str] = Field(None, max_length=100)
    driver_user_id: Optional[int] = Field(None, gt=0)


class VehicleLocationUpdate(BaseModel):
    lat: float
    lng: float


class VehicleResponse(VehicleBase):
    id: int
    mode: str = "live"
    assigned_route_id: Optional[str] = None
    driver_user_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VehicleAssignmentCandidate(BaseModel):
    id: int
    lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False)
    capacity: int = Field(..., gt=0, le=100)


class RouteAssignmentCandidate(BaseModel):
    route_id: str = Field(..., min_length=1, max_length=100)
    lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False)
    passenger_count: int = Field(default=0, ge=0, le=100)


class VehicleAssignmentRequest(BaseModel):
    vehicle_ids: Optional[List[int]] = Field(None, max_length=100)
    route_candidates: List[RouteAssignmentCandidate] = Field(..., min_length=1, max_length=500)


class VehicleAssignmentItem(BaseModel):
    vehicle_id: int
    route_id: str
    cost_meters: int


class VehicleAssignmentResponse(BaseModel):
    status: str
    assignments: List[VehicleAssignmentItem]
    unassigned_vehicle_ids: List[int] = Field(default_factory=list)
    unassigned_route_ids: List[str] = Field(default_factory=list)
