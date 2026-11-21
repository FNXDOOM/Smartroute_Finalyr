"""Small server-side client for Stadia geocoding and Valhalla routing."""

import json
import threading
import time
from functools import lru_cache
from urllib.parse import quote, unquote, urlencode

import httpx

from config import (
    STADIA_API_KEY,
    STADIA_CACHE_ENABLED,
    STADIA_CACHE_MAX_ENTRIES,
    STADIA_GEOCODER_URL,
    STADIA_MAP_MATCH_URL,
    STADIA_MATRIX_URL,
    STADIA_NEAREST_ROADS_URL,
    STADIA_ROUTER_URL,
    STADIA_ROUTING_COSTING,
    STADIA_TILES_URL,
    STADIA_MAP_STYLE_PATH,
)
from services import metrics
from utils.ttl_cache import CACHE_MISS, TTLCache

_HTTP_CLIENT_LOCK = threading.Lock()
_http_client: httpx.Client | None = None

# Per-process cache: N workers each keep their own copy (swap for Redis later).
_cache = TTLCache(max_entries=STADIA_CACHE_MAX_ENTRIES)
_TRAFFIC_COSTINGS = {"auto_traffic", "auto_traffic_premium"}
_MATRIX_DENIAL_COOLDOWN_SECONDS = 60
_matrix_denied_until = 0.0


class StadiaHTTPError(RuntimeError):
    """Provider failure without request URLs or credentials."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__("Stadia request failed")


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        with _HTTP_CLIENT_LOCK:
            if _http_client is None:
                _http_client = httpx.Client(
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                )
    return _http_client


def _request_json(url: str, *, params: dict | None = None, body: dict | None = None) -> dict:
    """Request a Stadia endpoint and return its JSON response."""
    if not STADIA_API_KEY:
        raise RuntimeError("Stadia API is not configured on the server")

    query = dict(params or {})
    query["api_key"] = STADIA_API_KEY
    request_url = f"{url}?{urlencode(query)}"
    headers = {"Accept": "application/json", "User-Agent": "SmartRouteAI/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"

    try:
        response = _get_http_client().request(
            "POST" if body is not None else "GET",
            request_url,
            headers=headers,
            json=body,
            timeout=10.0,
        )
        if response.status_code >= 400:
            raise StadiaHTTPError(response.status_code)
        return response.json()
    except RuntimeError:
        raise
    except Exception:
        # Never include the request URL or exception text: both can carry the API key.
        raise RuntimeError("Stadia request failed") from None


def _request_bytes(url: str, *, params: dict | None = None) -> tuple[bytes, str]:
    """Request a Stadia endpoint and return its raw response body."""
    if not STADIA_API_KEY:
        raise RuntimeError("Stadia API is not configured on the server")

    query = dict(params or {})
    query["api_key"] = STADIA_API_KEY
    request_url = f"{url}?{urlencode(query)}"
    try:
        response = _get_http_client().get(
            request_url,
            headers={"Accept": "*/*", "User-Agent": "SmartRouteAI/1.0"},
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise RuntimeError("Stadia map resource request failed")
        content_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
        return response.content, content_type
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError("Stadia map resource request failed") from None


def _round_coord(value: float) -> float:
    return round(float(value), 5)


def _locations_key(locations: list[dict]) -> tuple:
    return tuple(
        (_round_coord(point["lat"]), _round_coord(point.get("lng", point.get("lon"))))
        for point in locations
    )


def _cached(endpoint: str, key, ttl_seconds: int, compute):
    """Return a cached result or compute and cache one; failures are never cached."""
    if not STADIA_CACHE_ENABLED:
        return compute()
    cached = _cache.get((endpoint, key))
    if cached is not CACHE_MISS:
        metrics.STADIA_CACHE_HITS.labels(endpoint).inc()
        return cached
    metrics.STADIA_CACHE_MISSES.labels(endpoint).inc()
    result = compute()
    _cache.set((endpoint, key), result, ttl_seconds)
    return result


def fetch_stadia_style() -> dict:
    """Fetch the configured Stadia map style."""
    return _fetch_stadia_style_cached()


@lru_cache(maxsize=1)
def _fetch_stadia_style_cached() -> dict:
    """Cache the rarely-changing style so map mounts don't hit Stadia, retrying transient 502s rather than caching failures."""
    last_error = None
    for attempt in range(2):
        try:
            data, _ = _request_bytes(f"{STADIA_TILES_URL}/{STADIA_MAP_STYLE_PATH}")
            try:
                return json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("Stadia map style response was invalid") from exc
        except RuntimeError as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.2)
    raise last_error or RuntimeError("Stadia map style request failed")


def fetch_stadia_resource(resource_path: str) -> tuple[bytes, str]:
    """Fetch a validated resource from the Stadia tiles service."""
    safe_path = resource_path.strip().lstrip("/")
    if not safe_path or ".." in safe_path.split("/"):
        raise RuntimeError("Invalid Stadia map resource path")
    # Preserve @ in @2x sprite paths.
    quoted_path = quote(unquote(safe_path), safe="/@:")
    return _request_bytes(f"{STADIA_TILES_URL}/{quoted_path}")


def autocomplete(text: str, *, focus_point: str | None = None) -> dict:
    """Return location suggestions for a search term."""
    params = {"text": text, "lang": "en", "boundary.country": "IND", "size": 8}
    focus_key = None
    if focus_point:
        lng, lat = focus_point.split(",", 1)
        params["focus.point.lat"] = lat
        params["focus.point.lon"] = lng
        try:
            focus_key = (round(float(lng), 2), round(float(lat), 2))
        except ValueError:
            focus_key = focus_point
    key = (text.strip().lower(), focus_key)
    return _cached(
        "autocomplete",
        key,
        10 * 60,
        lambda: _request_json(f"{STADIA_GEOCODER_URL}/autocomplete", params=params),
    )


def reverse_geocode(lat: float, lng: float) -> dict:
    """Resolve coordinates to a nearby address."""
    key = (round(float(lat), 4), round(float(lng), 4))
    return _cached(
        "reverse_geocode",
        key,
        24 * 60 * 60,
        lambda: _request_json(
            f"{STADIA_GEOCODER_URL}/reverse", params={"point.lat": lat, "point.lon": lng}
        ),
    )


def forward_geocode(text: str) -> dict:
    """Resolve a place name to matching locations."""
    key = text.strip().lower()
    return _cached(
        "forward_geocode",
        key,
        60 * 60,
        lambda: _request_json(
            f"{STADIA_GEOCODER_URL}/search",
            params={"text": text, "lang": "en", "boundary.country": "IND", "size": 8},
        ),
    )


def route(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    *,
    costing: str | None = None,
) -> dict:
    """Return a route between two coordinates."""
    return route_many([
        {"lat": from_lat, "lon": from_lng},
        {"lat": to_lat, "lon": to_lng},
    ], costing=costing)


def route_many(locations: list[dict], *, costing: str | None = None) -> dict:
    """Return a route through an ordered list of locations."""
    selected_costing = costing or STADIA_ROUTING_COSTING
    body = {
        "locations": locations,
        "costing": selected_costing,
        "units": "kilometers",
        "directions_options": {"units": "kilometers"},
    }
    if selected_costing in _TRAFFIC_COSTINGS:
        # type 0 = depart now (live traffic).
        body["date_time"] = {"type": 0}
    ttl = 5 * 60 if selected_costing in _TRAFFIC_COSTINGS else 60 * 60
    key = (selected_costing, _locations_key(locations))
    return _cached("route", key, ttl, lambda: _request_json(STADIA_ROUTER_URL, body=body))


def nearest_roads(locations: list[dict]) -> dict:
    """Snap locations to their nearest roads."""
    key = _locations_key(locations)
    return _cached(
        "nearest_roads",
        key,
        60 * 60,
        lambda: _request_json(
            STADIA_NEAREST_ROADS_URL, body={"locations": locations, "verbose": True}
        ),
    )


def _request_matrix(body):
    global _matrix_denied_until
    if time.monotonic() < _matrix_denied_until:
        raise StadiaHTTPError(403)
    try:
        return _request_json(STADIA_MATRIX_URL, body=body)
    except StadiaHTTPError as error:
        if error.status_code == 403:
            # A matrix entitlement denial is not specific to one pool. Keep
            # using standard routing, and probe again after a short cooldown.
            _matrix_denied_until = time.monotonic() + _MATRIX_DENIAL_COOLDOWN_SECONDS
        raise


def matrix(sources: list[dict], targets: list[dict], *, costing: str | None = None) -> dict:
    """Return a travel-cost matrix for source and target locations."""
    selected_costing = costing or STADIA_ROUTING_COSTING
    key = (selected_costing, _locations_key(sources), _locations_key(targets))
    ttl = 5 * 60 if selected_costing in _TRAFFIC_COSTINGS else 60 * 60
    return _cached(
        "matrix",
        key,
        ttl,
        lambda: _request_matrix(
            {
                "sources": sources,
                "targets": targets,
                "costing": selected_costing,
                "units": "kilometers",
            },
        ),
    )


def map_match(locations: list[dict], *, costing: str | None = None) -> dict:
    """Match an ordered coordinate trace to roads."""
    selected_costing = costing or STADIA_ROUTING_COSTING
    key = (selected_costing, _locations_key(locations))
    return _cached(
        "map_match",
        key,
        60 * 60,
        lambda: _request_json(
            STADIA_MAP_MATCH_URL,
            body={
                "shape": locations,
                "costing": selected_costing,
                "units": "kilometers",
                "linear_references": True,
            },
        ),
    )


def _decode_polyline(encoded: str, precision: int = 6) -> list[list[float]]:
    """Decode an encoded route polyline into coordinates."""
    coordinates = []
    index = lat = lng = 0
    factor = 10 ** precision
    while index < len(encoded):
        shift = result = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        shift = result = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        coordinates.append([lng / factor, lat / factor])
    return coordinates


def extract_route_details(data: dict) -> dict:
    """Normalize Stadia/Valhalla output: geometry stays the single stitched polyline callers expect, legs split it per consecutive pair."""
    trip = data.get("trip") or {}
    geometry: list[list[float]] = []
    maneuvers: list[dict] = []
    legs: list[dict] = []
    for index, leg in enumerate(trip.get("legs", []) or []):
        shape = leg.get("shape")
        decoded = _decode_polyline(shape) if shape else []
        begin_shape_index = max(0, len(geometry) - 1)
        if decoded:
            geometry.extend(decoded if not geometry else decoded[1:])
        end_shape_index = max(0, len(geometry) - 1)
        leg_summary = leg.get("summary") or {}
        legs.append({
            "index": index,
            "geometry": decoded,
            "distanceMeters": float(leg_summary.get("length") or 0) * 1000,
            "durationSeconds": float(leg_summary.get("time") or 0),
            "begin_shape_index": begin_shape_index,
            "end_shape_index": end_shape_index,
        })
        for maneuver in leg.get("maneuvers", []) or []:
            instruction = (
                maneuver.get("verbal_pre_transition_instruction")
                or maneuver.get("verbal_instruction")
                or maneuver.get("instruction")
            )
            maneuvers.append({
                "instruction": instruction,
                "street_names": maneuver.get("street_names") or [],
                "length_km": maneuver.get("length") or 0,
                "duration_seconds": maneuver.get("time") or 0,
                "type": maneuver.get("type"),
                "begin_shape_index": maneuver.get("begin_shape_index"),
                "end_shape_index": maneuver.get("end_shape_index"),
            })
    summary = trip.get("summary") or {}
    return {
        "distanceMeters": float(summary.get("length") or 0) * 1000,
        "durationSeconds": float(summary.get("time") or 0),
        "geometry": geometry,
        "legs": legs,
        "maneuvers": maneuvers,
    }


def extract_nearest_point(data) -> dict | None:
    """Valhalla /locate returns a bare list (one entry per input), not a dict, so don't assume the response has .get()."""
    if isinstance(data, list):
        candidates = data
    else:
        candidates = (
            data.get("locations")
            or data.get("snapped_points")
            or data.get("results")
            or []
        )
        if isinstance(candidates, dict):
            candidates = [candidates]

    if not candidates:
        return None
    point = candidates[0] or {}

    # Snapped coords live in nested edges/nodes.
    nested = point.get("location") or point.get("point") or {}
    if not nested:
        nested = next(iter(point.get("edges") or point.get("nodes") or []), {}) or {}

    lat = point.get(
        "lat",
        point.get(
            "latitude",
            nested.get("correlated_lat", nested.get("lat", nested.get("latitude"))),
        ),
    )
    lng = point.get(
        "lon",
        point.get(
            "lng",
            point.get(
                "longitude",
                nested.get("correlated_lon", nested.get("lon", nested.get("lng", nested.get("longitude")))),
            ),
        ),
    )
    if lat is None or lng is None:
        return None
    return {"lat": float(lat), "lng": float(lng), "raw": point}
