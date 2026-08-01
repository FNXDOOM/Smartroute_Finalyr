from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.cluster_run import ClusterRun
from backend.models.ride_request import RideRequest
from backend.models.user import User
from backend.models.virtual_stop import VirtualStop
from backend.schemas.cluster import (
    ClusterGroup,
    ClusterHistoryResponse,
    ClusterResultResponse,
    ClusterRunResponse,
    ClusterRunSummary,
    ClusterTriggerRequest,
)
from backend.schemas.virtual_stop import VirtualStopResponse
from backend.services.clustering.h3_partitioner import get_h3_index, partition_requests
from backend.services.clustering.hdbscan_clusterer import cluster_passengers, get_cluster_groups
from backend.services.stops.road_snapper import build_road_graph, snap_to_road
from backend.services.stops.virtual_stop_generator import generate_virtual_stops
from backend.utils.auth_utils import get_current_user

router = APIRouter()


def _cluster_centroid(requests: List[RideRequest]) -> tuple[float, float]:
    if not requests:
        return 0.0, 0.0
    lat_sum = sum(req.pickup_lat for req in requests)
    lng_sum = sum(req.pickup_lng for req in requests)
    return lat_sum / len(requests), lng_sum / len(requests)


@router.get("/")
def get_cluster():
    return {"message": "Cluster router"}


@router.post("/create", response_model=ClusterResultResponse, status_code=status.HTTP_201_CREATED)
@router.post("/run", response_model=ClusterResultResponse, status_code=status.HTTP_201_CREATED)
def run_clustering(
    payload: ClusterTriggerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    h3_index: Optional[str] = Query(None, description="Optional H3 index filter"),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can trigger clustering",
        )

    query = db.query(RideRequest).filter(RideRequest.status == "pending")
    if h3_index:
        query = query.filter(RideRequest.h3_index == h3_index)

    requests = query.order_by(RideRequest.request_time.asc()).all()
    if not requests:
        cluster_run = ClusterRun(
            run_uuid=str(uuid4()),
            resolution=payload.resolution,
            min_cluster_size=payload.min_cluster_size,
            status="no_pending_requests",
            total_processed_requests=0,
            clusters_formed=0,
            noise_requests_count=0,
            created_by_user_id=current_user.id,
            cluster_summary=[],
        )
        db.add(cluster_run)
        db.commit()
        db.refresh(cluster_run)
        return ClusterResultResponse(
            cluster_run_id=cluster_run.id,
            status=cluster_run.status,
            total_processed_requests=0,
            clusters_formed=0,
            noise_requests_count=0,
            virtual_stops=[],
            clusters=[],
        )

    for request in requests:
        if not request.h3_index:
            request.h3_index = get_h3_index(request.pickup_lat, request.pickup_lng, resolution=payload.resolution)

    buckets = partition_requests(requests, resolution=payload.resolution)
    next_cluster_id = (db.query(func.max(VirtualStop.cluster_id)).scalar() or 0) + 1

    created_virtual_stops: List[VirtualStopResponse] = []
    cluster_groups: List[ClusterGroup] = []
    cluster_summary_payload: List[dict] = []
    noise_count = 0

    for bucket_h3_index, bucket_requests in buckets.items():
        labels = cluster_passengers(bucket_requests, min_cluster_size=payload.min_cluster_size)
        noise_count += int((labels == -1).sum())
        grouped_requests = get_cluster_groups(bucket_requests, labels)

        for _, members in grouped_requests.items():
            centroid_lat, centroid_lng = _cluster_centroid(members)
            candidate_stops = generate_virtual_stops(members, n_stops=1)
            stop_lat, stop_lng = candidate_stops[0]

            road_graph = build_road_graph(centroid_lat, centroid_lng, dist=2500)
            snapped_lat, snapped_lng, snapped_node_id = snap_to_road(road_graph, stop_lat, stop_lng)

            virtual_stop = VirtualStop(
                cluster_id=next_cluster_id,
                h3_index=bucket_h3_index,
                lat=snapped_lat,
                lng=snapped_lng,
                snapped_node_id=snapped_node_id,
                passenger_count=len(members),
            )
            db.add(virtual_stop)
            db.flush()

            ride_ids: List[int] = []
            for request in members:
                request.cluster_id = next_cluster_id
                request.virtual_stop_id = virtual_stop.id
                request.status = "clustered"
                ride_ids.append(request.id)

            virtual_stop_response = VirtualStopResponse.model_validate(virtual_stop)
            created_virtual_stops.append(virtual_stop_response)
            cluster_groups.append(
                ClusterGroup(
                    cluster_id=next_cluster_id,
                    h3_index=bucket_h3_index,
                    ride_request_ids=ride_ids,
                    virtual_stop=virtual_stop_response,
                )
            )
            cluster_summary_payload.append(
                {
                    "cluster_id": next_cluster_id,
                    "h3_index": bucket_h3_index,
                    "ride_request_ids": ride_ids,
                    "virtual_stop_id": virtual_stop.id,
                    "virtual_stop_lat": virtual_stop.lat,
                    "virtual_stop_lng": virtual_stop.lng,
                    "passenger_count": len(members),
                    "snapped_node_id": snapped_node_id,
                }
            )
            next_cluster_id += 1

    cluster_run = ClusterRun(
        run_uuid=str(uuid4()),
        resolution=payload.resolution,
        min_cluster_size=payload.min_cluster_size,
        status="clustered",
        total_processed_requests=len(requests),
        clusters_formed=len(cluster_groups),
        noise_requests_count=noise_count,
        created_by_user_id=current_user.id,
        cluster_summary=cluster_summary_payload,
    )
    db.add(cluster_run)
    db.commit()
    db.refresh(cluster_run)

    return ClusterResultResponse(
        cluster_run_id=cluster_run.id,
        status="clustered",
        total_processed_requests=len(requests),
        clusters_formed=len(cluster_groups),
        noise_requests_count=noise_count,
        virtual_stops=created_virtual_stops,
        clusters=cluster_groups,
    )


@router.get("/history", response_model=ClusterHistoryResponse)
def list_cluster_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view cluster history",
        )

    runs = (
        db.query(ClusterRun)
        .order_by(ClusterRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return ClusterHistoryResponse(status="ok", runs=[ClusterRunSummary.model_validate(run) for run in runs])


@router.get("/history/{run_id}", response_model=ClusterRunResponse)
def get_cluster_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view cluster history",
        )

    cluster_run = db.query(ClusterRun).filter(ClusterRun.id == run_id).first()
    if not cluster_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster run not found")

    return ClusterRunResponse.model_validate(cluster_run)
