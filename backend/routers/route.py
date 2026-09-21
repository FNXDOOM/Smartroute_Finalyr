from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models.cluster_run import ClusterRun
from models.ride_request import RideRequest
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
from services.carpool_run import (
    CARPOOL_CLOSABLE_ROUTE_STATUSES,
    CARPOOL_LIVE_ROUTE_STATUSES,
    close_carpool_run,
    is_carpool_run,
    riders_not_dropped_off,
    route_rides,
)
from services.notifications import create_notification, create_notifications_for_users
from utils.auth_utils import ensure_active_driver, get_current_user
from utils.carpool_status import (
    CARPOOL_BOARDED,
    CARPOOL_DRIVER_ACCEPTED,
    CARPOOL_DRIVER_ARRIVING,
    CARPOOL_DROPPED_OFF,
    CARPOOL_IN_TRANSIT,
    CARPOOL_PICKUP_READY,
    set_carpool_stage,
    stage_at_least,
)
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
    ensure_active_driver(current_user)

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

        if actual_vehicle.driver_user_id and actual_vehicle.driver_user_id != current_user.id:
            create_notification(
                db,
                user_id=actual_vehicle.driver_user_id,
                notification_type="route_assigned",
                title="New route assigned",
                message=(
                    f"Carpool run {persisted.route_id} is ready for your vehicle "
                    f"{actual_vehicle.license_plate}. Open Carpool Run to accept it."
                ),
                related_entity_type="route_plan",
                related_entity_id=persisted.route_plan.id,
                metadata={
                    "route_id": persisted.route_id,
                    "vehicle_id": actual_vehicle.id,
                    "carpool_run": bool((persisted.route_plan.route_metadata or {}).get("carpool_run")),
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
        "problem": str(metadata.get("problem") or "pdp"),
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

    routes_query = db.query(RoutePlan).filter(
        RoutePlan.mode == LIVE_MODE,
        RoutePlan.status == "solved",
    )
    if current_user.role == "driver":
        routes_query = routes_query.join(Vehicle, Vehicle.id == RoutePlan.vehicle_id).filter(
            Vehicle.driver_user_id == current_user.id,
        )
    routes = (
        routes_query
        .order_by(RoutePlan.created_at.desc())
        .limit(limit)
        .all()
    )
    # Repair older carpool routes that completed every ride but never stored
    # the route-level completed state.
    completed_route_ids = []
    for route in routes:
        metadata = route.route_metadata or {}
        if not metadata.get("carpool_run"):
            continue
        ride_ids = {
            passenger_id
            for waypoint in route.waypoints
            for passenger_id in (waypoint.passenger_ids or [])
        }
        if not ride_ids:
            continue
        unfinished = db.query(RideRequest).filter(
            RideRequest.id.in_(ride_ids),
            RideRequest.status.notin_(["completed", "cancelled"]),
        ).count()
        if unfinished == 0:
            route.status = "completed"
            metadata = dict(metadata)
            metadata["carpool_run_status"] = "completed"
            metadata["completed_at"] = metadata.get("completed_at") or datetime.now(timezone.utc).isoformat()
            route.route_metadata = metadata
            completed_route_ids.append(route.route_id)
            vehicle = db.query(Vehicle).filter(Vehicle.id == route.vehicle_id).first()
            if vehicle and vehicle.assigned_route_id == route.route_id:
                vehicle.assigned_route_id = None
                vehicle.status = "idle"
    if completed_route_ids:
        db.commit()
        routes = [route for route in routes if route.route_id not in completed_route_ids]
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
    if current_user.role == "driver":
        vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
        if not vehicle or vehicle.driver_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")

    # Plans written by the automatic dispatch job carry no road geometry, so a
    # driver opening the map is the first chance to fetch it (cached on the
    # plan, exactly once, for every later caller).
    resolve_route_geometry(db, route_plan)

    return _route_plan_response(route_plan)


@router.post("/{route_id}/accept", response_model=RoutePlanResponse)
def accept_route(
    route_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept an assigned route so its rides may begin progressing."""
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can accept routes",
        )
    ensure_active_driver(current_user)

    route_plan = db.query(RoutePlan).filter(
        RoutePlan.route_id == route_id,
        RoutePlan.mode == LIVE_MODE,
        RoutePlan.status == "solved",
    ).first()
    if not route_plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")

    vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
    if not vehicle or (current_user.role == "driver" and vehicle.driver_user_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")

    metadata = dict(route_plan.route_metadata or {})
    metadata["driver_accepted"] = True
    metadata["driver_accepted_at"] = datetime.now(timezone.utc).isoformat()
    run_is_carpool = is_carpool_run(route_plan)
    if run_is_carpool:
        metadata["carpool_run_status"] = "accepted"
    route_plan.route_metadata = metadata
    vehicle.status = "active"

    if run_is_carpool:
        # Riders advance to DRIVER_ACCEPTED together, and from here the route is
        # closed to new riders (the attach pass enforces this). Only riders that
        # have not passed that point move: this endpoint is reachable again on a
        # retry, and a run stays open while some riders are still being served.
        advancing = [
            passenger
            for passenger in route_rides(db, route_plan)
            if not stage_at_least(passenger.carpool_status, CARPOOL_DRIVER_ACCEPTED)
        ]
        for passenger in advancing:
            set_carpool_stage(passenger, CARPOOL_DRIVER_ACCEPTED)
        if advancing:
            create_notifications_for_users(
                db,
                user_ids={passenger.user_id for passenger in advancing},
                notification_type="carpool_driver_accepted",
                title="Driver accepted your carpool run",
                message="Your driver has accepted the run. Be ready at your pickup stop when they arrive.",
                related_entity_type="route_plan",
                related_entity_id=route_plan.id,
                metadata={"route_id": route_plan.route_id},
            )
    db.commit()
    db.refresh(route_plan)
    return _route_plan_response(route_plan)


def _get_driver_carpool_route(
    db: Session,
    route_id: str,
    current_user: User,
    statuses: tuple = CARPOOL_LIVE_ROUTE_STATUSES,
) -> RoutePlan:
    """Load a live carpool route and enforce driver ownership."""
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Driver access required")
    ensure_active_driver(current_user)
    route_plan = db.query(RoutePlan).filter(
        RoutePlan.route_id == route_id,
        RoutePlan.mode == LIVE_MODE,
        RoutePlan.status.in_(statuses),
    ).first()
    if not route_plan or not is_carpool_run(route_plan):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpool route not found")
    vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
    if not vehicle or (
        current_user.role == "driver" and vehicle.driver_user_id != current_user.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpool route not found")
    if not (route_plan.route_metadata or {}).get("driver_accepted"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Accept the carpool run first")
    return route_plan


def _get_carpool_ride_for_route(db: Session, route_plan: RoutePlan, ride_id: int) -> RideRequest:
    """Return a passenger included in the route's pickup and delivery nodes."""
    ride = db.query(RideRequest).filter(
        RideRequest.id == ride_id,
        RideRequest.is_shared.is_(True),
    ).first()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpool passenger not found")
    included = any(ride.id in (waypoint.passenger_ids or []) for waypoint in route_plan.waypoints)
    if not included:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passenger is not on this route")
    return ride


@router.post("/{route_id}/carpool/announce-pickup/{ride_id}")
def announce_carpool_pickup(
    route_id: str,
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tell one carpool passenger to walk to the assigned pickup stop."""
    route_plan = _get_driver_carpool_route(db, route_id, current_user)
    ride = _get_carpool_ride_for_route(db, route_plan, ride_id)
    if ride.status not in {"assigned", "arriving", "ready_for_pickup"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Passenger is not awaiting pickup")
    set_carpool_stage(ride, CARPOOL_DRIVER_ARRIVING)
    pickup = next(
        (
            waypoint for waypoint in route_plan.waypoints
            if waypoint.waypoint_type == "pickup" and ride.id in (waypoint.passenger_ids or [])
        ),
        None,
    )
    create_notification(
        db,
        user_id=ride.user_id,
        notification_type="carpool_pickup_requested",
        title="Walk to your carpool pickup stop",
        message="Your driver is approaching. Walk to the assigned pickup stop and confirm when you arrive.",
        related_entity_type="ride_request",
        related_entity_id=ride.id,
        metadata={
            "route_id": route_plan.route_id,
            "pickup_lat": pickup.lat if pickup else None,
            "pickup_lng": pickup.lng if pickup else None,
        },
    )
    db.commit()
    return {
        "status": ride.status,
        "carpool_status": ride.carpool_status,
        "ride_id": ride.id,
        "route_id": route_plan.route_id,
    }


@router.post("/{route_id}/carpool/confirm-pickup/{ride_id}")
def confirm_carpool_pickup(
    route_id: str,
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm that a ready passenger has boarded at the assigned stop."""
    route_plan = _get_driver_carpool_route(db, route_id, current_user)
    ride = _get_carpool_ride_for_route(db, route_plan, ride_id)
    if ride.status != "ready_for_pickup":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Passenger has not confirmed arrival")
    set_carpool_stage(ride, CARPOOL_BOARDED)
    create_notification(
        db,
        user_id=ride.user_id,
        notification_type="carpool_pickup_confirmed",
        title="You are onboard",
        message="Your driver confirmed pickup. You are now travelling to your destination.",
        related_entity_type="ride_request",
        related_entity_id=ride.id,
        metadata={"route_id": route_plan.route_id},
    )
    # The other riders on the run hear that a co-passenger boarded.
    other_user_ids = {
        other.user_id
        for other in route_rides(db, route_plan)
        if other.id != ride.id
    }
    if other_user_ids:
        create_notifications_for_users(
            db,
            user_ids=other_user_ids,
            notification_type="carpool_co_passenger_boarded",
            title="A co-passenger boarded",
            message="Another rider boarded the carpool at their pickup stop.",
            related_entity_type="route_plan",
            related_entity_id=route_plan.id,
            metadata={"route_id": route_plan.route_id, "ride_id": ride.id},
        )
    db.commit()
    return {
        "status": ride.status,
        "carpool_status": ride.carpool_status,
        "ride_id": ride.id,
        "route_id": route_plan.route_id,
    }


@router.post("/{route_id}/carpool/confirm-dropoff/{ride_id}")
def confirm_carpool_dropoff(
    route_id: str,
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm an individual carpool passenger reached their destination."""
    route_plan = _get_driver_carpool_route(db, route_id, current_user)
    ride = _get_carpool_ride_for_route(db, route_plan, ride_id)
    if ride.status != "in_progress":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Passenger is not onboard")
    set_carpool_stage(ride, CARPOOL_DROPPED_OFF)
    create_notification(
        db,
        user_id=ride.user_id,
        notification_type="carpool_dropoff_confirmed",
        title="You reached your destination",
        message="Your driver confirmed that you were dropped off. Your carpool ride is complete.",
        related_entity_type="ride_request",
        related_entity_id=ride.id,
        metadata={"route_id": route_plan.route_id},
    )
    db.commit()
    return {
        "status": ride.status,
        "carpool_status": ride.carpool_status,
        "ride_id": ride.id,
        "route_id": route_plan.route_id,
    }


@router.post("/{route_id}/carpool/mark-arrived/{ride_id}")
def mark_carpool_arrived(
    route_id: str,
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver reached the pickup stop; the passenger may now board."""
    route_plan = _get_driver_carpool_route(db, route_id, current_user)
    ride = _get_carpool_ride_for_route(db, route_plan, ride_id)
    if ride.carpool_status not in {CARPOOL_DRIVER_ARRIVING, CARPOOL_PICKUP_READY}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Passenger is not being picked up right now",
        )
    set_carpool_stage(ride, CARPOOL_PICKUP_READY)
    create_notification(
        db,
        user_id=ride.user_id,
        notification_type="carpool_driver_arrived",
        title="Your driver has arrived",
        message="Your driver is at the pickup stop. Confirm when you are ready to board.",
        related_entity_type="ride_request",
        related_entity_id=ride.id,
        metadata={"route_id": route_plan.route_id},
    )
    db.commit()
    return {
        "status": ride.status,
        "carpool_status": ride.carpool_status,
        "ride_id": ride.id,
        "route_id": route_plan.route_id,
    }


@router.post("/{route_id}/carpool/depart")
def depart_carpool_route(
    route_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver starts driving: every boarded rider moves to IN_TRANSIT."""
    route_plan = _get_driver_carpool_route(db, route_id, current_user)
    boarded = [ride for ride in route_rides(db, route_plan) if ride.carpool_status == CARPOOL_BOARDED]
    if not boarded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No passenger has boarded at a pickup stop yet",
        )
    for ride in boarded:
        set_carpool_stage(ride, CARPOOL_IN_TRANSIT)
        create_notification(
            db,
            user_id=ride.user_id,
            notification_type="carpool_ride_started",
            title="Your ride has started",
            message="The car is on the move towards your destination.",
            related_entity_type="ride_request",
            related_entity_id=ride.id,
            metadata={"route_id": route_plan.route_id},
        )
    db.commit()
    return {
        "status": "in_progress",
        "carpool_status": CARPOOL_IN_TRANSIT,
        "ride_ids": [ride.id for ride in boarded],
        "route_id": route_plan.route_id,
    }


@router.post("/{route_id}/carpool/complete")
def complete_carpool_route(
    route_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Close a carpool run and release its vehicle.

    This is the only path that closes a run reached through the driver's carpool
    endpoints: individual drop-offs record the drop-off, and the driver decides
    when the run is over.
    """
    route_plan = _get_driver_carpool_route(
        db, route_id, current_user, statuses=CARPOOL_CLOSABLE_ROUTE_STATUSES
    )
    rides = route_rides(db, route_plan)
    if not rides:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This carpool run has no riders")
    outstanding = riders_not_dropped_off(rides)
    if outstanding:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Ride(s) "
                + ", ".join(str(ride.id) for ride in outstanding)
                + " still need to be dropped off before the run can be completed"
            ),
        )
    if route_plan.status == "completed":
        return {"status": "completed", "route_id": route_plan.route_id, "already_completed": True}

    close_carpool_run(db, route_plan, rides)
    db.commit()
    return {"status": "completed", "route_id": route_plan.route_id}
