import h3


def get_h3_index(lat: float, lng: float, resolution: int = 9) -> str:
    """Get H3 index string for given lat/lng and resolution"""
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(lat, lng, resolution)
    elif hasattr(h3, "geo_to_h3"):
        return h3.geo_to_h3(lat, lng, resolution)
    raise AttributeError("H3 library missing latlng_to_cell or geo_to_h3")


def partition_requests(ride_requests: list, resolution: int = 9) -> dict:
    """
    Partition ride requests into H3 hexagonal cells.
    Returns a dict mapping h3_index -> list of requests.
    """
    buckets = {}
    for req in ride_requests:
        lat = req.pickup_lat if hasattr(req, "pickup_lat") else req["pickup_lat"]
        lng = req.pickup_lng if hasattr(req, "pickup_lng") else req["pickup_lng"]
        h3_idx = get_h3_index(lat, lng, resolution)
        buckets.setdefault(h3_idx, []).append(req)
    return buckets

