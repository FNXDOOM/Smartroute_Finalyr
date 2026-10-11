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
    """HDBSCAN leaf selection (finest clusters inside a 300 m epsilon), DBSCAN fallback; -1 labels are noise."""
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
        # All noise: fall back to DBSCAN.
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
    """Group requests by cluster label, dropping noise (-1)."""
    groups: dict = {}
    for req, label in zip(requests, labels):
        if label == -1:
            continue
        groups.setdefault(int(label), []).append(req)
    return groups
