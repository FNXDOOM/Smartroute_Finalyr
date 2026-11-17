from datetime import datetime, timezone
from types import SimpleNamespace

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
    assert not matching.road_detour_compatible(riders())
