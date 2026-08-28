import sys
from pathlib import Path

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
