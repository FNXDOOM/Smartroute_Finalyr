from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple

from backend.services.clustering.h3_partitioner import get_h3_index


@dataclass(frozen=True)
class DemandFeatures:
    hour: int
    day_of_week: int
    h3_zone: int
    historical_count: int
    is_weekend: int


def encode_h3_index(h3_index: str) -> int:
    """Stable compact encoding for a string H3 cell id."""
    return abs(hash(h3_index)) % 10_000


def build_demand_features(
    *,
    h3_index: str,
    reference_time: datetime,
    historical_count: int,
) -> DemandFeatures:
    hour = int(reference_time.hour)
    day_of_week = int(reference_time.weekday())
    is_weekend = 1 if day_of_week >= 5 else 0
    return DemandFeatures(
        hour=hour,
        day_of_week=day_of_week,
        h3_zone=encode_h3_index(h3_index),
        historical_count=int(historical_count),
        is_weekend=is_weekend,
    )


def features_to_dict(features: DemandFeatures) -> Dict[str, int]:
    return {
        "hour": features.hour,
        "day_of_week": features.day_of_week,
        "h3_zone": features.h3_zone,
        "historical_count": features.historical_count,
        "is_weekend": features.is_weekend,
    }


def ensure_h3_index(latitude: float, longitude: float, resolution: int) -> str:
    return get_h3_index(latitude, longitude, resolution=resolution)


def get_h3_center(h3_index: str) -> Tuple[float, float]:
    try:
        import h3
        if hasattr(h3, "cell_to_latlng"):
            lat, lng = h3.cell_to_latlng(h3_index)
            return float(lat), float(lng)
        if hasattr(h3, "h3_to_geo"):
            lat, lng = h3.h3_to_geo(h3_index)
            return float(lat), float(lng)
    except Exception:
        pass
    return 0.0, 0.0
