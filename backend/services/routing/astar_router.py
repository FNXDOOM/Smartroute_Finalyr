import osmnx as ox
import networkx as nx


def load_road_graph(place: str = "Bangalore, India") -> nx.MultiDiGraph:
    """Load drivable road graph for place."""
    G = ox.graph_from_place(place, network_type="drive")
    return G


def astar_route(graph: nx.MultiDiGraph, origin_node: int, dest_node: int) -> list:
    """Shortest A* path as node ID list."""
    path = nx.astar_path(graph, origin_node, dest_node, weight="length")
    return path
