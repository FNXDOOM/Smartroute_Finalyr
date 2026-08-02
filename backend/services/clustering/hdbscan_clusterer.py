import numpy as np
from typing import List, Tuple

from backend.utils.geo import haversine_meters


def _extract_pickup_coords(request) -> Tuple[float, float]:
    if hasattr(request, "pickup_lat") and hasattr(request, "pickup_lng"):
        return float(request.pickup_lat), float(request.pickup_lng)
    if hasattr(request, "lat") and hasattr(request, "lng"):
        return float(request.lat), float(request.lng)
    return float(request["pickup_lat"]), float(request["pickup_lng"])


def cluster_passengers(
    requests: list, min_cluster_size: int = 2
) -> np.ndarray:
    """
    Apply HDBSCAN clustering to passenger pickup locations.
    Returns array of integer cluster labels (-1 = noise/outlier).
    Falls back to DBSCAN (via sklearn) if hdbscan is unavailable.

    Note: haversine metric operates on radians, so coordinates are converted
    before being passed to the clusterer.  cluster_selection_epsilon is also
    expressed in radians:
        50 m / 6_371_000 m ≈ 7.85e-6 rad  (~50 m pickup-grouping radius)
    """
    coords = np.array([_extract_pickup_coords(r) for r in requests], dtype=float)

    if len(coords) < min_cluster_size:
        return np.array([-1] * len(coords))

    # ~50 m in radians  (was incorrectly 0.0005 ≈ 3 km)
    epsilon_rad = 50.0 / 6_371_000

    try:
        import hdbscan
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="haversine",
            cluster_selection_epsilon=epsilon_rad,
        )
        labels = clusterer.fit_predict(np.radians(coords))
    except ImportError:
        # Fallback to sklearn DBSCAN with haversine metric
        from sklearn.cluster import DBSCAN
        clusterer = DBSCAN(
            eps=epsilon_rad,
            min_samples=min_cluster_size,
            metric="haversine",
        )
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
