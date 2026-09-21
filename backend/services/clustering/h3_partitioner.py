from typing import Set

import h3


def get_h3_index(lat: float, lng: float, resolution: int = 9) -> str:
    """Get H3 index string for given lat/lng and resolution"""
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(lat, lng, resolution)
    elif hasattr(h3, "geo_to_h3"):
        return h3.geo_to_h3(lat, lng, resolution)
    raise AttributeError("H3 library missing latlng_to_cell or geo_to_h3")


def neighbouring_h3_cells(cell: str, k: int = 1) -> Set[str]:
    """The cell itself plus every cell within ``k`` rings of it.

    Route matching must not treat a single H3 cell as a hard boundary, so the
    clustering pass expands each cell to its neighbours. Degrades to the cell
    alone if the installed H3 build exposes no ring API.
    """
    if hasattr(h3, "grid_disk"):
        return set(h3.grid_disk(cell, k))
    elif hasattr(h3, "k_ring"):
        return set(h3.k_ring(cell, k))
    return {cell}


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

