from math import radians, cos, sin, asin, sqrt
from typing import List, Dict, Any, Optional


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * R * asin(sqrt(a))


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

    distance_matrix = build_distance_matrix(stops)
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
