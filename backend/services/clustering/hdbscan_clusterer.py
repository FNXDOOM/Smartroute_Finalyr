import numpy as np
import hdbscan


def cluster_passengers(requests: list, min_cluster_size: int = 2) -> np.ndarray:
    """
    Apply HDBSCAN clustering to passenger pickup locations.
    Returns array of cluster labels (-1 = noise/outlier).
    """
    coords = np.array([[r["pickup_lat"], r["pickup_lng"]] for r in requests])
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="haversine")
    labels = clusterer.fit_predict(np.radians(coords))
    return labels
