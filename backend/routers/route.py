from datetime import datetime
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models.cluster_run import ClusterRun
from models.route_plan import RoutePlan
from models.route_waypoint import RouteWaypointRecord
from models.user import User
from models.vehicle import Vehicle
from models.virtual_stop import VirtualStop
from schemas.route import (
    OptimizedRouteResponse,
    RouteHistoryResponse,
    RoutePlanResponse,
    RouteSolution,
    RouteWaypoint,
    RouteWaypointRecordResponse,
    VRPRequest,
)
from services.routing.vrp_solver import solve_vrp
from services.notifications import create_notification, create_notifications_for_users
from utils.auth_utils import get_current_user

router = APIRouter()



@router.post("/optimize", response_model=OptimizedRouteResponse)
def optimize_routes(
    payload: VRPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
        cluster_run = db.query(ClusterRun).filter(ClusterRun.id == payload.source_cluster_run_id).first()
        if not cluster_run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster run not found")

    vehicles = (
        db.query(Vehicle)
        .filter(Vehicle.id.in_(payload.vehicle_ids))
        .order_by(Vehicle.id.asc())
        .all()
    )
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
        .filter(VirtualStop.id.in_(payload.virtual_stop_ids))
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

    capacities = [vehicle.capacity for vehicle in vehicles]
    stops = [{"lat": payload.depot_lat, "lng": payload.depot_lng, "demand": 0, "stop_id": None}]
    for virtual_stop in virtual_stops:
        stops.append(
            {
                "lat": virtual_stop.lat,
                "lng": virtual_stop.lng,
                "demand": max(1, int(virtual_stop.passenger_count)),
                "stop_id": virtual_stop.id,
            }
        )

    solution = solve_vrp(
        stops=stops,
        num_vehicles=len(vehicles),
        vehicle_capacity=min(capacities) if capacities else 1,
        vehicle_capacities=capacities,
    )

    if solution["status"] == "no_solution":
        return OptimizedRouteResponse(status="no_solution", routes=[], unassigned_stops=payload.virtual_stop_ids)

    stop_lookup = {idx: stop for idx, stop in enumerate(stops)}
    used_stop_ids: List[int] = []
    route_solutions: List[RouteSolution] = []
    persisted_route_ids: List[str] = []

    for route_data in solution["routes"]:
        vehicle_idx = route_data["vehicle_idx"]
        actual_vehicle = vehicles[vehicle_idx]
        route_id = f"route-{actual_vehicle.id}-{uuid4().hex[:8]}"
        persisted_route_ids.append(route_id)

        waypoint_payloads: List[dict] = [
            {
                "stop_id": None,
                "lat": payload.depot_lat,
                "lng": payload.depot_lng,
                "waypoint_type": "depot",
                "passenger_ids": [],
            }
        ]

        for stop_index in route_data["stop_indices"][1:]:
            stop = stop_lookup[stop_index]
            if stop.get("stop_id") is None:
                continue
            virtual_stop = next(vs for vs in virtual_stops if vs.id == stop["stop_id"])
            used_stop_ids.append(virtual_stop.id)
            passenger_ids = [request.id for request in virtual_stop.ride_requests]
            waypoint_payloads.append(
                {
                    "stop_id": virtual_stop.id,
                    "lat": virtual_stop.lat,
                    "lng": virtual_stop.lng,
                    "waypoint_type": "pickup",
                    "passenger_ids": passenger_ids,
                }
            )

        waypoint_payloads.append(
            {
                "stop_id": None,
                "lat": payload.depot_lat,
                "lng": payload.depot_lng,
                "waypoint_type": "depot",
                "passenger_ids": [],
            }
        )

        estimated_duration = float(route_data["distance_m"]) / 8.33 if route_data["distance_m"] else 0.0
        route_solutions.append(
            RouteSolution(
                route_id=route_id,
                vehicle_id=actual_vehicle.id,
                waypoints=[RouteWaypoint(**waypoint) for waypoint in waypoint_payloads],
                total_distance_meters=float(route_data["distance_m"]),
                estimated_duration_seconds=estimated_duration,
            )
        )

        actual_vehicle.assigned_route_id = route_id
        actual_vehicle.status = "active"

        route_plan = RoutePlan(
            route_id=route_id,
            vehicle_id=actual_vehicle.id,
            source_cluster_run_id=payload.source_cluster_run_id,
            status="solved",
            depot_lat=payload.depot_lat,
            depot_lng=payload.depot_lng,
            total_distance_meters=float(route_data["distance_m"]),
            estimated_duration_seconds=estimated_duration,
            created_by_user_id=current_user.id,
            route_metadata={
                "vehicle_capacity": actual_vehicle.capacity,
                "assigned_stop_ids": [wp["stop_id"] for wp in waypoint_payloads if wp["stop_id"] is not None],
                "source_cluster_run_id": payload.source_cluster_run_id,
            },
        )
        db.add(route_plan)
        db.flush()

        passenger_user_ids = []
        for virtual_stop in virtual_stops:
            if virtual_stop.id in [wp["stop_id"] for wp in waypoint_payloads if wp["stop_id"] is not None]:
                passenger_user_ids.extend(request.user_id for request in virtual_stop.ride_requests)
        passenger_user_ids = sorted(set(passenger_user_ids))
        if passenger_user_ids:
            create_notifications_for_users(
                db,
                user_ids=passenger_user_ids,
                notification_type="route_assigned",
                title="Your route has been optimized",
                message=f"Your shared ride route has been assigned to vehicle {actual_vehicle.license_plate}.",
                related_entity_type="route_plan",
                related_entity_id=route_plan.id,
                metadata={
                    "route_id": route_id,
                    "vehicle_id": actual_vehicle.id,
                    "cluster_run_id": payload.source_cluster_run_id,
                },
            )

        create_notification(
            db,
            user_id=current_user.id,
            notification_type="route_optimized",
            title="Route optimization completed",
            message=f"Route {route_id} was optimized for vehicle {actual_vehicle.license_plate}.",
            related_entity_type="route_plan",
            related_entity_id=route_plan.id,
            metadata={
                "vehicle_id": actual_vehicle.id,
                "route_id": route_id,
                "cluster_run_id": payload.source_cluster_run_id,
            },
        )

        for sequence, waypoint in enumerate(waypoint_payloads):
            db.add(
                RouteWaypointRecord(
                    route_plan_id=route_plan.id,
                    sequence=sequence,
                    stop_id=waypoint["stop_id"],
                    lat=waypoint["lat"],
                    lng=waypoint["lng"],
                    waypoint_type=waypoint["waypoint_type"],
                    passenger_ids=waypoint["passenger_ids"],
                )
            )

    db.commit()

    unassigned_stops = [stop_id for stop_id in payload.virtual_stop_ids if stop_id not in set(used_stop_ids)]
    return OptimizedRouteResponse(
        status="solved",
        routes=route_solutions,
        unassigned_stops=unassigned_stops,
    )


@router.get("/history", response_model=RouteHistoryResponse)
def list_routes(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view route history",
        )

    routes = (
        db.query(RoutePlan)
        .order_by(RoutePlan.created_at.desc())
        .limit(limit)
        .all()
    )
    return RouteHistoryResponse(status="ok", routes=[RoutePlanResponse.model_validate(route) for route in routes])


@router.get("/history/{route_id}", response_model=RoutePlanResponse)
def get_route_history(
    route_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view route history",
        )

    route_plan = db.query(RoutePlan).filter(RoutePlan.route_id == route_id).first()
    if not route_plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")

    return RoutePlanResponse.model_validate(route_plan)
