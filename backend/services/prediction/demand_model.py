from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import pickle

import numpy as np
from sqlalchemy.orm import Session

from backend.models.ride_request import RideRequest
from backend.services.prediction.feature_engineering import (
    build_demand_features,
    features_to_dict,
)

MODEL_PATH = Path(__file__).resolve().parents[3] / "ml" / "models" / "demand_model.pkl"
FEATURE_ORDER = ["hour", "day_of_week", "h3_zone", "historical_count", "is_weekend"]


@lru_cache(maxsize=1)
def load_model() -> Any | None:
    if not MODEL_PATH.exists():
        return None
    with MODEL_PATH.open("rb") as handle:
        return pickle.load(handle)


def _query_historical_requests(
    db: Session,
    *,
    h3_index: Optional[str] = None,
    min_lat: Optional[float] = None,
    min_lng: Optional[float] = None,
    max_lat: Optional[float] = None,
    max_lng: Optional[float] = None,
    lookback_days: int = 30,
) -> List[RideRequest]:
    threshold = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    query = db.query(RideRequest).filter(RideRequest.request_time >= threshold)

    if h3_index:
        query = query.filter(RideRequest.h3_index == h3_index)
    if min_lat is not None:
        query = query.filter(RideRequest.pickup_lat >= min_lat)
    if max_lat is not None:
        query = query.filter(RideRequest.pickup_lat <= max_lat)
    if min_lng is not None:
        query = query.filter(RideRequest.pickup_lng >= min_lng)
    if max_lng is not None:
        query = query.filter(RideRequest.pickup_lng <= max_lng)

    return query.all()


def _count_historical_requests(
    db: Session,
    *,
    h3_index: str,
    lookback_days: int,
) -> int:
    threshold = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    return (
        db.query(RideRequest)
        .filter(RideRequest.request_time >= threshold, RideRequest.h3_index == h3_index)
        .count()
    )


def _predict_with_model(features: Dict[str, int]) -> Optional[float]:
    model = load_model()
    if model is None:
        return None

    vector = np.array([[features[column] for column in FEATURE_ORDER]], dtype=float)
    prediction = model.predict(vector)
    return float(np.asarray(prediction).reshape(-1)[0])


def _fallback_prediction(features: Dict[str, int]) -> float:
    demand = float(features["historical_count"])
    hour = features["hour"]
    day_of_week = features["day_of_week"]
    is_weekend = features["is_weekend"]

    if 7 <= hour <= 10 or 17 <= hour <= 20:
        demand *= 1.35
    elif 22 <= hour or hour <= 5:
        demand *= 0.8
    else:
        demand *= 1.0

    if is_weekend:
        demand *= 0.9
    if day_of_week == 0:
        demand *= 1.05

    return max(0.0, round(demand + 0.5, 2))


def predict_zone_demand(
    db: Session,
    *,
    h3_index: str,
    reference_time: datetime,
    lookback_days: int = 30,
) -> Dict[str, Any]:
    historical_count = _count_historical_requests(db, h3_index=h3_index, lookback_days=lookback_days)
    engineered = build_demand_features(
        h3_index=h3_index,
        reference_time=reference_time,
        historical_count=historical_count,
    )
    feature_dict = features_to_dict(engineered)
    model_prediction = _predict_with_model(feature_dict)
    if model_prediction is None:
        predicted_demand = _fallback_prediction(feature_dict)
        method = "heuristic_fallback"
        model_name = "no_model_available"
    else:
        predicted_demand = max(0.0, float(model_prediction))
        method = "xgboost_model"
        model_name = MODEL_PATH.name

    return {
        "h3_index": h3_index,
        "historical_request_count": historical_count,
        "predicted_demand": predicted_demand,
        "model_name": model_name,
        "method": method,
        "features": feature_dict,
    }


def build_heatmap_cells(
    db: Session,
    *,
    reference_time: datetime,
    lookback_days: int,
    h3_indexes: Iterable[str],
) -> List[Dict[str, Any]]:
    cells: List[Dict[str, Any]] = []
    for h3_index in sorted(set(h3_indexes)):
        result = predict_zone_demand(
            db,
            h3_index=h3_index,
            reference_time=reference_time,
            lookback_days=lookback_days,
        )
        cells.append(result)
    return cells

