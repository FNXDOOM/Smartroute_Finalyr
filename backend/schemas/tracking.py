from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class VehicleTelemetryUpdate(BaseModel):
    lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False)
    status: Optional[Literal["idle", "active", "en_route", "offline"]] = None
    payload: Optional[dict[str, Any]] = Field(default=None)


class TrackingEventResponse(BaseModel):
    id: int
    vehicle_id: Optional[int] = None
    ride_request_id: Optional[int] = None
    route_plan_id: Optional[int] = None
    event_type: str
    status: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    payload: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VehicleSnapshot(BaseModel):
    id: int
    license_plate: str
    status: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    assigned_route_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TrackingFeedResponse(BaseModel):
    status: str
    vehicles: list[VehicleSnapshot]
    events: list[TrackingEventResponse]

