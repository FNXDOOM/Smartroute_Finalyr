from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from schemas.virtual_stop import VirtualStopResponse


class ClusterTriggerRequest(BaseModel):
    resolution: int = Field(default=9, ge=0, le=15, description="H3 spatial resolution")
    min_cluster_size: int = Field(default=2, ge=1, le=100, description="Minimum HDBSCAN cluster size")


class ClusterGroup(BaseModel):
    cluster_id: int
    h3_index: str
    ride_request_ids: List[int]
    virtual_stop: VirtualStopResponse


class ClusterResultResponse(BaseModel):
    cluster_run_id: int | None = None
    status: str
    total_processed_requests: int
    clusters_formed: int
    noise_requests_count: int
    virtual_stops: List[VirtualStopResponse]
    clusters: List[ClusterGroup]


class ClusterRunSummary(BaseModel):
    id: int
    run_uuid: str
    resolution: int
    min_cluster_size: int
    status: str
    total_processed_requests: int
    clusters_formed: int
    noise_requests_count: int
    created_by_user_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ClusterRunResponse(ClusterRunSummary):
    cluster_summary: Optional[list] = None


class ClusterHistoryResponse(BaseModel):
    status: str
    runs: List[ClusterRunSummary]
