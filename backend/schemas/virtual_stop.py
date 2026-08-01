from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class VirtualStopBase(BaseModel):
    cluster_id: int
    h3_index: Optional[str] = None
    lat: float
    lng: float
    snapped_node_id: Optional[str] = None
    passenger_count: int = 0


class VirtualStopCreate(VirtualStopBase):
    pass


class VirtualStopResponse(VirtualStopBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
