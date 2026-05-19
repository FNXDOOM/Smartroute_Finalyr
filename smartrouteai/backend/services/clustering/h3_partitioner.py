import h3
import numpy as np


def partition_requests(ride_requests: list, resolution: int = 9) -> dict:
    """
    Partition ride requests into H3 hexagonal cells.
    Returns a dict mapping h3_index -> list of requests.
    """
    buckets = {}
    for req in ride_requests:
        lat, lng = req["pickup_lat"], req["pickup_lng"]
        h3_index = h3.geo_to_h3(lat, lng, resolution)
        buckets.setdefault(h3_index, []).append(req)
    return buckets
