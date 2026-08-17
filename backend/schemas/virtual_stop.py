from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class VirtualStopBase(BaseModel):
    cluster_id: int
    h3_index: Optional[str] = None
    lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False)
    snapped_node_id: Optional[str] = Field(None, max_length=100)
    passenger_count: int = Field(default=0, ge=0, le=100)


class VirtualStopCreate(VirtualStopBase):
    pass


class VirtualStopResponse(VirtualStopBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
