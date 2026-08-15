import functools
from typing import Tuple

from utils.geo import haversine_meters as _haversine_meters  # noqa: F401


def snap_to_road(graph, lat: float, lng: float) -> Tuple[float, float, str]:
    """
    Snap a lat/lng coordinate to the nearest road network node using OSMnx.
    Returns (snapped_lat, snapped_lng, node_id_str).
    Falls back to original lat/lng if graph is None or OSMnx fails.
    """
    if graph is None:
        return lat, lng, "none"

    try:
        import osmnx as ox
        nearest_node = ox.distance.nearest_nodes(graph, X=lng, Y=lat)
        node_data = graph.nodes[nearest_node]
        return float(node_data["y"]), float(node_data["x"]), str(nearest_node)
    except Exception:
        return lat, lng, "none"


# Cache road graphs by rounded centre coordinate (0.05° ≈ 5 km grid).
# This avoids downloading a fresh graph for every cluster centroid — a
# huge win both for memory and for clustering job speed.
@functools.lru_cache(maxsize=16)
def _cached_road_graph(grid_lat: float, grid_lng: float, dist: int):
    try:
        import osmnx as ox
        return ox.graph_from_point((grid_lat, grid_lng), dist=dist, network_type="drive")
    except Exception:
        return None


def build_road_graph(lat: float, lng: float, dist: int = 3000):
    """
    Return a cached drivable road graph for the grid cell containing lat/lng.
    Snaps to a 0.05° grid (~5 km) so nearby centroids reuse the same graph.
    Returns networkx MultiDiGraph or None on failure.
    """
    # Round to nearest 0.05° to create a coarse grid key
    grid_lat = round(round(lat / 0.05) * 0.05, 6)
    grid_lng = round(round(lng / 0.05) * 0.05, 6)
    return _cached_road_graph(grid_lat, grid_lng, dist)
