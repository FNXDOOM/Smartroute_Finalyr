from datetime import datetime, timezone
from types import SimpleNamespace
import pytest

from services import carpool_matching as matching


def riders():
    return [
        SimpleNamespace(id=5, request_time=datetime.now(timezone.utc),
                        pickup_lat=12.997038, pickup_lng=77.669131,
                        dest_lat=13.0372354, dest_lng=77.787191),
        SimpleNamespace(id=4, request_time=datetime.now(timezone.utc),
                        pickup_lat=13.008625, pickup_lng=77.693211,
                        dest_lat=13.027276, dest_lng=77.731848),
    ]


def test_same_road_riders_not_rejected_by_straight_line(monkeypatch):
    # Road order: pickup A -> pickup B -> destination B -> destination A.
    positions = [0, 3, 15, 9]
    monkeypatch.setattr(matching, "matrix", lambda *a, **k: {
        "sources_to_targets": [
            [{"distance": abs(x - y)} for y in positions] for x in positions
        ]
    })
    requests = riders()
    assert matching.pickup_corridor_distance_meters(*requests) > 150
    assert matching.road_detour_compatible(requests)
    groups, ids = matching.find_cross_cell_corridor_groups(requests)
    assert len(groups) == 1
    assert ids == {4, 5}


def test_excessive_road_detour_rejected(monkeypatch):
    distances = [[0, 20, 10, 20], [20, 0, 20, 10],
                 [10, 20, 0, 20], [20, 10, 20, 0]]
    monkeypatch.setattr(matching, "matrix", lambda *a, **k: {
        "sources_to_targets": [[{"distance": d} for d in row] for row in distances]
    })
    assert not matching.road_detour_compatible(riders())


def test_routing_failure_does_not_create_pool(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("routing unavailable")
    monkeypatch.setattr(matching, "matrix", fail)
    monkeypatch.setattr(matching, "route", fail)
    with pytest.raises(RuntimeError, match="matching could not be evaluated"):
        matching.road_detour_compatible(riders())


def test_missing_provider_skips_route_fallback(monkeypatch):
    calls = []

    def unconfigured(*args, **kwargs):
        raise RuntimeError("Stadia API is not configured on the server")

    def route_spy(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("fallback must not be attempted")

    monkeypatch.setattr(matching, "matrix", unconfigured)
    monkeypatch.setattr(matching, "route", route_spy)
    with pytest.raises(RuntimeError, match="matching could not be evaluated"):
        matching.road_detour_compatible(riders())
    assert calls == []


def test_matrix_denial_falls_back_to_standard_routes(monkeypatch, caplog):
    def denied(*args, **kwargs):
        raise RuntimeError("sensitive upstream URL must not be logged")
    requests = riders()
    positions = {
        (requests[0].pickup_lat, requests[0].pickup_lng): 0,
        (requests[1].pickup_lat, requests[1].pickup_lng): 3,
        (requests[0].dest_lat, requests[0].dest_lng): 15,
        (requests[1].dest_lat, requests[1].dest_lng): 9,
    }
    def standard_route(lat1, lon1, lat2, lon2, **kwargs):
        return {"trip": {"units": "kilometers", "status": 0, "summary": {
            "length": abs(positions[(lat1, lon1)] - positions[(lat2, lon2)])
        }}}
    monkeypatch.setattr(matching, "matrix", denied)
    monkeypatch.setattr(matching, "route", standard_route)
    groups, ids = matching.find_cross_cell_corridor_groups(requests)
    assert len(groups) == 1
    assert ids == {4, 5}
    assert "trying standard road routes" in caplog.text
    assert "sensitive upstream" not in caplog.text
