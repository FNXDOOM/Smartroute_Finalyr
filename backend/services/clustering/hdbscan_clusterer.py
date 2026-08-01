import numpy as np
from math import radians, cos, sin, asin, sqrt
from typing import List, Tuple


def _extract_pickup_coords(request) -> Tuple[float, float]:
    if hasattr(request, "pickup_lat") and hasattr(request, "pickup_lng"):
        return float(request.pickup_lat), float(request.pickup_lng)
    if hasattr(request, "lat") and hasattr(request, "lng"):
        return float(request.lat), float(request.lng)
    return float(request["pickup_lat"]), float(request["pickup_lng"])


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance in meters between two lat/lng points."""
    R = 6_371_000
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * R * asin(sqrt(a))


def cluster_passengers(
    requests: list, min_cluster_size: int = 2
) -> np.ndarray:
    """
    Apply HDBSCAN clustering to passenger pickup locations.
    Returns array of integer cluster labels (-1 = noise/outlier).
    Falls back to DBSCAN (via sklearn) if hdbscan is unavailable.
    """
    coords = np.array([_extract_pickup_coords(r) for r in requests], dtype=float)

    # Need at least min_cluster_size points to form a cluster
    if len(coords) < min_cluster_size:
        return np.array([-1] * len(coords))

    try:
        import hdbscan
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="haversine",
            cluster_selection_epsilon=0.0005,  # ~55m in radians
        )
        labels = clusterer.fit_predict(np.radians(coords))
    except ImportError:
        # Fallback to sklearn DBSCAN with haversine metric
        from sklearn.cluster import DBSCAN
        clusterer = DBSCAN(eps=0.001, min_samples=min_cluster_size, metric="haversine")
        labels = clusterer.fit_predict(np.radians(coords))

    return labels


def get_cluster_groups(requests: list, labels: np.ndarray) -> dict:
    """
    Groups requests by their cluster label.
    Returns dict: {cluster_id -> list of request objects}. Excludes noise (-1).
    """
    groups: dict = {}
    for req, label in zip(requests, labels):
        if label == -1:
            continue
        groups.setdefault(int(label), []).append(req)
    return groups
