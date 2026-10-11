from typing import Set, Tuple

import h3


def get_h3_index(lat: float, lng: float, resolution: int = 9) -> str:
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(lat, lng, resolution)
    elif hasattr(h3, "geo_to_h3"):
        return h3.geo_to_h3(lat, lng, resolution)
    raise AttributeError("H3 library missing latlng_to_cell or geo_to_h3")


def get_h3_center(cell: str) -> Tuple[float, float]:
    """Cell centre, or the origin when the installed H3 build exposes no centre API."""
    try:
        if hasattr(h3, "cell_to_latlng"):
            lat, lng = h3.cell_to_latlng(cell)
            return float(lat), float(lng)
        if hasattr(h3, "h3_to_geo"):
            lat, lng = h3.h3_to_geo(cell)
            return float(lat), float(lng)
    except Exception:
        pass
    return 0.0, 0.0


def neighbouring_h3_cells(cell: str, k: int = 1) -> Set[str]:
    """Cell plus everything within k rings: one H3 cell is not a carpool boundary. Cell alone if the build has no ring API."""
    if hasattr(h3, "grid_disk"):
        return set(h3.grid_disk(cell, k))
    elif hasattr(h3, "k_ring"):
        return set(h3.k_ring(cell, k))
    return {cell}


def partition_requests(ride_requests: list, resolution: int = 9) -> dict:
    """Bucket requests by H3 cell: h3_index -> list of requests."""
    buckets = {}
    for req in ride_requests:
        lat = req.pickup_lat if hasattr(req, "pickup_lat") else req["pickup_lat"]
        lng = req.pickup_lng if hasattr(req, "pickup_lng") else req["pickup_lng"]
        h3_idx = get_h3_index(lat, lng, resolution)
        buckets.setdefault(h3_idx, []).append(req)
    return buckets

