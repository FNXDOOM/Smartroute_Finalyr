from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class RideRequestBase(BaseModel):
    pickup_lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False, description="Pickup latitude")
    pickup_lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False, description="Pickup longitude")
    dest_lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False, description="Destination latitude")
    dest_lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False, description="Destination longitude")
    pickup_label: Optional[str] = Field(None, max_length=200)
    destination_label: Optional[str] = Field(None, max_length=200)
    ride_option_id: Optional[str] = Field(None, max_length=40)
    ride_option_name: Optional[str] = Field(None, max_length=80)
    ride_option_price: Optional[str] = Field(None, max_length=40)
    # Carpool vs private; default keeps existing clients pooling.
    is_shared: bool = True


class RideRequestCreate(RideRequestBase):
    pass


class RideRequestStatusUpdate(BaseModel):
    status: str = Field(..., max_length=30, description="pending | clustered | assigned | arriving | ready_for_pickup | in_progress | completed | cancelled")


class RideRequestResponse(RideRequestBase):
    id: int
    user_id: int
    status: str
    mode: str = "live"
    demo_run_id: Optional[str] = None
    h3_index: Optional[str] = None
    cluster_id: Optional[int] = None
    virtual_stop_id: Optional[int] = None
    # Fine per-rider carpool stage (see utils/carpool_status.py), null for private rides; additive, so clients reading only ``status`` are unaffected.
    carpool_status: Optional[str] = None
    request_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RideRequestBatchCreate(BaseModel):
    requests: List[RideRequestCreate] = Field(..., min_length=1, max_length=100)


class DemoSharedBatchCreate(BaseModel):
    demo_run_id: str = Field(..., min_length=1, max_length=64)
    riders: List[RideRequestCreate] = Field(..., min_length=1, max_length=3)


class RideRouteLeg(BaseModel):
    """One leg of a pooled route: the drive between two consecutive stops."""

    index: int
    geometry: List[List[float]] = Field(default_factory=list)
    distance_meters: float = 0
    duration_seconds: float = 0
    from_sequence: Optional[int] = None
    to_sequence: Optional[int] = None


class RideRouteStop(BaseModel):
    sequence: int
    lat: float
    lng: float
    waypoint_type: str = Field(..., description="depot | pickup | destination")
    passenger_count: int = 0
    is_mine: bool = False
    walk_meters: Optional[float] = None


class RideRouteResponse(BaseModel):
    """The pooled route as the passenger's map draws it; `stops` covers the whole shared route and `is_mine` marks the ones this passenger uses."""

    route_id: str
    vehicle_id: int
    provider: str = "unknown"
    problem: str = "pdp"
    geometry: List[List[float]] = Field(default_factory=list)
    legs: List[RideRouteLeg] = Field(default_factory=list)
    stops: List[RideRouteStop] = Field(default_factory=list)
    my_pickup_sequence: Optional[int] = None
    my_destination_sequence: Optional[int] = None
    my_pickup_walk_meters: Optional[float] = None
    my_pickup_stop_lat: Optional[float] = None
    my_pickup_stop_lng: Optional[float] = None
    my_leg_indices: List[int] = Field(default_factory=list)
    total_distance_meters: float = 0
    estimated_duration_seconds: float = 0
    # Carpool lifecycle surfaced to the passenger: driver acceptance of the run, the route's own state, and this rider's fine stage (utils/carpool_status.py).
    driver_accepted: bool = False
    route_status: str = "solved"
    carpool_status: Optional[str] = None
