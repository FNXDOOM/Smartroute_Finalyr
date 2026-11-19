import functools
import logging
import math
import os
from typing import List, Dict, Any, Optional

import networkx as nx

from config import ROUTE_SOLVER_MAX_SECONDS, ROUTE_SOLVER_MIN_SECONDS
from services.stops.road_snapper import build_road_graph
from services.stadia_client import matrix as stadia_matrix
from utils.geo import haversine_meters as _haversine_meters
from utils.ride_states import ROUTE_SOLVED

# GUIDED_LOCAL_SEARCH always spends the full time_limit, so CI lowers it via SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS instead of this default.
DEFAULT_SHARED_RIDE_SOLVER_SECONDS = 15


def shared_ride_solver_time_limit() -> int:
    raw = os.getenv("SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS", "")
    try:
        return max(1, int(raw)) if raw else max(1, int(ROUTE_SOLVER_MAX_SECONDS))
    except ValueError:
        return DEFAULT_SHARED_RIDE_SOLVER_SECONDS


def solver_time_limit_for_size(pairs: int, *, max_seconds: Optional[int] = None) -> int:
    """Tiered budget: small pools return quickly, large pools keep the old ceiling."""
    ceiling = max(1, int(max_seconds or shared_ride_solver_time_limit()))
    floor = max(1, min(int(ROUTE_SOLVER_MIN_SECONDS), ceiling))
    if pairs <= 3:
        tier = floor
    elif pairs <= 6:
        tier = floor * 2
    elif pairs <= 12:
        tier = floor * 4
    else:
        tier = ceiling
    return max(1, min(tier, ceiling))


# Stadia's matrix endpoint accepts at most 25 sources x 25 targets per call.
MATRIX_CHUNK_SIZE = 25
# Bound local graph work; larger requests require the chunked road provider.
OSM_MATRIX_NODE_CAP = 25


class _MatrixUnavailable(Exception):
    """A road matrix block could not be read (never cached)."""


def build_distance_matrix(stops: List[Dict]) -> List[List[int]]:
    """Build symmetric distance matrix in meters."""
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


def build_road_distance_matrix(stops: List[Dict]) -> Optional[List[List[int]]]:
    """Return directed road distances, or None; never invent unreachable arcs."""
    matrix = [[0] * len(stops) for _ in stops]
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
    if len(stops) > OSM_MATRIX_NODE_CAP:
        return None

    graph = build_road_graph(centre_lat, centre_lng, dist=radius)
    if graph is None:
        return None

    try:
        import osmnx as ox

        nodes = [ox.distance.nearest_nodes(graph, X=stop["lng"], Y=stop["lat"]) for stop in stops]
        for i, origin_node in enumerate(nodes):
            lengths = nx.single_source_dijkstra_path_length(graph, origin_node, weight="length")
            for j, destination_node in enumerate(nodes):
                if destination_node not in lengths:
                    return None
                distance = float(lengths[destination_node])
                if not math.isfinite(distance) or distance < 0:
                    return None
                matrix[i][j] = int(round(distance))
    except Exception:
        return None
    return matrix


def _matrix_rows(data: Dict[str, Any]) -> list:
    """Parse Stadia matrix shapes."""
    return (
        data.get("sources_to_targets")
        or data.get("sourcesToTargets")
        or data.get("matrix")
        or data.get("durations")
        or []
    )


@functools.lru_cache(maxsize=64)
def _fetch_matrix_block(
    source_key: tuple,
    target_key: tuple,
) -> tuple:
    """Stadia block cached by rounded coords; raises _MatrixUnavailable so a transient failure is never cached."""
    source_points = [{"lat": lat, "lon": lng} for lat, lng in source_key]
    target_points = [{"lat": lat, "lon": lng} for lat, lng in target_key]
    try:
        data = stadia_matrix(source_points, target_points)
    except RuntimeError as exc:
        raise _MatrixUnavailable(str(exc)) from exc

    rows = _matrix_rows(data)
    if not isinstance(rows, list) or len(rows) < len(source_key):
        raise _MatrixUnavailable("matrix response had too few rows")
    result = []
    for i in range(len(source_key)):
        row = rows[i] if isinstance(rows[i], list) else []
        if len(row) < len(target_key):
            raise _MatrixUnavailable("matrix response row was too short")
        parsed = []
        for j in range(len(target_key)):
            item = row[j]
            distance = item.get("distance") if isinstance(item, dict) else item
            if distance is None:
                raise _MatrixUnavailable("matrix response contained a null distance")
            # Request in km; OR-Tools needs meters
            try:
                distance = float(distance)
                if not math.isfinite(distance) or distance < 0:
                    raise ValueError("distance must be finite and nonnegative")
                parsed.append(int(round(distance * 1000)))
            except (TypeError, ValueError, OverflowError) as exc:
                raise _MatrixUnavailable("matrix response held a non-numeric distance") from exc
        result.append(tuple(parsed))
    return tuple(result)


def _matrix_block(sources: List[Dict], targets: List[Dict]) -> Optional[List[List[int]]]:
    """One source/target block, served from cache when the coordinates repeat."""
    source_key = tuple((round(float(s["lat"]), 5), round(float(s["lng"]), 5)) for s in sources)
    target_key = tuple((round(float(t["lat"]), 5), round(float(t["lng"]), 5)) for t in targets)
    try:
        block = _fetch_matrix_block(source_key, target_key)
    except _MatrixUnavailable:
        return None
    return [list(row) for row in block]


def build_stadia_distance_matrix(
    sources: List[Dict],
    targets: Optional[List[Dict]] = None,
) -> Optional[List[List[int]]]:
    """Fetch Stadia road matrix if configured, chunked past the endpoint's 25x25 cap."""
    targets = sources if targets is None else targets
    if not sources or not targets:
        return None
    result = [[0] * len(targets) for _ in sources]
    for source_offset in range(0, len(sources), MATRIX_CHUNK_SIZE):
        for target_offset in range(0, len(targets), MATRIX_CHUNK_SIZE):
            block = _matrix_block(
                sources[source_offset:source_offset + MATRIX_CHUNK_SIZE],
                targets[target_offset:target_offset + MATRIX_CHUNK_SIZE],
            )
            if block is None:
                return None
            for row_offset, row in enumerate(block):
                result[source_offset + row_offset][target_offset:target_offset + len(row)] = row
    return result


def build_road_distance_to_targets(
    sources: List[Dict],
    targets: List[Dict],
) -> Optional[List[List[int]]]:
    """Build OSM matrix for origins/targets."""
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
    """Solve CVRP with OR-Tools."""
    try:
        from ortools.constraint_solver import routing_enums_pb2, pywrapcp
    except ImportError:
        raise RuntimeError("OR-Tools not installed. Run: pip install ortools")

    if not stops:
        return {"routes": [], "total_distance_m": 0, "status": "no_stops"}

    if num_vehicles <= 0:
        return {"routes": [], "total_distance_m": 0, "status": "no_vehicles"}

    distance_matrix = build_stadia_distance_matrix(stops) or build_road_distance_matrix(stops)
    if distance_matrix is None:
        logging.getLogger(__name__).warning(
            "No road matrix from Stadia or OSM; dispatch skipped for %s stops", len(stops)
        )
        return {"routes": [], "total_distance_m": 0, "status": "routing_unavailable"}
    demands = [int(s.get("demand", 0)) for s in stops]

    manager = pywrapcp.RoutingIndexManager(len(stops), num_vehicles, depot_idx)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        """Return the routing distance between two indexed locations."""
        return distance_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_cb_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb_idx)

    def demand_callback(from_index):
        """Return the passenger demand for an indexed location."""
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
    params.time_limit.seconds = solver_time_limit_for_size(max(1, len(stops) - 1))

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
        "status": ROUTE_SOLVED,
    }


def solve_shared_ride_pdp(
    nodes: List[Dict],
    num_vehicles: int,
    vehicle_capacity: int = 4,
    vehicle_capacities: Optional[List[int]] = None,
    depot_idx: int = 0,
    time_limit_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Pooled PDP over depot + pickup + destination nodes; each destination carries pair_index at its boarding pickup and returns its demand."""
    try:
        from ortools.constraint_solver import routing_enums_pb2, pywrapcp
    except ImportError:
        raise RuntimeError("OR-Tools not installed. Run: pip install ortools")

    if not nodes:
        return {"routes": [], "total_distance_m": 0, "status": "no_stops"}
    if num_vehicles <= 0:
        return {"routes": [], "total_distance_m": 0, "status": "no_vehicles"}

    pickups = [index for index, node in enumerate(nodes) if node.get("kind") == "pickup"]
    destinations = [index for index, node in enumerate(nodes) if node.get("kind") == "destination"]
    if not pickups or not destinations:
        return {"routes": [], "total_distance_m": 0, "status": "no_stops"}

    # Each vehicle ends on a zero-demand depot copy, so the final arc is a free hop rather than a return trip.
    end_node = len(nodes)
    matrix_nodes = [dict(node) for node in nodes]
    matrix_nodes.append({
        "lat": nodes[depot_idx]["lat"],
        "lng": nodes[depot_idx]["lng"],
        "kind": "depot_end",
        "demand": 0,
    })

    distance_matrix = build_stadia_distance_matrix(matrix_nodes)
    if distance_matrix is None:
        distance_matrix = build_road_distance_matrix(matrix_nodes)
    if distance_matrix is None:
        logging.getLogger(__name__).warning(
            "No road matrix from Stadia or OSM; dispatch skipped for %s stops", len(matrix_nodes)
        )
        return {"routes": [], "total_distance_m": 0, "status": "routing_unavailable"}

    if vehicle_capacities and len(vehicle_capacities) == num_vehicles:
        capacities = [max(1, int(capacity)) for capacity in vehicle_capacities]
    else:
        capacities = [max(1, int(vehicle_capacity))] * num_vehicles

    manager = pywrapcp.RoutingIndexManager(
        len(matrix_nodes),
        num_vehicles,
        [depot_idx] * num_vehicles,
        [end_node] * num_vehicles,
    )
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        """Return the routing distance between two indexed locations."""
        return distance_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_cb_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb_idx)

    # Precedence uses the distance dimension; the load dimension isn't a reliable ordering constraint in every OR-Tools version.
    max_route_distance = max(1, sum(max(row) for row in distance_matrix))
    routing.AddDimension(
        transit_cb_idx,
        0,
        max_route_distance,
        True,
        "Distance",
    )
    distance_dimension = routing.GetDimensionOrDie("Distance")

    def load_callback(from_index):
        """Seats taken at a boarding stop, seats freed at a destination."""
        node = matrix_nodes[manager.IndexToNode(from_index)]
        demand = int(node.get("demand") or 0)
        if node.get("kind") == "pickup":
            return demand
        if node.get("kind") == "destination":
            return -demand
        return 0

    load_cb_idx = routing.RegisterUnaryTransitCallback(load_callback)
    routing.AddDimensionWithVehicleCapacity(
        load_cb_idx,
        0,
        capacities,
        True,
        "Load",
    )
    # Some OR-Tools builds return a success flag from AddDimension, so look the dimension up by name.
    load_dimension = routing.GetDimensionOrDie("Load")

    for index in destinations:
        pair_index = nodes[index].get("pair_index")
        if pair_index is None:
            return {"routes": [], "total_distance_m": 0, "status": "no_solution"}
        pickup_var = manager.NodeToIndex(int(pair_index))
        destination_var = manager.NodeToIndex(index)
        if pickup_var < 0 or destination_var < 0:
            return {"routes": [], "total_distance_m": 0, "status": "no_solution"}
        # Same vehicle for the pair, and board before alighting.
        routing.AddPickupAndDelivery(pickup_var, destination_var)
        routing.solver().Add(
            routing.VehicleVar(pickup_var) == routing.VehicleVar(destination_var)
        )
        routing.solver().Add(
            distance_dimension.CumulVar(pickup_var) <= distance_dimension.CumulVar(destination_var)
        )

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = (
        solver_time_limit_for_size(len(pickups)) if time_limit_seconds is None else max(1, time_limit_seconds)
    )

    solution = routing.SolveWithParameters(params)
    if not solution:
        return {"routes": [], "total_distance_m": 0, "status": "no_solution"}

    routes = []
    total_distance = 0
    for vehicle_idx in range(num_vehicles):
        stop_indices = []
        index = routing.Start(vehicle_idx)
        route_distance = 0
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node < len(nodes):
                stop_indices.append(node)
            previous = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(previous, index, vehicle_idx)
        if len(stop_indices) > 1:
            routes.append({
                "vehicle_idx": vehicle_idx,
                "stop_indices": stop_indices,
                "distance_m": route_distance,
            })
        total_distance += route_distance

    if not routes:
        return {"routes": [], "total_distance_m": 0, "status": "no_solution"}

    return {
        "routes": routes,
        "total_distance_m": total_distance,
        "status": ROUTE_SOLVED,
    }
