from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

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

