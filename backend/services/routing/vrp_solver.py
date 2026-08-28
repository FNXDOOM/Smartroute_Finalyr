from typing import List, Dict, Any, Optional

import networkx as nx

from services.stops.road_snapper import build_road_graph
from services.stadia_client import matrix as stadia_matrix
from utils.geo import haversine_meters as _haversine_meters


def build_distance_matrix(stops: List[Dict]) -> List[List[int]]:
    """
    Build a symmetric integer distance matrix (meters) from a list of stops.
    Each stop dict must have 'lat' and 'lng' keys.
    Index 0 is reserved as the depot.
    """
    n = len(stops)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                dist = _haversine_meters(
                    stops[i]["lat"], stops[i]["lng"],
                    stops[j]["lat"], stops[j]["lng"]
                )
                matrix[i][j] = int(dist)
    return matrix


def build_road_distance_matrix(stops: List[Dict]) -> List[List[int]]:
    """Build a drivable distance matrix from the local OSM road graph.

    The graph download can fail when OSM data is unavailable or when stops are
    outside the graph coverage. In those cases, retain the optimizer's safe
    fallback instead of failing an entire dispatch run.
    """
    matrix = build_distance_matrix(stops)
    if len(stops) < 2:
        return matrix

    centre_lat = sum(stop["lat"] for stop in stops) / len(stops)
    centre_lng = sum(stop["lng"] for stop in stops) / len(stops)
    radius = max(
        3000,
        int(max(
            _haversine_meters(centre_lat, centre_lng, stop["lat"], stop["lng"])
            for stop in stops
        ) * 1.35),
    )
    graph = build_road_graph(centre_lat, centre_lng, dist=radius)
    if graph is None:
        return matrix

    try:
        import osmnx as ox

        nodes = [ox.distance.nearest_nodes(graph, X=stop["lng"], Y=stop["lat"]) for stop in stops]
        for i, origin_node in enumerate(nodes):
            lengths = nx.single_source_dijkstra_path_length(graph, origin_node, weight="length")
            for j, destination_node in enumerate(nodes):
                if i != j and destination_node in lengths:
                    matrix[i][j] = int(round(lengths[destination_node]))
    except Exception:
        # Keep the Haversine values for pairs that cannot be resolved on-road.
        return matrix
    return matrix


def _matrix_rows(data: Dict[str, Any]) -> list:
    """Accept the common Stadia/Valhalla matrix response shapes."""
    return (
        data.get("sources_to_targets")
        or data.get("sourcesToTargets")
        or data.get("matrix")
        or data.get("durations")
        or []
    )


def build_stadia_distance_matrix(
    sources: List[Dict],
    targets: Optional[List[Dict]] = None,
) -> Optional[List[List[int]]]:
    """Fetch a road matrix for dispatch when Stadia is configured.

    ``sources`` and ``targets`` may be different-sized lists. This matters for
    fleet assignment, where vehicle origins and route pickup points are not a
    single square matrix. Stadia's matrix service is capped by the number of
    source/target elements, so larger jobs deliberately use the local OSM road
    graph instead.
    """
    targets = sources if targets is None else targets
    if not sources or not targets or len(sources) > 25 or len(targets) > 25:
        return None
    source_points = [{"lat": stop["lat"], "lon": stop["lng"]} for stop in sources]
    target_points = [{"lat": stop["lat"], "lon": stop["lng"]} for stop in targets]
    try:
        data = stadia_matrix(source_points, target_points)
    except RuntimeError:
        return None

    rows = _matrix_rows(data)
    if not isinstance(rows, list) or len(rows) < len(sources):
        return None
    result = [[0] * len(targets) for _ in sources]
    for i in range(len(sources)):
        row = rows[i] if isinstance(rows[i], list) else []
        if len(row) < len(targets):
            return None
        for j in range(len(targets)):
            item = row[j]
            if isinstance(item, dict):
                distance = item.get("distance")
            else:
                distance = item
            if distance is None:
                return None
            # The request uses units=kilometers; keep OR-Tools in meters.
            try:
                result[i][j] = max(0, int(round(float(distance) * 1000)))
            except (TypeError, ValueError):
                return None
    return result


def build_road_distance_to_targets(
    sources: List[Dict],
    targets: List[Dict],
) -> Optional[List[List[int]]]:
    """Build a local OSM road-distance matrix for different origins/targets."""
    if not sources or not targets:
        return None

    points = [*sources, *targets]
    centre_lat = sum(point["lat"] for point in points) / len(points)
    centre_lng = sum(point["lng"] for point in points) / len(points)
    radius = max(
        3000,
        int(max(
            _haversine_meters(centre_lat, centre_lng, point["lat"], point["lng"])
            for point in points
        ) * 1.35),
    )
    graph = build_road_graph(centre_lat, centre_lng, dist=radius)
    if graph is None:
        return None

    try:
        import osmnx as ox

        source_nodes = [ox.distance.nearest_nodes(graph, X=point["lng"], Y=point["lat"]) for point in sources]
        target_nodes = [ox.distance.nearest_nodes(graph, X=point["lng"], Y=point["lat"]) for point in targets]
        result = []
        for source_node in source_nodes:
            lengths = nx.single_source_dijkstra_path_length(graph, source_node, weight="length")
            result.append([
                int(round(lengths[target_node])) if target_node in lengths else 0
                for target_node in target_nodes
            ])
        if any(distance <= 0 for row in result for distance in row):
            return None
        return result
    except Exception:
        return None


def solve_vrp(
    stops: List[Dict],
    num_vehicles: int,
    vehicle_capacity: int = 6,
    depot_idx: int = 0,
    vehicle_capacities: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Solve the Capacitated Vehicle Routing Problem (CVRP) using Google OR-Tools.

    Args:
        stops: List of dicts with 'lat', 'lng', 'demand' (passenger count). Index 0 = depot.
        num_vehicles: Number of available vehicles.
        vehicle_capacity: Fallback capacity when per-vehicle capacities are not provided.
        depot_idx: Index of the depot node.
        vehicle_capacities: Optional per-vehicle capacity list.

    Returns:
        Dict with 'routes' (list of node-index lists per vehicle) and 'total_distance_m'.
    """
    try:
        from ortools.constraint_solver import routing_enums_pb2, pywrapcp
    except ImportError:
        raise RuntimeError("OR-Tools not installed. Run: pip install ortools")

    if not stops:
        return {"routes": [], "total_distance_m": 0, "status": "no_stops"}

    if num_vehicles <= 0:
        return {"routes": [], "total_distance_m": 0, "status": "no_vehicles"}

    distance_matrix = build_stadia_distance_matrix(stops) or build_road_distance_matrix(stops)
    demands = [int(s.get("demand", 0)) for s in stops]

    manager = pywrapcp.RoutingIndexManager(len(stops), num_vehicles, depot_idx)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return distance_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_cb_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb_idx)

    def demand_callback(from_index):
        return demands[manager.IndexToNode(from_index)]

    demand_cb_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    if vehicle_capacities and len(vehicle_capacities) == num_vehicles:
        capacities = [max(1, int(cap)) for cap in vehicle_capacities]
    else:
        capacities = [vehicle_capacity] * num_vehicles

    routing.AddDimensionWithVehicleCapacity(
        demand_cb_idx,
        0,
        capacities,
        True,
        "Capacity",
    )

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = 10

    solution = routing.SolveWithParameters(params)

    if not solution:
        return {"routes": [], "total_distance_m": 0, "status": "no_solution"}

    routes = []
    total_distance = 0
    for vehicle_idx in range(num_vehicles):
        route_nodes = []
        idx = routing.Start(vehicle_idx)
        route_dist = 0
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            route_nodes.append(node)
            prev_idx = idx
            idx = solution.Value(routing.NextVar(idx))
            route_dist += routing.GetArcCostForVehicle(prev_idx, idx, vehicle_idx)
        if len(route_nodes) > 1:
            routes.append(
                {
                    "vehicle_idx": vehicle_idx,
                    "stop_indices": route_nodes,
                    "distance_m": route_dist,
                }
            )
        total_distance += route_dist

    return {
        "routes": routes,
        "total_distance_m": total_distance,
        "status": "solved",
    }
