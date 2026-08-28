from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.user import User
from services.stadia_client import autocomplete, forward_geocode, reverse_geocode
from utils.auth_utils import get_current_user
from utils.geo import is_india_location

router = APIRouter()


def _label(properties: dict, fallback: str) -> str:
    return properties.get("label") or properties.get("name") or fallback


@router.get("/suggest")
def suggest_locations(
    query: str = Query(..., min_length=3, max_length=200),
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lng: Optional[float] = Query(None, ge=-180, le=180),
    _: User = Depends(get_current_user),
):
    if (lat is None) != (lng is None):
        raise HTTPException(status_code=422, detail="lat and lng must be provided together")
    try:
        data = autocomplete(query, focus_point=f"{lng},{lat}" if lat is not None else None)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    results = []
    for feature in data.get("features", []):
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) < 2:
            continue
        lng_value, lat_value = coordinates[:2]
        if not is_india_location(lat_value, lng_value):
            continue
        properties = feature.get("properties", {})
        results.append({
            "lat": lat_value,
            "lng": lng_value,
            "label": _label(properties, query),
            "raw": feature,
        })
    return results


@router.get("/reverse")
def reverse_location(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    _: User = Depends(get_current_user),
):
    if not is_india_location(lat, lng):
        raise HTTPException(status_code=422, detail="Location is outside India")
    try:
        data = reverse_geocode(lat, lng)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    feature = (data.get("features") or [None])[0]
    if not feature:
        raise HTTPException(status_code=404, detail="Location not found")
    return {
        "lat": lat,
        "lng": lng,
        "label": _label(feature.get("properties", {}), "Selected map location"),
    }


@router.get("/search")
def search_locations(
    query: str = Query(..., min_length=2, max_length=200),
    _: User = Depends(get_current_user),
):
    try:
        data = forward_geocode(query)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    results = []
    for feature in data.get("features", []):
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) < 2:
            continue
        lng_value, lat_value = coordinates[:2]
        if not is_india_location(lat_value, lng_value):
            continue
        properties = feature.get("properties", {})
        results.append({
            "lat": lat_value,
            "lng": lng_value,
            "label": _label(properties, query),
            "raw": feature,
        })
    return results
