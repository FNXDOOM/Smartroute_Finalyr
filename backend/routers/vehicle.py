from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.vehicle import Vehicle
from schemas.vehicle import (
    RouteAssignmentCandidate,
    VehicleAssignmentItem,
    VehicleAssignmentRequest,
    VehicleAssignmentResponse,
    VehicleCreate,
    VehicleResponse,
    VehicleUpdate,
)
from services.assignment.hungarian_assigner import assign_vehicles
from services.routing.vrp_solver import build_road_distance_to_targets, build_stadia_distance_matrix
from config import STADIA_API_KEY
from utils.auth_utils import get_current_user
from utils.geo import haversine_meters
from utils.ride_scope import LIVE_MODE

router = APIRouter()


@router.get("/", response_model=List[VehicleResponse])
def list_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view fleet vehicles",
        )
    query = db.query(Vehicle).filter(Vehicle.mode == LIVE_MODE)
    if current_user.role == "driver":
        query = query.filter(Vehicle.driver_user_id == current_user.id)
    return query.order_by(Vehicle.id.asc()).all()


# NOTE: /idle MUST be declared before /{vehicle_id} so FastAPI does not
# swallow the literal string "idle" as an integer path parameter.
@router.get("/idle", response_model=List[VehicleResponse])
def list_idle_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view fleet vehicles",
        )
    query = db.query(Vehicle).filter(Vehicle.mode == LIVE_MODE, Vehicle.status == "idle")
    if current_user.role == "driver":
        query = query.filter(Vehicle.driver_user_id == current_user.id)
    return (
        query
        .order_by(Vehicle.id.asc())
        .all()
    )


@router.post("/assign", response_model=VehicleAssignmentResponse)
def assign_idle_vehicles_to_routes(
    payload: VehicleAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can assign vehicles",
        )

    vehicle_query = db.query(Vehicle).filter(Vehicle.mode == LIVE_MODE, Vehicle.status == "idle")
    if current_user.role == "driver":
        vehicle_query = vehicle_query.filter(Vehicle.driver_user_id == current_user.id)
    if payload.vehicle_ids:
        vehicle_query = vehicle_query.filter(Vehicle.id.in_(payload.vehicle_ids))
    vehicles = vehicle_query.order_by(Vehicle.id.asc()).all()
    if not vehicles:
        return VehicleAssignmentResponse(status="no_idle_vehicles", assignments=[])

    routes = payload.route_candidates
    if not routes:
        return VehicleAssignmentResponse(status="no_routes", assignments=[])

    located_vehicles = [vehicle for vehicle in vehicles if vehicle.lat is not None and vehicle.lng is not None]
    route_points = [{"lat": route.lat, "lng": route.lng} for route in routes]
    road_costs = None
    if located_vehicles:
        vehicle_points = [{"lat": vehicle.lat, "lng": vehicle.lng} for vehicle in located_vehicles]
        if STADIA_API_KEY:
            road_costs = build_stadia_distance_matrix(vehicle_points, route_points)
        if road_costs is None:
            road_costs = build_road_distance_to_targets(vehicle_points, route_points)

    located_costs = {
        vehicle.id: road_costs[index]
        for index, vehicle in enumerate(located_vehicles)
    } if road_costs is not None else {}

    cost_matrix = []
    for vehicle in vehicles:
        if vehicle.id in located_costs:
            vehicle_costs = located_costs[vehicle.id]
        else:
            if vehicle.lat is None or vehicle.lng is None:
                # Missing GPS is never selected ahead of a located vehicle.
                vehicle_costs = [999_999 for _ in routes]
            else:
                # A provider/OSM outage should not make dispatch fail. This is
                # only an outage fallback; normal assignment uses road costs.
                vehicle_costs = [
                    int(haversine_meters(vehicle.lat, vehicle.lng, route.lat, route.lng))
                    for route in routes
                ]
        cost_matrix.append(vehicle_costs)

    matched_pairs = assign_vehicles(cost_matrix)
    assignments: List[VehicleAssignmentItem] = []
    matched_vehicle_indices = set()
    matched_route_indices = set()

    for vehicle_idx, route_idx in matched_pairs:
        vehicle = vehicles[vehicle_idx]
        route = routes[route_idx]
        vehicle.assigned_route_id = route.route_id
        vehicle.status = "active"
        assignments.append(
            VehicleAssignmentItem(
                vehicle_id=vehicle.id,
                route_id=route.route_id,
                cost_meters=cost_matrix[vehicle_idx][route_idx],
            )
        )
        matched_vehicle_indices.add(vehicle_idx)
        matched_route_indices.add(route_idx)

    db.commit()

    unassigned_vehicle_ids = [
        vehicle.id for idx, vehicle in enumerate(vehicles) if idx not in matched_vehicle_indices
    ]
    unassigned_route_ids = [
        route.route_id for idx, route in enumerate(routes) if idx not in matched_route_indices
    ]

    return VehicleAssignmentResponse(
        status="assigned",
        assignments=assignments,
        unassigned_vehicle_ids=unassigned_vehicle_ids,
        unassigned_route_ids=unassigned_route_ids,
    )


@router.post("/", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can create vehicles",
        )

    exists = db.query(Vehicle).filter(Vehicle.license_plate == payload.license_plate).first()
    if exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vehicle with this license plate already exists",
        )

    vehicle = Vehicle(
        license_plate=payload.license_plate,
        capacity=payload.capacity,
        mode=LIVE_MODE,
        status=payload.status or "idle",
        lat=payload.lat,
        lng=payload.lng,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.patch("/{vehicle_id}", response_model=VehicleResponse)
def update_vehicle(
    vehicle_id: int,
    payload: VehicleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can update vehicles",
        )

    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    if current_user.role == "driver" and vehicle.driver_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Vehicle is not assigned to this driver")

    if payload.status is not None:
        vehicle.status = payload.status
    if payload.lat is not None:
        vehicle.lat = payload.lat
    if payload.lng is not None:
        vehicle.lng = payload.lng
    if payload.assigned_route_id is not None:
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change vehicle route assignments",
            )
        vehicle.assigned_route_id = payload.assigned_route_id
    if payload.driver_user_id is not None:
        if current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can assign drivers")
        driver = db.query(User).filter(User.id == payload.driver_user_id, User.role == "driver").first()
        if not driver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver user not found")
        vehicle.driver_user_id = driver.id

    db.commit()
    db.refresh(vehicle)
    return vehicle
