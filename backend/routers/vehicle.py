from math import radians, cos, sin, asin, sqrt
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.models.vehicle import Vehicle
from backend.models.virtual_stop import VirtualStop
from backend.schemas.vehicle import (
    RouteAssignmentCandidate,
    VehicleAssignmentItem,
    VehicleAssignmentRequest,
    VehicleAssignmentResponse,
    VehicleCreate,
    VehicleResponse,
    VehicleUpdate,
)
from backend.services.assignment.hungarian_assigner import assign_vehicles
from backend.utils.auth_utils import get_current_user

router = APIRouter()


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    radius = 6_371_000
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return int(2 * radius * asin(sqrt(a)))


@router.get("/", response_model=List[VehicleResponse])
def list_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Vehicle).order_by(Vehicle.id.asc()).all()


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

    if payload.status is not None:
        vehicle.status = payload.status
    if payload.lat is not None:
        vehicle.lat = payload.lat
    if payload.lng is not None:
        vehicle.lng = payload.lng
    if payload.assigned_route_id is not None:
        vehicle.assigned_route_id = payload.assigned_route_id

    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("/idle", response_model=List[VehicleResponse])
def list_idle_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Vehicle)
        .filter(Vehicle.status == "idle")
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

    vehicle_query = db.query(Vehicle).filter(Vehicle.status == "idle")
    if payload.vehicle_ids:
        vehicle_query = vehicle_query.filter(Vehicle.id.in_(payload.vehicle_ids))
    vehicles = vehicle_query.order_by(Vehicle.id.asc()).all()
    if not vehicles:
        return VehicleAssignmentResponse(status="no_idle_vehicles", assignments=[])

    routes = payload.route_candidates
    if not routes:
        return VehicleAssignmentResponse(status="no_routes", assignments=[])

    cost_matrix = []
    for vehicle in vehicles:
        if vehicle.lat is None or vehicle.lng is None:
            vehicle_costs = [999_999 for _ in routes]
        else:
            vehicle_costs = [
                _haversine_meters(vehicle.lat, vehicle.lng, route.lat, route.lng)
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

    unassigned_vehicle_ids = [vehicle.id for idx, vehicle in enumerate(vehicles) if idx not in matched_vehicle_indices]
    unassigned_route_ids = [route.route_id for idx, route in enumerate(routes) if idx not in matched_route_indices]

    return VehicleAssignmentResponse(
        status="assigned",
        assignments=assignments,
        unassigned_vehicle_ids=unassigned_vehicle_ids,
        unassigned_route_ids=unassigned_route_ids,
    )
