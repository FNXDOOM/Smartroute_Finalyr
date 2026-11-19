from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional
import pickle

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.ride_request import RideRequest
from services.clustering.h3_partitioner import get_h3_index
from services.prediction.feature_engineering import (
    build_demand_features,
    features_to_dict,
)
from services.prediction.model_contract import FEATURE_ORDER, MODEL_PATH
from utils.ride_scope import LIVE_MODE

@lru_cache(maxsize=1)
def load_model() -> Any | None:
    if not MODEL_PATH.exists():
        return None
    with MODEL_PATH.open("rb") as handle:
        return pickle.load(handle)

def _count_historical_requests(
    db: Session,
    *,
    h3_index: str,
    lookback_days: int,
) -> int:
    threshold = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    return (
        db.query(RideRequest)
        .filter(
            RideRequest.request_time >= threshold,
            RideRequest.h3_index == h3_index,
            RideRequest.mode == LIVE_MODE,
        )
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

def demand_count_query(db: Session, threshold: datetime):
    """Grouped live-ride counts, shared by the demand jobs and EXPLAIN script."""
    return (
        db.query(RideRequest.h3_index, func.count(RideRequest.id))
        .filter(
            RideRequest.request_time >= threshold,
            RideRequest.mode == LIVE_MODE,
            RideRequest.h3_index.isnot(None),
        )
        .group_by(RideRequest.h3_index)
    )


def count_requests_by_h3(
    db: Session,
    *,
    reference_time: datetime,
    lookback_days: int,
    resolution: int = 9,
) -> Dict[str, int]:
    """One grouped query plus a small null-H3 fallback, instead of a count per zone."""
    threshold = reference_time - timedelta(days=lookback_days)
    counts = dict(demand_count_query(db, threshold).all())
    null_rows = (
        db.query(RideRequest.pickup_lat, RideRequest.pickup_lng)
        .filter(
            RideRequest.request_time >= threshold,
            RideRequest.mode == LIVE_MODE,
            RideRequest.h3_index.is_(None),
        )
        .all()
    )
    for lat, lng in null_rows:
        h3_index = get_h3_index(lat, lng, resolution=resolution)
        counts[h3_index] = counts.get(h3_index, 0) + 1
    return {key: int(value) for key, value in counts.items()}


def predict_zone_demands(
    db: Session,
    *,
    h3_indexes: Iterable[str],
    reference_time: datetime,
    lookback_days: int = 30,
    counts_by_h3: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    """Batch demand prediction: one count query and one model.predict call."""
    indexes = sorted({index for index in h3_indexes if index})
    if not indexes:
        return []
    counts = counts_by_h3 or count_requests_by_h3(
        db, reference_time=reference_time, lookback_days=lookback_days
    )
    features: List[Dict[str, int]] = []
    for h3_index in indexes:
        engineered = build_demand_features(
            h3_index=h3_index,
            reference_time=reference_time,
            historical_count=int(counts.get(h3_index, 0)),
        )
        features.append(features_to_dict(engineered))

    model = load_model()
    predictions: List[Optional[float]] = [None] * len(indexes)
    if model is not None:
        matrix = np.array(
            [[feature[column] for column in FEATURE_ORDER] for feature in features],
            dtype=float,
        )
        predictions = [float(value) for value in np.asarray(model.predict(matrix)).reshape(-1)]

    results: List[Dict[str, Any]] = []
    for h3_index, feature, prediction in zip(indexes, features, predictions):
        if prediction is None:
            predicted = _fallback_prediction(feature)
            method = "heuristic_fallback"
            model_name = "no_model_available"
        else:
            predicted = max(0.0, float(prediction))
            method = "xgboost_model"
            model_name = MODEL_PATH.name
        results.append({
            "h3_index": h3_index,
            "historical_request_count": int(feature["historical_count"]),
            "predicted_demand": predicted,
            "model_name": model_name,
            "method": method,
            "features": feature,
        })
    return results


def build_heatmap_cells(
    db: Session,
    *,
    reference_time: datetime,
    lookback_days: int,
    h3_indexes: Iterable[str],
) -> List[Dict[str, Any]]:
    return predict_zone_demands(
        db,
        h3_indexes=h3_indexes,
        reference_time=reference_time,
        lookback_days=lookback_days,
    )

