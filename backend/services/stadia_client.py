"""Small server-side client for Stadia geocoding and Valhalla routing."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode
from urllib.request import Request, urlopen

from config import (
    STADIA_API_KEY,
    STADIA_GEOCODER_URL,
    STADIA_MAP_MATCH_URL,
    STADIA_MATRIX_URL,
    STADIA_NEAREST_ROADS_URL,
    STADIA_ROUTER_URL,
    STADIA_ROUTING_COSTING,
    STADIA_TILES_URL,
    STADIA_MAP_STYLE_PATH,
)


def _request_json(url: str, *, params: dict | None = None, body: dict | None = None) -> dict:
    if not STADIA_API_KEY:
        raise RuntimeError("Stadia API is not configured on the server")

    query = dict(params or {})
    query["api_key"] = STADIA_API_KEY
    request_url = f"{url}?{urlencode(query)}"
    headers = {"Accept": "application/json", "User-Agent": "SmartRouteAI/1.0"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    request = Request(request_url, data=data, headers=headers, method="POST" if body else "GET")
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Stadia request failed") from exc
    except Exception as exc:
        raise RuntimeError(f"Stadia request failed: {exc}") from exc


def _request_bytes(url: str, *, params: dict | None = None) -> tuple[bytes, str]:
    if not STADIA_API_KEY:
        raise RuntimeError("Stadia API is not configured on the server")

    query = dict(params or {})
    query["api_key"] = STADIA_API_KEY
    request_url = f"{url}?{urlencode(query)}"
    request = Request(
        request_url,
        headers={"Accept": "*/*", "User-Agent": "SmartRouteAI/1.0"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return response.read(), response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("Stadia map resource request failed") from exc
    except Exception as exc:
        raise RuntimeError(f"Stadia map resource request failed: {exc}") from exc


def fetch_stadia_style() -> dict:
    data, _ = _request_bytes(f"{STADIA_TILES_URL}/{STADIA_MAP_STYLE_PATH}")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Stadia map style response was invalid") from exc


def fetch_stadia_resource(resource_path: str) -> tuple[bytes, str]:
    safe_path = resource_path.strip().lstrip("/")
    if not safe_path or ".." in safe_path.split("/"):
        raise RuntimeError("Invalid Stadia map resource path")
    # Stadia's sprite assets use the literal `@2x` suffix. Preserve `@` while
    # still quoting spaces and other unsafe path characters.
    quoted_path = quote(unquote(safe_path), safe="/@:")
    return _request_bytes(f"{STADIA_TILES_URL}/{quoted_path}")


def autocomplete(text: str, *, focus_point: str | None = None) -> dict:
    params = {"text": text, "lang": "en", "boundary.country": "IND", "size": 8}
    if focus_point:
        lng, lat = focus_point.split(",", 1)
        params["focus.point.lat"] = lat
        params["focus.point.lon"] = lng
    return _request_json(f"{STADIA_GEOCODER_URL}/autocomplete", params=params)


def reverse_geocode(lat: float, lng: float) -> dict:
    return _request_json(
        f"{STADIA_GEOCODER_URL}/reverse", params={"point.lat": lat, "point.lon": lng}
    )


def forward_geocode(text: str) -> dict:
    return _request_json(
        f"{STADIA_GEOCODER_URL}/search",
        params={"text": text, "lang": "en", "boundary.country": "IND", "size": 8},
    )


def route(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    *,
    costing: str | None = None,
) -> dict:
    return route_many([
        {"lat": from_lat, "lon": from_lng},
        {"lat": to_lat, "lon": to_lng},
    ], costing=costing)


def route_many(locations: list[dict], *, costing: str | None = None) -> dict:
    selected_costing = costing or STADIA_ROUTING_COSTING
    body = {
        "locations": locations,
        "costing": selected_costing,
        "units": "kilometers",
        "directions_options": {"units": "kilometers"},
    }
    if selected_costing in {"auto_traffic", "auto_traffic_premium"}:
        # Valhalla's type 0 means depart at the current time, allowing the
        # provider to apply the live traffic profile where the plan supports it.
        body["date_time"] = {"type": 0}
    return _request_json(
        STADIA_ROUTER_URL,
        body=body,
    )


def nearest_roads(locations: list[dict]) -> dict:
    return _request_json(STADIA_NEAREST_ROADS_URL, body={"locations": locations, "verbose": True})


def matrix(sources: list[dict], targets: list[dict], *, costing: str | None = None) -> dict:
    return _request_json(
        STADIA_MATRIX_URL,
        body={
            "sources": sources,
            "targets": targets,
            "costing": costing or STADIA_ROUTING_COSTING,
            "units": "kilometers",
        },
    )


def map_match(locations: list[dict], *, costing: str | None = None) -> dict:
    return _request_json(
        STADIA_MAP_MATCH_URL,
        body={
            "shape": locations,
            "costing": costing or STADIA_ROUTING_COSTING,
            "units": "kilometers",
            "linear_references": True,
        },
    )


def _decode_polyline(encoded: str, precision: int = 6) -> list[list[float]]:
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
    """Normalize Stadia/Valhalla route output for the rest of the app."""
    trip = data.get("trip") or {}
    geometry: list[list[float]] = []
    maneuvers: list[dict] = []
    for leg in trip.get("legs", []) or []:
        shape = leg.get("shape")
        if shape:
            decoded = _decode_polyline(shape)
            geometry.extend(decoded if not geometry else decoded[1:])
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
        "maneuvers": maneuvers,
    }


def extract_nearest_point(data) -> dict | None:
    """Handle the response shapes used by Stadia's nearest-roads (Valhalla
    /locate) endpoint. Valhalla's /locate returns a bare JSON *list* — one
    entry per input location — not a dict wrapping a "locations" key, so this
    must not assume the top-level response has a .get() method.
    """
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

    # Valhalla nests the snapped coordinate inside the first correlated
    # "edges" (or "nodes") entry rather than at the top level of each
    # location result.
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
