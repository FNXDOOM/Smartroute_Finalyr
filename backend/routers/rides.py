from typing import List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.ride_request import RideRequest
from models.route_waypoint import RouteWaypointRecord
from models.route_plan import RoutePlan
from models.vehicle import Vehicle
from models.cluster_run import ClusterRun
from models.tracking_event import TrackingEvent
from models.notification import Notification
from models.virtual_stop import VirtualStop
from schemas.ride_request import (
    RideRequestCreate,
    RideRequestResponse,
    RideRequestStatusUpdate,
    RideRequestBatchCreate,
    DemoSharedBatchCreate,
)
from schemas.tracking import VehicleSnapshot
from services.notifications import create_notification
from utils.auth_utils import get_current_user
from utils.geo import is_india_location
from services.clustering.h3_partitioner import get_h3_index
from utils.ride_scope import (
    LIVE_MODE,
    PRESENTATION_DEMO_MODE,
    apply_ride_scope,
    validate_ride_mode,
)

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
    if not all(
        is_india_location(lat, lng)
        for lat, lng in (
            (ride_in.pickup_lat, ride_in.pickup_lng),
            (ride_in.dest_lat, ride_in.dest_lng),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Pickup and destination must be within the supported India service area",
        )
    # Calculate Uber H3 spatial cell index
    h3_idx = get_h3_index(ride_in.pickup_lat, ride_in.pickup_lng, resolution=9)

    new_request = RideRequest(
        user_id=current_user.id,
        pickup_lat=ride_in.pickup_lat,
        pickup_lng=ride_in.pickup_lng,
        dest_lat=ride_in.dest_lat,
        dest_lng=ride_in.dest_lng,
        status="pending",
        mode=LIVE_MODE,
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


@router.post("/batch", response_model=List[RideRequestResponse], status_code=status.HTTP_201_CREATED)
def create_batch_ride_requests(
    batch_in: RideRequestBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create multiple ride requests in a single transaction"""
    created_requests = []
    for item in batch_in.requests:
        h3_idx = get_h3_index(item.pickup_lat, item.pickup_lng, resolution=9)
        req = RideRequest(
            user_id=current_user.id,
            pickup_lat=item.pickup_lat,
            pickup_lng=item.pickup_lng,
            dest_lat=item.dest_lat,
            dest_lng=item.dest_lng,
            status="pending",
            mode=LIVE_MODE,
            h3_index=h3_idx,
            pickup_label=item.pickup_label,
            destination_label=item.destination_label,
            ride_option_id=item.ride_option_id or "swift-x",
            ride_option_name=item.ride_option_name or "SwiftX",
            ride_option_price=item.ride_option_price or "₹12–15",
        )
        db.add(req)
        db.flush()
        create_notification(
            db,
            user_id=current_user.id,
            notification_type="ride_requested",
            title="Ride request created",
            message=f"Your ride request #{req.id} has been received and is pending clustering.",
            related_entity_type="ride_request",
            related_entity_id=req.id,
            metadata={"status": req.status, "h3_index": h3_idx},
        )
        created_requests.append(req)
    db.commit()
    for req in created_requests:
        db.refresh(req)
    return created_requests


@router.post("/demo-batch", response_model=List[RideRequestResponse], status_code=status.HTTP_201_CREATED)
def create_demo_clustered_riders(
    zone: str = Query("indiranagar", description="Preset cluster zone: indiranagar | koramangala"),
    demo_run_id: Optional[str] = Query(None, min_length=1, max_length=64),
    pickup_lat: Optional[float] = Query(None, ge=-90, le=90),
    pickup_lng: Optional[float] = Query(None, ge=-180, le=180),
    dest_lat: Optional[float] = Query(None, ge=-90, le=90),
    dest_lng: Optional[float] = Query(None, ge=-180, le=180),
    pickup_label: Optional[str] = Query(None, max_length=255),
    destination_label: Optional[str] = Query(None, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates 3 sample passenger ride requests in a dense cluster heading along a common corridor.
    Designed for 1-click live presentations of HDBSCAN clustering and pre-dispatch CVRP routing.
    """
    demo_run_id = demo_run_id or uuid4().hex
    custom_coordinates = (pickup_lat, pickup_lng, dest_lat, dest_lng)
    if any(value is not None for value in custom_coordinates) and not all(
        value is not None for value in custom_coordinates
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Custom demo routes require pickup_lat, pickup_lng, dest_lat, and dest_lng",
        )

    if all(value is not None for value in custom_coordinates):
        if not all(
            is_india_location(lat, lng)
            for lat, lng in ((pickup_lat, pickup_lng), (dest_lat, dest_lng))
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Pickup and destination must be within the supported India service area",
            )
        pickup_name = pickup_label or "Selected pickup"
        destination_name = destination_label or "Selected destination"
        # Keep the requests close enough to demonstrate HDBSCAN while allowing
        # the selected pickup and destination to be visible as separate points.
        pickup_offsets = [(0.0, 0.0), (0.00002, 0.00002), (-0.00002, 0.00002)]
        destination_offsets = [(0.0, 0.0), (0.00002, -0.00002), (-0.00002, -0.00002)]
        presets = [
            {
                "plat": pickup_lat + lat_offset,
                "plng": pickup_lng + lng_offset,
                "plbl": f"{pickup_name} (Rider {index + 1})",
                "dlat": dest_lat + dest_lat_offset,
                "dlng": dest_lng + dest_lng_offset,
                "dlbl": f"{destination_name} (Dropoff {index + 1})",
            }
            for index, ((lat_offset, lng_offset), (dest_lat_offset, dest_lng_offset)) in enumerate(
                zip(pickup_offsets, destination_offsets)
            )
        ]
    elif zone.lower() == "koramangala":
        presets = [
            {"plat": 12.93520, "plng": 77.62450, "plbl": "Koramangala 5th Block", "dlat": 12.9756, "dlng": 77.6066, "dlbl": "MG Road Metro"},
            {"plat": 12.93522, "plng": 77.62452, "plbl": "Koramangala 5th Block (East)", "dlat": 12.9749, "dlng": 77.6080, "dlbl": "Church Street"},
            {"plat": 12.93518, "plng": 77.62447, "plbl": "Koramangala 5th Block (West)", "dlat": 12.9734, "dlng": 77.6075, "dlbl": "Brigade Road"},
        ]
    else:
        # Indiranagar — all three within the same H3 cell (8961892eddbffff)
        presets = [
            {"plat": 12.97190, "plng": 77.64124, "plbl": "Indiranagar 100 Feet Rd", "dlat": 12.9756, "dlng": 77.6066, "dlbl": "MG Road Metro"},
            {"plat": 12.97192, "plng": 77.64126, "plbl": "Indiranagar 100 Feet Rd (East)", "dlat": 12.9749, "dlng": 77.6080, "dlbl": "Church Street"},
            {"plat": 12.97194, "plng": 77.64120, "plbl": "Indiranagar 100 Feet Rd (North)", "dlat": 12.9734, "dlng": 77.6075, "dlbl": "Brigade Road"},
        ]

    created = []
    for p in presets:
        h3_idx = get_h3_index(p["plat"], p["plng"], resolution=9)
        req = RideRequest(
            user_id=current_user.id,
            pickup_lat=p["plat"],
            pickup_lng=p["plng"],
            dest_lat=p["dlat"],
            dest_lng=p["dlng"],
            status="pending",
            mode=PRESENTATION_DEMO_MODE,
            demo_run_id=demo_run_id,
            h3_index=h3_idx,
            pickup_label=p["plbl"],
            destination_label=p["dlbl"],
            ride_option_id="swift-x",
            ride_option_name="SwiftX",
            ride_option_price="₹12–15",
        )
        db.add(req)
        db.flush()
        create_notification(
            db,
            user_id=current_user.id,
            notification_type="ride_requested",
            title="Ride request created",
            message=f"Sample ride request #{req.id} ({p['plbl']}) created and pending clustering.",
            related_entity_type="ride_request",
            related_entity_id=req.id,
            metadata={"status": req.status, "h3_index": h3_idx},
        )
        created.append(req)
    db.commit()
    for req in created:
        db.refresh(req)
    return created


@router.post("/demo-shared-batch", response_model=List[RideRequestResponse], status_code=status.HTTP_201_CREATED)
def create_demo_shared_batch(
    batch_in: DemoSharedBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create up to three presentation riders joining one shared-auto route."""
    created = []
    for item in batch_in.riders:
        if not all(
            is_india_location(lat, lng)
            for lat, lng in (
                (item.pickup_lat, item.pickup_lng),
                (item.dest_lat, item.dest_lng),
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="All shared-demo pickup and destination points must be within the supported India service area",
            )
        h3_idx = get_h3_index(item.pickup_lat, item.pickup_lng, resolution=9)
        req = RideRequest(
            user_id=current_user.id,
            pickup_lat=item.pickup_lat,
            pickup_lng=item.pickup_lng,
            dest_lat=item.dest_lat,
            dest_lng=item.dest_lng,
            status="pending",
            mode=PRESENTATION_DEMO_MODE,
            demo_run_id=batch_in.demo_run_id,
            h3_index=h3_idx,
            pickup_label=item.pickup_label,
            destination_label=item.destination_label,
            ride_option_id=item.ride_option_id or "swift-x",
            ride_option_name=item.ride_option_name or "SwiftX",
            ride_option_price=item.ride_option_price or "₹12–15",
        )
        db.add(req)
        db.flush()
        create_notification(
            db,
            user_id=current_user.id,
            notification_type="ride_requested",
            title="Shared ride request created",
            message=f"Shared-demo ride #{req.id} ({item.pickup_label or 'virtual-stop pickup'}) is pending route matching.",
            related_entity_type="ride_request",
            related_entity_id=req.id,
            metadata={"status": req.status, "h3_index": h3_idx, "demo_run_id": batch_in.demo_run_id},
        )
        created.append(req)
    db.commit()
    for req in created:
        db.refresh(req)
    return created


@router.delete("/demo-runs/{demo_run_id}", status_code=status.HTTP_200_OK)
def reset_demo_run(
    demo_run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove one presentation run and release any vehicle it temporarily used."""
    owned_demo_rides = db.query(RideRequest).filter(
        RideRequest.mode == PRESENTATION_DEMO_MODE,
        RideRequest.demo_run_id == demo_run_id,
        RideRequest.user_id == current_user.id,
    ).all()
    if current_user.role != "admin" and not owned_demo_rides:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only reset your own presentation demo runs",
        )

    demo_rides = owned_demo_rides if current_user.role != "admin" else apply_ride_scope(
        db.query(RideRequest), PRESENTATION_DEMO_MODE, demo_run_id
    ).all()
    if not demo_rides:
        return {"deleted_rides": 0, "demo_run_id": demo_run_id}

    ride_ids = [ride.id for ride in demo_rides]
    stop_ids = {ride.virtual_stop_id for ride in demo_rides if ride.virtual_stop_id}
    route_plans = db.query(RoutePlan).filter(
        RoutePlan.mode == PRESENTATION_DEMO_MODE,
        RoutePlan.demo_run_id == demo_run_id,
    ).all()
    route_plan_ids = [route.id for route in route_plans]

    for route_plan in route_plans:
        vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
        if vehicle and vehicle.assigned_route_id == route_plan.route_id:
            vehicle.assigned_route_id = None
            vehicle.status = "idle"

    if route_plan_ids:
        db.query(TrackingEvent).filter(TrackingEvent.route_plan_id.in_(route_plan_ids)).delete(
            synchronize_session=False
        )
        db.query(RouteWaypointRecord).filter(
            RouteWaypointRecord.route_plan_id.in_(route_plan_ids)
        ).delete(synchronize_session=False)
        db.query(RoutePlan).filter(RoutePlan.id.in_(route_plan_ids)).delete(
            synchronize_session=False
        )

    db.query(Notification).filter(
        Notification.related_entity_type == "ride_request",
        Notification.related_entity_id.in_(ride_ids),
    ).delete(synchronize_session=False)
    if route_plan_ids:
        db.query(Notification).filter(
            Notification.related_entity_type == "route_plan",
            Notification.related_entity_id.in_(route_plan_ids),
        ).delete(synchronize_session=False)

    if stop_ids:
        db.query(RideRequest).filter(RideRequest.virtual_stop_id.in_(stop_ids)).update(
            {RideRequest.virtual_stop_id: None}, synchronize_session=False
        )
        db.query(RideRequest).filter(RideRequest.id.in_(ride_ids)).delete(
            synchronize_session=False
        )
        db.query(VirtualStop).filter(
            VirtualStop.mode == PRESENTATION_DEMO_MODE,
            VirtualStop.demo_run_id == demo_run_id,
            VirtualStop.id.in_(stop_ids),
        ).delete(
            synchronize_session=False
        )
    else:
        db.query(RideRequest).filter(RideRequest.id.in_(ride_ids)).delete(
            synchronize_session=False
        )

    db.query(ClusterRun).filter(
        ClusterRun.mode == PRESENTATION_DEMO_MODE,
        ClusterRun.demo_run_id == demo_run_id,
    ).delete(synchronize_session=False)
    db.commit()
    return {"deleted_rides": len(ride_ids), "demo_run_id": demo_run_id}


@router.get("/my-rides", response_model=List[RideRequestResponse])
def get_my_ride_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all ride requests created by the current authenticated user"""
    rides = (
        db.query(RideRequest)
        .filter(RideRequest.user_id == current_user.id, RideRequest.mode == LIVE_MODE)
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
    mode: str = Query(LIVE_MODE, description="live | presentation_demo"),
    demo_run_id: Optional[str] = Query(None, min_length=1, max_length=64),
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
    try:
        mode = validate_ride_mode(mode)
        query = apply_ride_scope(db.query(RideRequest), mode, demo_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
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
