import osmnx as ox
import networkx as nx


def snap_to_road(graph: nx.MultiDiGraph, lat: float, lng: float) -> tuple:
    """
    Snap a lat/lng coordinate to the nearest road network node.
    Returns (snapped_lat, snapped_lng).
    """
    nearest_node = ox.distance.nearest_nodes(graph, X=lng, Y=lat)
    node_data = graph.nodes[nearest_node]
    return node_data["y"], node_data["x"]
