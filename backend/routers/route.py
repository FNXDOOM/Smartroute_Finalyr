from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models.cluster_run import ClusterRun
from models.route_plan import RoutePlan
from models.user import User
from models.vehicle import Vehicle
from models.virtual_stop import VirtualStop
from schemas.route import (
    OptimizedRouteResponse,
    RouteHistoryResponse,
    RouteLeg,
    RoutePlanResponse,
    RouteSolution,
    RouteWaypoint,
    RouteWaypointRecordResponse,
    VRPRequest,
)
from services.routing.shared_route_builder import (
    build_shared_routes,
    persist_shared_route,
    resolve_route_geometry,
)
from services.notifications import create_notification, create_notifications_for_users
from utils.auth_utils import get_current_user
from utils.ride_scope import LIVE_MODE

router = APIRouter()


@router.post("/optimize", response_model=OptimizedRouteResponse)
def optimize_routes(
    payload: VRPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build and persist optimized routes for eligible clusters."""
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can optimize routes",
        )

    if not payload.vehicle_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one vehicle is required for route optimization",
        )

    if payload.source_cluster_run_id is not None:
        cluster_run = db.query(ClusterRun).filter(
            ClusterRun.id == payload.source_cluster_run_id,
            ClusterRun.mode == LIVE_MODE,
        ).first()
        if not cluster_run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster run not found")

    vehicle_query = db.query(Vehicle).filter(Vehicle.id.in_(payload.vehicle_ids))
    if current_user.role == "driver":
        vehicle_query = vehicle_query.filter(Vehicle.driver_user_id == current_user.id)
    vehicles = vehicle_query.order_by(Vehicle.id.asc()).all()
    if len(vehicles) != len(payload.vehicle_ids):
        found_ids = {vehicle.id for vehicle in vehicles}
        missing_ids = [vehicle_id for vehicle_id in payload.vehicle_ids if vehicle_id not in found_ids]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Some vehicles were not found", "missing_vehicle_ids": missing_ids},
        )

    if not payload.virtual_stop_ids:
        return OptimizedRouteResponse(status="no_virtual_stops", routes=[], unassigned_stops=[])

    virtual_stops = (
        db.query(VirtualStop)
        .filter(VirtualStop.id.in_(payload.virtual_stop_ids), VirtualStop.mode == LIVE_MODE)
        .order_by(VirtualStop.id.asc())
        .all()
    )
    if len(virtual_stops) != len(payload.virtual_stop_ids):
        found_ids = {stop.id for stop in virtual_stops}
        missing_ids = [stop_id for stop_id in payload.virtual_stop_ids if stop_id not in found_ids]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Some virtual stops were not found", "missing_virtual_stop_ids": missing_ids},
        )

    built_routes = build_shared_routes(
        vehicles=vehicles,
        virtual_stops=virtual_stops,
        depot_lat=payload.depot_lat,
        depot_lng=payload.depot_lng,
    )
    if not built_routes:
        return OptimizedRouteResponse(
            status="no_solution",
            routes=[],
            unassigned_stops=payload.virtual_stop_ids,
        )

    used_stop_ids: List[int] = []
    route_solutions: List[RouteSolution] = []

    for built in built_routes:
        actual_vehicle = vehicles[built.vehicle_index]
        persisted = persist_shared_route(
            db,
            built,
            vehicle=actual_vehicle,
            mode=LIVE_MODE,
            created_by_user_id=current_user.id,
            source_cluster_run_id=payload.source_cluster_run_id,
        )
        used_stop_ids.extend(built.stop_ids)
        route_solutions.append(
            RouteSolution(
                route_id=persisted.route_id,
                vehicle_id=actual_vehicle.id,
                waypoints=[RouteWaypoint(**waypoint) for waypoint in built.waypoints],
                total_distance_meters=float(built.distance_m),
                estimated_duration_seconds=float(built.duration_s),
                geometry=built.geometry,
                maneuvers=built.maneuvers,
                legs=[RouteLeg(**leg) for leg in built.legs],
            )
        )

        passenger_user_ids = persisted.passenger_user_ids
        if passenger_user_ids:
            create_notifications_for_users(
                db,
                user_ids=passenger_user_ids,
                notification_type="route_assigned",
                title="Your route has been optimized",
                message=f"Your shared ride route has been assigned to vehicle {actual_vehicle.license_plate}.",
                related_entity_type="route_plan",
                related_entity_id=persisted.route_plan.id,
                metadata={
                    "route_id": persisted.route_id,
                    "vehicle_id": actual_vehicle.id,
                    "cluster_run_id": payload.source_cluster_run_id,
                },
            )

        create_notification(
            db,
            user_id=current_user.id,
            notification_type="route_optimized",
            title="Route optimization completed",
            message=f"Route {persisted.route_id} was optimized for vehicle {actual_vehicle.license_plate}.",
            related_entity_type="route_plan",
            related_entity_id=persisted.route_plan.id,
            metadata={
                "vehicle_id": actual_vehicle.id,
                "route_id": persisted.route_id,
                "cluster_run_id": payload.source_cluster_run_id,
            },
        )

    db.commit()

    unassigned_stops = [stop_id for stop_id in payload.virtual_stop_ids if stop_id not in set(used_stop_ids)]
    return OptimizedRouteResponse(
        status="solved",
        routes=route_solutions,
        unassigned_stops=unassigned_stops,
    )


def _route_plan_response(route_plan: RoutePlan) -> RoutePlanResponse:
    """Route plan with its geometry, legs and problem promoted out of metadata."""
    metadata = route_plan.route_metadata or {}
    response = RoutePlanResponse.model_validate(route_plan)
    return response.model_copy(update={
        "geometry": metadata.get("geometry") or [],
        "legs": [RouteLeg(**leg) for leg in (metadata.get("legs") or [])],
        "problem": str(metadata.get("problem") or "cvrp"),
    })


@router.get("/history", response_model=RouteHistoryResponse)
def list_routes(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return route plans visible to the current user."""
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view route history",
        )

    routes = (
        db.query(RoutePlan)
        .filter(RoutePlan.mode == LIVE_MODE)
        .order_by(RoutePlan.created_at.desc())
        .limit(limit)
        .all()
    )
    return RouteHistoryResponse(
        status="ok",
        routes=[_route_plan_response(route) for route in routes],
    )


@router.get("/history/{route_id}", response_model=RoutePlanResponse)
def get_route_history(
    route_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return recently generated route plans."""
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view route history",
        )

    route_plan = db.query(RoutePlan).filter(
        RoutePlan.route_id == route_id,
        RoutePlan.mode == LIVE_MODE,
    ).first()
    if not route_plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")

    # Plans written by the automatic dispatch job carry no road geometry, so a
    # driver opening the map is the first chance to fetch it (cached on the
    # plan, exactly once, for every later caller).
    resolve_route_geometry(db, route_plan)

    return _route_plan_response(route_plan)
