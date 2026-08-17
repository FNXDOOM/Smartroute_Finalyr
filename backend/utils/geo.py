"""Shared geospatial utilities — single source of truth for haversine distance."""
from math import asin, cos, radians, sin, sqrt

INDIA_BOUNDS = {
    "min_lat": 6.5,
    "max_lat": 35.7,
    "min_lng": 68.1,
    "max_lng": 97.4,
}


def is_india_location(lat: float, lng: float) -> bool:
    return (
        INDIA_BOUNDS["min_lat"] <= lat <= INDIA_BOUNDS["max_lat"]
        and INDIA_BOUNDS["min_lng"] <= lng <= INDIA_BOUNDS["max_lng"]
    )


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in metres between two lat/lng points."""
    R = 6_371_000
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * R * asin(sqrt(a))
