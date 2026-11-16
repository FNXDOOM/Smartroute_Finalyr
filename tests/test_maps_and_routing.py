import sys
from types import SimpleNamespace
from pathlib import Path

import networkx as nx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from routers.maps import _rewrite_style
from services.routing import vrp_solver


def test_stadia_style_rewrite_hides_upstream_host_and_api_key():
    rewritten = _rewrite_style({
        "url": "https://tiles.stadiamaps.com/data/openmaptiles.json?api_key=secret",
        "tiles": ["https://tiles.stadiamaps.com/data/openmaptiles/{z}/{x}/{y}.pbf?api_key=secret"],
        "sprite": "https://tiles.stadiamaps.com/styles/alidade-smooth/sprite",
        "glyphs": "https://tiles.stadiamaps.com/fonts/{fontstack}/{range}.pbf",
    }, "http://127.0.0.1:8000/")

    serialized = str(rewritten)
    assert "tiles.stadiamaps.com" not in serialized
    assert "api_key" not in serialized
    assert rewritten["tiles"] == ["http://127.0.0.1:8000/maps/stadia/resource/data/openmaptiles/{z}/{x}/{y}.pbf"]
    assert rewritten["sprite"] == "http://127.0.0.1:8000/maps/stadia/resource/styles/alidade-smooth/sprite"


def test_stadia_matrix_supports_different_source_and_target_counts(monkeypatch):
    monkeypatch.setattr(
        vrp_solver,
        "stadia_matrix",
        lambda sources, targets: {
            "sources_to_targets": [
                [{"distance": 1.2}, {"distance": 2.4}],
                [{"distance": 3.6}, {"distance": 4.8}],
            ]
        },
    )

    matrix = vrp_solver.build_stadia_distance_matrix(
        [{"lat": 12.9, "lng": 77.6}, {"lat": 12.91, "lng": 77.61}],
        [{"lat": 12.92, "lng": 77.62}, {"lat": 12.93, "lng": 77.63}],
    )

    assert matrix == [[1200, 2400], [3600, 4800]]


def _mock_road_graph(monkeypatch, connected=True):
    graph = nx.DiGraph()
    graph.add_nodes_from([1, 2])
    if connected:
        graph.add_edge(1, 2, length=1200)
        graph.add_edge(2, 1, length=1800)
    monkeypatch.setattr(vrp_solver, "build_road_graph", lambda *args, **kwargs: graph)
    monkeypatch.setitem(sys.modules, "osmnx", SimpleNamespace(
        distance=SimpleNamespace(nearest_nodes=lambda graph, X, Y: 1 if X < 77.61 else 2)
    ))
    return [{"lat": 13, "lng": 77.60}, {"lat": 13, "lng": 77.62}]


def test_road_matrix_preserves_directed_road_distances(monkeypatch):
    points = _mock_road_graph(monkeypatch)
    assert vrp_solver.build_road_distance_matrix(points) == [[0, 1200], [1800, 0]]


def test_disconnected_roads_are_not_replaced_with_straight_lines(monkeypatch):
    points = _mock_road_graph(monkeypatch, connected=False)
    assert vrp_solver.build_road_distance_matrix(points) is None


def test_missing_road_graph_does_not_produce_distance_matrix(monkeypatch):
    monkeypatch.setattr(vrp_solver, "build_road_graph", lambda *args, **kwargs: None)
    assert vrp_solver.build_road_distance_matrix([
        {"lat": 13, "lng": 77.60}, {"lat": 13, "lng": 77.62}
    ]) is None


@pytest.mark.parametrize("distance", [None, -1, float("nan"), float("inf")])
def test_invalid_provider_distance_is_not_a_verified_matrix(monkeypatch, distance):
    vrp_solver._fetch_matrix_block.cache_clear()
    monkeypatch.setattr(vrp_solver, "stadia_matrix", lambda *args: {
        "sources_to_targets": [[{"distance": distance}]]
    })
    try:
        assert vrp_solver.build_stadia_distance_matrix([{"lat": 13, "lng": 77.60}]) is None
    finally:
        vrp_solver._fetch_matrix_block.cache_clear()
