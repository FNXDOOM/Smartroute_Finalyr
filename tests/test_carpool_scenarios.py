"""Synthetic directed-road scenarios: deterministic policy tests, not live map claims."""
from datetime import datetime, timezone
from types import SimpleNamespace
from threading import Barrier, Lock

import pytest

from services import carpool_matching as matching


def rider(index, pickup=0, destination=10, shared=True):
    return SimpleNamespace(
        id=index, request_time=datetime(2026, 11, 20, tzinfo=timezone.utc),
        pickup_lat=13.0, pickup_lng=77.0 + pickup / 110,
        dest_lat=13.0, dest_lng=77.0 + destination / 110, is_shared=shared,
    )


@pytest.fixture
def line_roads(monkeypatch):
    def matrix(sources, targets, **kwargs):
        return {"sources_to_targets": [
            [{"distance": abs(a["lon"] - b["lon"]) * 110} for b in targets]
            for a in sources
        ]}
    monkeypatch.setattr(matching, "matrix", matrix)
    return matrix


@pytest.mark.parametrize("count,expected", [(2, [2]), (3, [3]), (4, [2, 2]), (5, [3, 2]), (7, [3, 2, 2])])
@pytest.mark.parametrize("local", [False, True])
def test_compatible_riders_do_not_strand_a_fourth(count, expected, local, line_roads):
    requests = [rider(i, pickup=i * .001) for i in range(count)]
    groups = (matching.split_compatible_shared_group(requests) if local
              else matching.find_cross_cell_corridor_groups(requests)[0])
    assert sorted(map(len, groups), reverse=True) == expected
    assert sorted(item.id for group in groups for item in group) == list(range(count))


@pytest.mark.parametrize("destinations", [(3, 8), (8, 3)])
def test_same_pickup_nested_destinations_are_order_independent(destinations, line_roads):
    requests = [rider(i, destination=dest) for i, dest in enumerate(destinations)]
    assert list(map(len, matching.split_compatible_shared_group(requests))) == [2]


@pytest.mark.parametrize("local", [True, False])
@pytest.mark.parametrize("reverse", [True, False])
def test_rides_35_and_36_are_evaluated_by_roads_not_destination_spread(monkeypatch, local, reverse):
    # Production coordinates; the distances below are a synthetic nested-road
    # fixture, not a claim about the live provider's actual routes.
    requests = [rider(35), rider(36)]
    for request, destination in zip(requests, [(13.027276, 77.731848), (13.072354, 77.787191)]):
        request.pickup_lat, request.pickup_lng = 12.997038, 77.669131
        request.dest_lat, request.dest_lng = destination
    positions = {(12.997038, 77.669131): 0, (13.027276, 77.731848): 14, (13.072354, 77.787191): 23}
    calls = []
    def matrix(sources, targets, **kwargs):
        calls.append(1)
        return {"sources_to_targets": [
            [{"distance": abs(positions[(a["lat"], a["lon"])] - positions[(b["lat"], b["lon"])])}
             for b in targets] for a in sources
        ]}
    monkeypatch.setattr(matching, "matrix", matrix)
    if reverse:
        requests.reverse()
        # Change arrival order too; the matcher sorts by request_time/id.
        requests[0].id, requests[1].id = 35, 36
    groups = (matching.split_compatible_shared_group(requests) if local
              else matching.find_cross_cell_corridor_groups(requests)[0])
    assert list(map(len, groups)) == [2]
    assert calls, "The road check must not be skipped by a destination-radius gate"


@pytest.mark.parametrize("destinations", [(10, 25), (25, 10)])
def test_far_apart_destinations_still_require_road_detour_limits(monkeypatch, destinations):
    requests = [rider(i, destination=destination) for i, destination in enumerate(destinations)]
    def matrix(sources, targets, **kwargs):
        pickup = requests[0].pickup_lng
        return {"sources_to_targets": [
            [{"distance": 0 if a["lon"] == b["lon"] else (
                abs(a["lon"] - b["lon"]) * 110
                if pickup in (a["lon"], b["lon"]) else 50
            )} for b in targets] for a in sources
        ]}
    monkeypatch.setattr(matching, "matrix", matrix)
    assert matching.find_cross_cell_corridor_groups(requests) == ([], set())


def test_local_pickups_cannot_bypass_road_detour_policy(monkeypatch):
    requests = [rider(0), rider(1, pickup=.001, destination=11)]
    distances = [[0, 20, 10, 20], [20, 0, 20, 10], [10, 20, 0, 20], [20, 10, 20, 0]]
    monkeypatch.setattr(matching, "matrix", lambda *a, **k: {
        "sources_to_targets": [[{"distance": d} for d in row] for row in distances],
    })
    assert all(len(group) == 1 for group in matching.split_compatible_shared_group(requests))


def test_private_rides_never_enter_corridor_pool(line_roads):
    groups, ids = matching.find_cross_cell_corridor_groups([rider(0), rider(1, shared=False)])
    assert groups == [] and ids == set()


def test_overlapping_corridor_can_drop_off_before_final_pickup(line_roads):
    requests = [rider(0, 0, 4), rider(1, 3, 8), rider(2, 7, 10)]
    groups, ids = matching.find_cross_cell_corridor_groups(requests)
    assert list(map(len, groups)) == [3]
    assert ids == {0, 1, 2}


def test_disjoint_short_trips_are_not_a_carpool(line_roads):
    assert not matching.road_detour_compatible([rider(0, 0, 1), rider(1, 2, 3)])


def test_opposite_trips_cannot_share_only_a_zero_length_stop(line_roads):
    assert not matching.road_detour_compatible([rider(0, 0, 3), rider(1, 3, 0)])


@pytest.mark.parametrize("requests", [
    [rider(0, 0, 10), rider(1, 10, 0)],  # Opposite directions.
    [rider(0, 0, 10), rider(1, 20, 30)],  # Disjoint routes.
    [rider(0, 0, 2), rider(1, 1, -2)],   # Short rider would exceed detour budget.
])
def test_incompatible_trips_stay_pending(requests, line_roads):
    assert matching.find_cross_cell_corridor_groups(requests) == ([], set())


def test_road_fallback_is_bounded_parallel_work(monkeypatch):
    monkeypatch.setattr(matching, "matrix", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("denied")))
    barrier = Barrier(4, timeout=3)
    lock = Lock()
    calls = []

    def route(*coords, **kwargs):
        with lock:
            calls.append(coords)
            first_wave = len(calls) <= 4
        if first_wave:
            barrier.wait()
        return {"trip": {"status": 0, "units": "kilometers", "summary": {"length": 1}}}

    monkeypatch.setattr(matching, "route", route)
    points = [{"lat": 13, "lon": 77 + i * .01} for i in range(4)]
    assert matching._road_distances(points) == [[0 if i == j else 1000 for j in range(4)] for i in range(4)]
    assert len(calls) == 12


def test_road_outage_is_reported_instead_of_incompatibility(monkeypatch):
    def fail(*a, **k):
        raise RuntimeError("upstream URL with credentials must not be exposed")
    monkeypatch.setattr(matching, "matrix", fail)
    monkeypatch.setattr(matching, "route", fail)
    with matching.road_matching_batch() as stats:
        groups, _ = matching.find_cross_cell_corridor_groups([rider(0), rider(1, .5), rider(2, 1)])
    assert groups == []
    assert stats["routing_failures"] > 0
    assert stats["matrix_attempts"] == 1


def test_pool_checks_reuse_directed_distances_within_tick(monkeypatch, line_roads):
    calls = []
    def counted(sources, targets, **kwargs):
        calls.append(1)
        return line_roads(sources, targets, **kwargs)
    monkeypatch.setattr(matching, "matrix", counted)
    requests = [rider(0), rider(1, .5)]
    with matching.road_matching_batch():
        assert matching.road_detour_compatible(requests)
        assert matching.road_detour_compatible(requests[::-1])
    assert len(calls) == 1


def test_dispatch_solver_uses_standard_routes_when_matrix_is_denied(monkeypatch):
    from services.routing import vrp_solver
    vrp_solver._fetch_matrix_block.cache_clear()
    def fail(*a, **k):
        raise RuntimeError("matrix denied")
    monkeypatch.setattr(vrp_solver, "stadia_matrix", fail)
    monkeypatch.setattr(matching, "matrix", fail)
    monkeypatch.setattr(matching, "route", lambda a, b, c, d, **k: {
        "trip": {"status": 0, "units": "kilometers", "summary": {"length": abs(b - d) * 110}}
    })
    nodes = [
        dict(lat=13, lng=77, kind="depot", demand=0),
        dict(lat=13, lng=77, kind="pickup", demand=1),
        dict(lat=13, lng=77.01, kind="pickup", demand=1),
        dict(lat=13, lng=77.03, kind="destination", demand=1, pair_index=1),
        dict(lat=13, lng=77.04, kind="destination", demand=1, pair_index=2),
    ]
    monkeypatch.setattr(vrp_solver, "build_road_graph", lambda *a, **k: pytest.fail("must not download OSM when standard routes work"))
    result = vrp_solver.solve_shared_ride_pdp(nodes, 1, vehicle_capacity=2, time_limit_seconds=1)
    assert result["status"] == "solved"
    order = result["routes"][0]["stop_indices"]
    assert order.index(1) < order.index(3)
    assert order.index(2) < order.index(4)


def test_final_solver_cannot_exceed_a_riders_detour_budget(monkeypatch):
    from services.routing import vrp_solver
    nodes = [
        dict(lat=13, lng=77, kind="depot", demand=0),
        dict(lat=13, lng=77.01, kind="pickup", demand=2),
        dict(lat=13, lng=77.02, kind="destination", demand=1, pair_index=1),
        dict(lat=13, lng=77.03, kind="destination", demand=1, pair_index=1),
    ]
    def matrix(points):
        distances = [[0 if i == j else 20000 for j in range(len(points))] for i in range(len(points))]
        distances[1][2] = distances[1][3] = 1000
        return distances
    monkeypatch.setattr(vrp_solver, "build_stadia_distance_matrix", matrix)
    result = vrp_solver.solve_shared_ride_pdp(nodes, 1, vehicle_capacity=2, time_limit_seconds=1)
    assert result["status"] == "no_solution"


@pytest.mark.parametrize("vehicle_count,expected", [(2, [2, 2]), (1, [3])])
def test_four_shared_riders_dispatch_as_pairs_not_a_solo_ride(mock_road_matrix, vehicle_count, expected):
    from services.routing.shared_route_builder import build_shared_routes
    stops = [SimpleNamespace(
        id=i + 1, cluster_id=1 if i < 2 else 2, lat=13, lng=77 + i * .00001,
        ride_requests=[SimpleNamespace(id=i + 1, is_shared=True, status="clustered", dest_lat=13, dest_lng=77.03)],
    ) for i in range(4)]
    built = build_shared_routes(
        vehicles=[SimpleNamespace(id=i, capacity=3) for i in range(vehicle_count)],
        virtual_stops=stops, depot_lat=13, depot_lng=77, enrich=False,
    )
    assert sorted(len(route.ride_ids) for route in built) == expected


def test_one_seat_vehicle_cannot_be_used_for_a_carpool(mock_road_matrix):
    from services.routing.shared_route_builder import build_shared_routes
    stops = [SimpleNamespace(
        id=i + 1, lat=13, lng=77,
        ride_requests=[SimpleNamespace(id=i + 1, is_shared=True, status="clustered", dest_lat=13, dest_lng=77.03)],
    ) for i in range(2)]
    built = build_shared_routes(
        vehicles=[SimpleNamespace(id=1, capacity=1)], virtual_stops=stops,
        depot_lat=13, depot_lng=77, enrich=False,
    )
    assert built == []


def test_periodic_dispatch_subtracts_work_time_and_does_not_overlap(monkeypatch):
    import asyncio
    from services import background_jobs
    sleeps, calls = [], []
    times = iter([100.0, 103.0])
    async def in_thread(fn):
        fn()
    async def sleep(delay):
        sleeps.append(delay)
        raise asyncio.CancelledError
    monkeypatch.setattr(background_jobs, "asyncio", SimpleNamespace(
        to_thread=in_thread, sleep=sleep, CancelledError=asyncio.CancelledError,
        get_running_loop=lambda: SimpleNamespace(time=lambda: next(times)),
    ))
    monkeypatch.setattr(background_jobs, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(background_jobs.STATE, "active_tasks", [])
    asyncio.run(background_jobs._run_periodic("test_tick", 5, lambda db: calls.append(1)))
    assert calls == [1]
    assert sleeps == [2.0]
