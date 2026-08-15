from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.ride_request import RideRequest
from models.route_waypoint import RouteWaypointRecord
from models.route_plan import RoutePlan
from models.vehicle import Vehicle
from schemas.ride_request import (
    RideRequestCreate,
    RideRequestResponse,
    RideRequestStatusUpdate,
)
from schemas.tracking import VehicleSnapshot
from services.notifications import create_notification
from utils.auth_utils import get_current_user
from services.clustering.h3_partitioner import get_h3_index

router = APIRouter()

# Valid ride statuses — enforced on every write
VALID_RIDE_STATUSES = {"pending", "clustered", "assigned", "arriving", "in_progress", "completed", "cancelled"}


@router.post("/request", response_model=RideRequestResponse, status_code=status.HTTP_201_CREATED)
def create_ride_request(
    ride_in: RideRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a new ride request for the authenticated passenger"""
    # Calculate Uber H3 spatial cell index
    h3_idx = get_h3_index(ride_in.pickup_lat, ride_in.pickup_lng, resolution=9)

    new_request = RideRequest(
        user_id=current_user.id,
        pickup_lat=ride_in.pickup_lat,
        pickup_lng=ride_in.pickup_lng,
        dest_lat=ride_in.dest_lat,
        dest_lng=ride_in.dest_lng,
        status="pending",
        h3_index=h3_idx,
        pickup_label=ride_in.pickup_label,
        destination_label=ride_in.destination_label,
        ride_option_id=ride_in.ride_option_id,
        ride_option_name=ride_in.ride_option_name,
        ride_option_price=ride_in.ride_option_price,
    )
    db.add(new_request)
    db.flush()
    create_notification(
        db,
        user_id=current_user.id,
        notification_type="ride_requested",
        title="Ride request created",
        message=f"Your ride request #{new_request.id} has been received and is pending clustering.",
        related_entity_type="ride_request",
        related_entity_id=new_request.id,
        metadata={"status": new_request.status, "h3_index": h3_idx},
    )
    db.commit()
    db.refresh(new_request)
    return new_request


@router.get("/my-rides", response_model=List[RideRequestResponse])
def get_my_ride_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all ride requests created by the current authenticated user"""
    rides = (
        db.query(RideRequest)
        .filter(RideRequest.user_id == current_user.id)
        .order_by(RideRequest.request_time.desc())
        .all()
    )
    return rides


@router.get("/{ride_id}", response_model=RideRequestResponse)
def get_ride_request_by_id(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ride request details by ID"""
    ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ride request #{ride_id} not found",
        )
    # Check authorization (passenger owner or admin)
    if ride.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this ride request",
        )
    return ride


@router.get("/{ride_id}/vehicle", response_model=Optional[VehicleSnapshot])
def get_ride_vehicle(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Passenger-scoped: which vehicle (if any) is currently assigned to this ride.

    Unlike /vehicle/* and /tracking/*, this endpoint has no admin/driver
    restriction — only ownership (or admin) is required, since a passenger
    needs to know their own assigned vehicle.

    Resolves via: ride.virtual_stop_id == waypoint.stop_id (and ride.id is in
    that waypoint's passenger_ids) -> waypoint.route_plan_id -> RoutePlan.vehicle_id.
    Returns null if no route has been optimized for this ride yet.
    """
    ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ride request #{ride_id} not found",
        )
    if ride.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this ride request",
        )

    if not ride.virtual_stop_id:
        return None

    candidate_waypoints = (
        db.query(RouteWaypointRecord)
        .filter(RouteWaypointRecord.stop_id == ride.virtual_stop_id)
        .all()
    )
    match = next(
        (w for w in candidate_waypoints if ride.id in (w.passenger_ids or [])),
        None,
    )
    if not match:
        return None

    route_plan = db.query(RoutePlan).filter(RoutePlan.id == match.route_plan_id).first()
    if not route_plan:
        return None

    vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
    if not vehicle:
        return None

    return VehicleSnapshot.model_validate(vehicle)


@router.get("/", response_model=List[RideRequestResponse])
def list_ride_requests(
    ride_status: Optional[str] = Query(None, alias="status", description="Filter by ride status"),
    h3_index: Optional[str] = Query(None, description="Filter by H3 spatial cell index"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List ride requests across the system. Admin/driver only."""
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can list all ride requests",
        )
    query = db.query(RideRequest)
    if ride_status:
        if ride_status not in VALID_RIDE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_RIDE_STATUSES))}",
            )
        query = query.filter(RideRequest.status == ride_status)
    if h3_index:
        query = query.filter(RideRequest.h3_index == h3_index)

    rides = query.order_by(RideRequest.request_time.desc()).offset(offset).limit(limit).all()
    return rides


@router.patch("/{ride_id}/status", response_model=RideRequestResponse)
def update_ride_request_status(
    ride_id: int,
    status_update: RideRequestStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update status of a ride request (e.g. clustered, assigned, in_progress, completed, cancelled)"""
    ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ride request #{ride_id} not found",
        )

    # Check permission
    if ride.user_id != current_user.id and current_user.role not in ["admin", "driver"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this ride status",
        )

    # Passengers may cancel their own request, but operational state changes
    # must come from dispatch/admin workflows or the driver.
    if ride.user_id == current_user.id and current_user.role == "passenger" and status_update.status != "cancelled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Passengers may only cancel their own ride requests",
        )

    old_status = ride.status
    if status_update.status not in VALID_RIDE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_RIDE_STATUSES))}",
        )
    ride.status = status_update.status
    create_notification(
        db,
        user_id=ride.user_id,
        notification_type="ride_status_updated",
        title="Ride status updated",
        message=f"Your ride request #{ride.id} changed from {old_status} to {status_update.status}.",
        related_entity_type="ride_request",
        related_entity_id=ride.id,
        metadata={"old_status": old_status, "new_status": status_update.status},
    )
    db.commit()
    db.refresh(ride)
    return ride


@router.delete("/{ride_id}", status_code=status.HTTP_200_OK)
def cancel_ride_request(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel / delete a pending or clustered ride request"""
    ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ride request #{ride_id} not found",
        )

    if ride.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to cancel this ride request",
        )

    if ride.status in ["in_progress", "completed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a ride that is already {ride.status}",
        )

    ride.status = "cancelled"
    create_notification(
        db,
        user_id=ride.user_id,
        notification_type="ride_cancelled",
        title="Ride request cancelled",
        message=f"Your ride request #{ride.id} has been cancelled.",
        related_entity_type="ride_request",
        related_entity_id=ride.id,
        metadata={"status": "cancelled"},
    )
    db.commit()
    return {"message": f"Ride request #{ride_id} has been cancelled successfully"}
