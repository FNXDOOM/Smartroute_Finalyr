import numpy as np
from typing import List, Tuple


def _extract_coords(point) -> Tuple[float, float]:
    if hasattr(point, "pickup_lat") and hasattr(point, "pickup_lng"):
        return float(point.pickup_lat), float(point.pickup_lng)
    if hasattr(point, "lat") and hasattr(point, "lng"):
        return float(point.lat), float(point.lng)
    if isinstance(point, dict):
        if "pickup_lat" in point and "pickup_lng" in point:
            return float(point["pickup_lat"]), float(point["pickup_lng"])
        return float(point["lat"]), float(point["lng"])
    raise ValueError("Unsupported point format for virtual stop generation")


def generate_virtual_stops(cluster_points: list, n_stops: int = 1) -> List[Tuple[float, float]]:
    """
    Use K-Medoids to select representative virtual stop locations from a cluster.
    Falls back to centroid if sklearn_extra is unavailable.
    Returns list of (lat, lng) tuples.
    """
    coords = np.array([
        list(_extract_coords(p))
        for p in cluster_points
    ])

    if len(coords) <= n_stops:
        return [(float(c[0]), float(c[1])) for c in coords]

    try:
        from sklearn_extra.cluster import KMedoids
        kmedoids = KMedoids(n_clusters=n_stops, metric="euclidean", random_state=42)
        kmedoids.fit(coords)
        centers = coords[kmedoids.medoid_indices_]
        return [(float(c[0]), float(c[1])) for c in centers]
    except Exception:
        # Fallback: use geometric centroid
        centroid = coords.mean(axis=0)
        return [(float(centroid[0]), float(centroid[1]))]
