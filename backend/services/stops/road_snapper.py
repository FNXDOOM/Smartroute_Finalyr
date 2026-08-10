from typing import Tuple

from utils.geo import haversine_meters as _haversine_meters  # noqa: F401 — kept for any future internal use


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


def build_road_graph(lat: float, lng: float, dist: int = 3000):
    """
    Download a drivable road graph centred on lat/lng within `dist` metres.
    Returns networkx MultiDiGraph or None on failure.
    """
    try:
        import osmnx as ox
        G = ox.graph_from_point((lat, lng), dist=dist, network_type="drive")
        return G
    except Exception:
        return None
