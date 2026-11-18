import time
from typing import Tuple

from utils.geo import haversine_meters as _haversine_meters  # noqa: F401

# Overpass defaults (180 s timeout + rate-limit pauses) can stall a dispatch tick
# for minutes; bound the fetch and retry failures instead of caching them forever.
_GRAPH_TIMEOUT_SECONDS = 25
_FAILURE_RETRY_SECONDS = 60
_GRAPH_CACHE: dict = {}


def snap_to_road(graph, lat: float, lng: float) -> Tuple[float, float, str]:
    """Snap point to nearest road node."""
    if graph is None:
        return lat, lng, "none"

    try:
        import osmnx as ox
        nearest_node = ox.distance.nearest_nodes(graph, X=lng, Y=lat)
        node_data = graph.nodes[nearest_node]
        return float(node_data["y"]), float(node_data["x"]), str(nearest_node)
    except Exception:
        return lat, lng, "none"


# Cache graphs by grid cell; a failed fetch is retried after a short cooldown.
def _cached_road_graph(grid_lat: float, grid_lng: float, dist: int):
    """Load and cache the road graph around a coordinate."""
    key = (grid_lat, grid_lng, dist)
    now = time.monotonic()
    entry = _GRAPH_CACHE.get(key)
    if entry is not None and (entry[1] is not None or now < entry[0]):
        return entry[1]
    graph = None
    try:
        import osmnx as ox
        for setting in ("timeout", "requests_timeout"):
            if hasattr(ox.settings, setting):
                setattr(ox.settings, setting, _GRAPH_TIMEOUT_SECONDS)
        if hasattr(ox.settings, "overpass_rate_limit"):
            ox.settings.overpass_rate_limit = False
        graph = ox.graph_from_point((grid_lat, grid_lng), dist=dist, network_type="drive")
    except Exception:
        graph = None
    if len(_GRAPH_CACHE) >= 16:
        _GRAPH_CACHE.pop(next(iter(_GRAPH_CACHE)))
    _GRAPH_CACHE[key] = (now + _FAILURE_RETRY_SECONDS, graph)
    return graph


def build_road_graph(lat: float, lng: float, dist: int = 3000):
    """Return cached road graph for lat/lng."""
    # Round to 0.05 deg grid key
    grid_lat = round(round(lat / 0.05) * 0.05, 6)
    grid_lng = round(round(lng / 0.05) * 0.05, 6)
    return _cached_road_graph(grid_lat, grid_lng, dist)
