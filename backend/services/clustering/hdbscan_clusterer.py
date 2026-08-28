import numpy as np
from typing import List, Tuple

from utils.geo import haversine_meters


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
    Apply density-based clustering to passenger pickup locations.
    Returns array of integer cluster labels (-1 = noise/outlier).

    Strategy
    --------
    1. Primary: HDBSCAN with ``cluster_selection_method='leaf'`` and
       ``cluster_selection_epsilon`` set to 300 m in radians.  This mode
       picks the finest-grained clusters that sit within the epsilon
       neighbourhood, which is the correct behaviour for ride-sharing grouping.
    2. Fallback: sklearn DBSCAN with the same epsilon if hdbscan is not installed.

    The 300 m radius comfortably groups passengers waiting on the same block
    or within a typical shared-taxi boarding window.
        300 m / 6_371_000 m ≈ 4.71e-5 rad
    """
    coords = np.array([_extract_pickup_coords(r) for r in requests], dtype=float)

    if len(coords) < min_cluster_size:
        return np.array([-1] * len(coords))

    # 300 m expressed in radians for haversine
    epsilon_rad = 300.0 / 6_371_000

    try:
        import hdbscan as _hdbscan
        clusterer = _hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=1,
            metric="haversine",
            cluster_selection_epsilon=epsilon_rad,
            cluster_selection_method="leaf",
        )
        labels = clusterer.fit_predict(np.radians(coords))
        # If HDBSCAN still produces all noise (can happen with very few points),
        # fall through to DBSCAN which is more reliable for small, tight groups.
        if (labels == -1).all():
            raise ValueError("HDBSCAN produced all-noise; using DBSCAN fallback")
    except Exception:
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
