"""Stadia response cache: hits, rounding, costing keys, failures, kill switch, TTL."""

import pytest

from services import stadia_client
from utils.ttl_cache import TTLCache

LOCATIONS = [
    {"lat": 12.9716, "lng": 77.5946},
    {"lat": 12.9352, "lng": 77.6245},
]


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(stadia_client, "_cache", TTLCache(max_entries=10))
    monkeypatch.setattr(stadia_client, "STADIA_CACHE_ENABLED", True)


def _counter(monkeypatch):
    calls = []

    def fake_request(url, *, params=None, body=None):
        calls.append((url, params, body))
        return {"trip": {"legs": []}}

    monkeypatch.setattr(stadia_client, "_request_json", fake_request)
    return calls


def test_cache_hit_avoids_second_upstream_call(monkeypatch):
    calls = _counter(monkeypatch)
    first = stadia_client.route(12.9716, 77.5946, 12.9352, 77.6245)
    second = stadia_client.route(12.9716, 77.5946, 12.9352, 77.6245)
    assert first == second
    assert len(calls) == 1


def test_rounding_collapses_nearly_identical_coordinates(monkeypatch):
    calls = _counter(monkeypatch)
    stadia_client.route(12.97160001, 77.59460001, 12.93520001, 77.62450001)
    stadia_client.route(12.97160002, 77.59460002, 12.93520002, 77.62450002)
    assert len(calls) == 1


def test_different_costing_uses_a_different_key(monkeypatch):
    calls = _counter(monkeypatch)
    stadia_client.route_many(LOCATIONS, costing="auto")
    stadia_client.route_many(LOCATIONS, costing="bicycle")
    assert len(calls) == 2


def test_forward_geocode_is_case_and_space_normalized(monkeypatch):
    calls = _counter(monkeypatch)
    stadia_client.forward_geocode("MG Road")
    stadia_client.forward_geocode("  mg road ")
    assert len(calls) == 1


def test_failures_are_not_cached(monkeypatch):
    calls = []

    def fail(url, *, params=None, body=None):
        calls.append(url)
        raise RuntimeError("upstream down")

    monkeypatch.setattr(stadia_client, "_request_json", fail)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            stadia_client.route(12.9716, 77.5946, 12.9352, 77.6245)
    assert len(calls) == 2


def test_disabled_cache_bypasses(monkeypatch):
    calls = _counter(monkeypatch)
    monkeypatch.setattr(stadia_client, "STADIA_CACHE_ENABLED", False)
    stadia_client.route(12.9716, 77.5946, 12.9352, 77.6245)
    stadia_client.route(12.9716, 77.5946, 12.9352, 77.6245)
    assert len(calls) == 2


def test_ttl_expiry_refetches(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(
        stadia_client, "_cache", TTLCache(max_entries=10, clock=lambda: now[0])
    )
    calls = _counter(monkeypatch)
    stadia_client.route(12.9716, 77.5946, 12.9352, 77.6245, costing="auto_traffic")
    now[0] += 301
    stadia_client.route(12.9716, 77.5946, 12.9352, 77.6245, costing="auto_traffic")
    assert len(calls) == 2


from utils.ttl_cache import CACHE_MISS, TTLCache


def test_eviction_is_oldest_first_not_lru():
    cache = TTLCache(max_entries=2)
    cache.set("a", 1, 100)
    cache.set("b", 2, 100)
    assert cache.get("a") == 1  # a was read recently, but was inserted first
    cache.set("c", 3, 100)
    assert cache.get("a") is CACHE_MISS
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_cached_results_are_isolated_from_caller_mutation(monkeypatch):
    _counter(monkeypatch)
    first = stadia_client.route(12.9716, 77.5946, 12.9352, 77.6245)
    first["trip"]["legs"].append("mutated")
    second = stadia_client.route(12.9716, 77.5946, 12.9352, 77.6245)
    assert second["trip"]["legs"] == []
