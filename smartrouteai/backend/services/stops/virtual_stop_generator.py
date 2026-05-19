import numpy as np
from sklearn_extra.cluster import KMedoids


def generate_virtual_stops(cluster_points: list, n_stops: int = 1) -> list:
    """
    Use K-Medoids to select representative virtual stop locations
    from a cluster of passenger pickup points.
    Returns list of (lat, lng) tuples.
    """
    coords = np.array([[p["lat"], p["lng"]] for p in cluster_points])
    if len(coords) <= n_stops:
        return [(p["lat"], p["lng"]) for p in cluster_points]

    kmedoids = KMedoids(n_clusters=n_stops, metric="euclidean", random_state=42)
    kmedoids.fit(coords)
    centers = coords[kmedoids.medoid_indices_]
    return [(float(c[0]), float(c[1])) for c in centers]
