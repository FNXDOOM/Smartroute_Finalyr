from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobRunResponse(BaseModel):
    id: int
    job_name: str
    status: str
    triggered_by_user_id: Optional[int] = None
    is_scheduled: bool
    summary: Optional[dict] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DemandSnapshotResponse(BaseModel):
    id: int
    job_run_id: int
    h3_index: str
    lat: float
    lng: float
    lookback_days: int
    historical_request_count: int
    predicted_demand: float
    model_name: Optional[str] = None
    method: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class VehicleRebalanceSuggestionResponse(BaseModel):
    id: int
    job_run_id: int
    vehicle_id: int
    target_h3_index: str
    target_lat: float
    target_lng: float
    score: float
    reason: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BackgroundJobStatusResponse(BaseModel):
    status: str
    scheduler_running: bool
    cluster_interval_seconds: int
    demand_interval_seconds: int
    rebalance_interval_seconds: int
    last_cluster_run_at: Optional[datetime] = None
    last_demand_run_at: Optional[datetime] = None
    last_rebalance_run_at: Optional[datetime] = None
    active_tasks: List[str] = Field(default_factory=list)

