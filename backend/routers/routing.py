from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.user import User
from services.stadia_client import (
    extract_nearest_point,
    extract_route_details,
    map_match,
    matrix,
    nearest_roads,
    route,
)
from utils.auth_utils import get_current_user
from utils.geo import is_india_location

router = APIRouter()


@router.get("/route")
def road_route(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lng: float = Query(..., ge=-180, le=180),
    to_lat: float = Query(..., ge=-90, le=90),
    to_lng: float = Query(..., ge=-180, le=180),
    traffic: bool = Query(False),
    _: User = Depends(get_current_user),
):
    if not all(
        is_india_location(lat, lng)
        for lat, lng in ((from_lat, from_lng), (to_lat, to_lng))
    ):
        raise HTTPException(status_code=422, detail="Route locations must be within India")
    try:
        data = route(from_lat, from_lng, to_lat, to_lng, costing="auto_traffic" if traffic else None)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    details = extract_route_details(data)
    if not details["geometry"]:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No drivable route found")
    return details


@router.get("/nearest-road")
def nearest_road(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    _: User = Depends(get_current_user),
):
    if not is_india_location(lat, lng):
        raise HTTPException(status_code=422, detail="Location is outside India")
    try:
        data = nearest_roads([{"lat": lat, "lon": lng}])
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    point = extract_nearest_point(data)
    if not point:
        raise HTTPException(status_code=404, detail="No nearby road found")
    if not is_india_location(point["lat"], point["lng"]):
        raise HTTPException(status_code=502, detail="Nearest road is outside the service area")
    return point


@router.post("/map-match")
def match_trace(
    locations: list[dict],
    _: User = Depends(get_current_user),
):
    if not 2 <= len(locations) <= 100:
        raise HTTPException(status_code=422, detail="At least 2 and at most 100 GPS points are required")
    normalized = []
    for point in locations:
        lat = point.get("lat")
        lng = point.get("lng", point.get("lon"))
        if lat is None or lng is None or not is_india_location(float(lat), float(lng)):
            raise HTTPException(status_code=422, detail="All trace points must be within India")
        normalized.append({"lat": float(lat), "lon": float(lng)})
    try:
        details = extract_route_details(map_match(normalized))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return details


@router.post("/matrix")
def route_matrix(
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin or driver users can request a route matrix")
    sources = payload.get("sources") or []
    targets = payload.get("targets") or []
    if not 1 <= len(sources) <= 25 or not 1 <= len(targets) <= 25:
        raise HTTPException(status_code=422, detail="Matrix sources and targets must each contain 1 to 25 points")
    normalized_sources = []
    normalized_targets = []
    for collection, output in ((sources, normalized_sources), (targets, normalized_targets)):
        for point in collection:
            lat = point.get("lat")
            lng = point.get("lng", point.get("lon"))
            if lat is None or lng is None or not is_india_location(float(lat), float(lng)):
                raise HTTPException(status_code=422, detail="All matrix points must be within India")
            output.append({"lat": float(lat), "lon": float(lng)})
    try:
        return matrix(normalized_sources, normalized_targets, costing=payload.get("costing"))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
