from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DemandPredictionRequest(BaseModel):
    h3_index: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    resolution: int = Field(default=9, ge=0, le=15)
    reference_time: Optional[datetime] = None
    lookback_days: int = Field(default=30, ge=1, le=365)


class DemandHeatmapRequest(BaseModel):
    min_lat: float = Field(..., ge=-90, le=90)
    min_lng: float = Field(..., ge=-180, le=180)
    max_lat: float = Field(..., ge=-90, le=90)
    max_lng: float = Field(..., ge=-180, le=180)
    resolution: int = Field(default=9, ge=0, le=15)
    reference_time: Optional[datetime] = None
    lookback_days: int = Field(default=30, ge=1, le=365)


class DemandPredictionResult(BaseModel):
    h3_index: str
    latitude: float
    longitude: float
    resolution: int
    reference_time: datetime
    historical_request_count: int
    predicted_demand: float
    model_name: str
    method: str

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class DemandHeatmapCell(BaseModel):
    h3_index: str
    latitude: float
    longitude: float
    historical_request_count: int
    predicted_demand: float

    model_config = ConfigDict(from_attributes=True)


class DemandHeatmapResponse(BaseModel):
    status: str
    reference_time: datetime
    cells: List[DemandHeatmapCell]

