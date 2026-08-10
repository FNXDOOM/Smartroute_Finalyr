from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models.ride_request import RideRequest
from models.user import User
from schemas.predict import (
    DemandHeatmapCell,
    DemandHeatmapResponse,
    DemandPredictionResult,
)
from services.clustering.h3_partitioner import get_h3_index
from services.prediction.feature_engineering import get_h3_center
from services.prediction.demand_model import build_heatmap_cells, predict_zone_demand
from utils.auth_utils import get_current_user

router = APIRouter()



@router.get("/demand", response_model=DemandPredictionResult)
def predict_demand_for_point(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    resolution: int = Query(9, ge=0, le=15),
    reference_time: Optional[datetime] = Query(None),
    lookback_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    h3_index = get_h3_index(latitude, longitude, resolution=resolution)
    ref_time = reference_time or datetime.now(timezone.utc)
    prediction = predict_zone_demand(
        db,
        h3_index=h3_index,
        reference_time=ref_time,
        lookback_days=lookback_days,
    )
    return DemandPredictionResult(
        h3_index=h3_index,
        latitude=latitude,
        longitude=longitude,
        resolution=resolution,
        reference_time=ref_time,
        historical_request_count=prediction["historical_request_count"],
        predicted_demand=prediction["predicted_demand"],
        model_name=prediction["model_name"],
        method=prediction["method"],
    )


@router.get("/heatmap", response_model=DemandHeatmapResponse)
def predict_demand_heatmap(
    min_lat: float = Query(..., ge=-90, le=90),
    min_lng: float = Query(..., ge=-180, le=180),
    max_lat: float = Query(..., ge=-90, le=90),
    max_lng: float = Query(..., ge=-180, le=180),
    resolution: int = Query(9, ge=0, le=15),
    reference_time: Optional[datetime] = Query(None),
    lookback_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if min_lat > max_lat or min_lng > max_lng:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bounding box coordinates",
        )

    threshold = reference_time or datetime.now(timezone.utc)
    query = (
        db.query(RideRequest)
        .filter(
            RideRequest.request_time >= threshold - timedelta(days=lookback_days),
            RideRequest.pickup_lat >= min_lat,
            RideRequest.pickup_lat <= max_lat,
            RideRequest.pickup_lng >= min_lng,
            RideRequest.pickup_lng <= max_lng,
        )
        .order_by(RideRequest.request_time.desc())
    )
    rides = query.all()

    grouped_h3_indexes: Dict[str, int] = defaultdict(int)
    for ride in rides:
        h3_index = ride.h3_index or get_h3_index(ride.pickup_lat, ride.pickup_lng, resolution=resolution)
        grouped_h3_indexes[h3_index] += 1

    if not grouped_h3_indexes:
        return DemandHeatmapResponse(status="ok", reference_time=threshold, cells=[])

    cells_payload = build_heatmap_cells(
        db,
        reference_time=threshold,
        lookback_days=lookback_days,
        h3_indexes=grouped_h3_indexes.keys(),
    )

    cells: List[DemandHeatmapCell] = []
    for cell in cells_payload:
        cell_lat, cell_lng = get_h3_center(cell["h3_index"])
        cells.append(
            DemandHeatmapCell(
                h3_index=cell["h3_index"],
                latitude=cell_lat,
                longitude=cell_lng,
                historical_request_count=cell["historical_request_count"],
                predicted_demand=cell["predicted_demand"],
            )
        )

    return DemandHeatmapResponse(status="ok", reference_time=threshold, cells=cells)
