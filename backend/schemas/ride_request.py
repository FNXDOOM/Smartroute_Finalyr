from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class RideRequestBase(BaseModel):
    pickup_lat: float = Field(..., ge=-90, le=90, description="Pickup latitude")
    pickup_lng: float = Field(..., ge=-180, le=180, description="Pickup longitude")
    dest_lat: float = Field(..., ge=-90, le=90, description="Destination latitude")
    dest_lng: float = Field(..., ge=-180, le=180, description="Destination longitude")
    # Optional human-readable labels from the mobile client
    pickup_label: Optional[str] = None
    destination_label: Optional[str] = None
    ride_option_id: Optional[str] = None
    ride_option_name: Optional[str] = None
    ride_option_price: Optional[str] = None


class RideRequestCreate(RideRequestBase):
    pass


class RideRequestStatusUpdate(BaseModel):
    status: str = Field(..., description="pending | clustered | assigned | in_progress | completed | cancelled")


class RideRequestResponse(RideRequestBase):
    id: int
    user_id: int
    status: str
    h3_index: Optional[str] = None
    cluster_id: Optional[int] = None
    virtual_stop_id: Optional[int] = None
    request_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RideRequestBatchCreate(BaseModel):
    requests: List[RideRequestCreate]
