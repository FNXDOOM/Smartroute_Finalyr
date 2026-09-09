import functools
from typing import Tuple

from utils.geo import haversine_meters as _haversine_meters  # noqa: F401


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


# Cache graphs by grid cell
@functools.lru_cache(maxsize=16)
def _cached_road_graph(grid_lat: float, grid_lng: float, dist: int):
    """Load and cache the road graph around a coordinate."""
    try:
        import osmnx as ox
        return ox.graph_from_point((grid_lat, grid_lng), dist=dist, network_type="drive")
    except Exception:
        return None


def build_road_graph(lat: float, lng: float, dist: int = 3000):
    """Return cached road graph for lat/lng."""
    # Round to 0.05 deg grid key
    grid_lat = round(round(lat / 0.05) * 0.05, 6)
    grid_lng = round(round(lng / 0.05) * 0.05, 6)
    return _cached_road_graph(grid_lat, grid_lng, dist)
