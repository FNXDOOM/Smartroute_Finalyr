from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class RideRequestBase(BaseModel):
    pickup_lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False, description="Pickup latitude")
    pickup_lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False, description="Pickup longitude")
    dest_lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False, description="Destination latitude")
    dest_lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False, description="Destination longitude")
    # Optional human-readable labels from the mobile client
    pickup_label: Optional[str] = Field(None, max_length=200)
    destination_label: Optional[str] = Field(None, max_length=200)
    ride_option_id: Optional[str] = Field(None, max_length=40)
    ride_option_name: Optional[str] = Field(None, max_length=80)
    ride_option_price: Optional[str] = Field(None, max_length=40)


class RideRequestCreate(RideRequestBase):
    pass


class RideRequestStatusUpdate(BaseModel):
    status: str = Field(..., max_length=20, description="pending | clustered | assigned | in_progress | completed | cancelled")


class RideRequestResponse(RideRequestBase):
    id: int
    user_id: int
    status: str
    mode: str = "live"
    demo_run_id: Optional[str] = None
    h3_index: Optional[str] = None
    cluster_id: Optional[int] = None
    virtual_stop_id: Optional[int] = None
    request_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RideRequestBatchCreate(BaseModel):
    requests: List[RideRequestCreate] = Field(..., min_length=1, max_length=100)
