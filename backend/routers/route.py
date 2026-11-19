from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models.cluster_run import ClusterRun
from models.job_run import JobRun
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
    VRPRequest,
)
from services.routing.shared_route_builder import (
    build_shared_routes,
    persist_shared_route,
    resolve_route_geometry,
)
from services import route_plan_meta
from services.carpool_lifecycle import (
    CarpoolRefused,
    CarpoolRun,
    settle_carpool_run,
)
from services.notifications import create_notification, create_notifications_for_users
from utils.auth_utils import ensure_active_driver, get_current_user
from utils.carpool_status import CARPOOL_IN_TRANSIT
from utils.ride_scope import LIVE_MODE
from utils.ride_states import CLOSABLE_ROUTE_STATUSES, RIDE_COMPLETED, RIDE_IN_PROGRESS, ROUTE_SOLVED

router = APIRouter()


def _carpool_http(refused: CarpoolRefused) -> HTTPException:
    """Map a carpool refusal to the HTTP status the endpoint used to raise."""
    return HTTPException(status_code=refused.status_code, detail=refused.detail)


def _rider_ack(route_id: str, ride: RideRequest) -> dict:
    """The per-rider response shape the carpool endpoints share."""
    return {
        "status": ride.status,
        "carpool_status": ride.carpool_status,
        "ride_id": ride.id,
        "route_id": route_id,
    }


def _authorize_optimizer(current_user: User) -> None:
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can optimize routes",
        )
    ensure_active_driver(current_user)


@router.post("/optimize", response_model=OptimizedRouteResponse)
def optimize_routes(
    payload: VRPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build and persist optimized routes for eligible clusters."""
    return run_route_optimization(db, payload, current_user)


def _validate_optimize_inputs(db: Session, payload: VRPRequest, current_user: User):
    """Validate ownership/existence once for both the sync and queued paths."""
    _authorize_optimizer(current_user)
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
        return vehicles, None
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
    return vehicles, virtual_stops


def run_route_optimization(
    db: Session, payload: VRPRequest, current_user: User
) -> OptimizedRouteResponse:
    """Shared solve path for the sync endpoint and the worker."""
    vehicles, virtual_stops = _validate_optimize_inputs(db, payload, current_user)
    if virtual_stops is None:
        return OptimizedRouteResponse(status="no_virtual_stops", routes=[], unassigned_stops=[])

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
                    "carpool_run": route_plan_meta.is_carpool(persisted.route_plan),
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
        status=ROUTE_SOLVED,
        routes=route_solutions,
        unassigned_stops=unassigned_stops,
    )


@router.post("/optimize/async", status_code=status.HTTP_202_ACCEPTED)
def optimize_routes_async(
    payload: VRPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue the same solve for the worker and return immediately."""
    _validate_optimize_inputs(db, payload, current_user)
    job = JobRun(
        job_name="optimize_route",
        status="queued",
        triggered_by_user_id=current_user.id,
        is_scheduled=False,
        summary={"request": payload.model_dump(mode="json")},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.id, "status": "queued"}


@router.get("/optimize/jobs/{job_id}")
def get_optimize_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a queued/solved optimize job; only its owner or an admin."""
    job = (
        db.query(JobRun)
        .filter(JobRun.id == job_id, JobRun.job_name == "optimize_route")
        .first()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.triggered_by_user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this job",
        )
    summary = job.summary or {}
    return {
        "job_id": job.id,
        "status": job.status,
        "result": summary.get("result"),
        "error_message": job.error_message,
    }


def _route_plan_response(route_plan: RoutePlan) -> RoutePlanResponse:
    """Route plan with its geometry, legs and problem promoted out of metadata."""
    response = RoutePlanResponse.model_validate(route_plan)
    return response.model_copy(update={
        "geometry": route_plan_meta.geometry(route_plan),
        "legs": [RouteLeg(**leg) for leg in route_plan_meta.legs(route_plan)],
        "problem": route_plan_meta.problem(route_plan),
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
        RoutePlan.status == ROUTE_SOLVED,
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
    # Repair older carpool routes that completed every ride but never stored the route-level completed state.
    completed_route_ids = []
    for route in routes:
        if settle_carpool_run(db, route, notify=False):
            completed_route_ids.append(route.route_id)
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

    # Plans from the automatic dispatch job carry no road geometry, so a driver opening the map fetches it once and caches it on the plan.
    resolve_route_geometry(db, route_plan)

    return _route_plan_response(route_plan)


@router.post("/{route_id}/accept", response_model=RoutePlanResponse)
def accept_route(
    route_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept an assigned route so its rides may begin progressing."""
    ensure_active_driver(current_user)
    try:
        route_plan = CarpoolRun.accept(db, route_id, current_user)
    except CarpoolRefused as refused:
        raise _carpool_http(refused) from refused
    db.commit()
    db.refresh(route_plan)
    return _route_plan_response(route_plan)


@router.post("/{route_id}/carpool/announce-pickup/{ride_id}")
def announce_carpool_pickup(
    route_id: str,
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tell one carpool passenger to walk to the assigned pickup stop."""
    ensure_active_driver(current_user)
    try:
        run = CarpoolRun.open(db, route_id, current_user)
        ride = run.announce(ride_id)
    except CarpoolRefused as refused:
        raise _carpool_http(refused) from refused
    db.commit()
    return _rider_ack(route_id, ride)


@router.post("/{route_id}/carpool/confirm-pickup/{ride_id}")
def confirm_carpool_pickup(
    route_id: str,
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm that a ready passenger has boarded at the assigned stop."""
    ensure_active_driver(current_user)
    try:
        run = CarpoolRun.open(db, route_id, current_user)
        ride = run.confirm_pickup(ride_id)
    except CarpoolRefused as refused:
        raise _carpool_http(refused) from refused
    db.commit()
    return _rider_ack(route_id, ride)


@router.post("/{route_id}/carpool/confirm-dropoff/{ride_id}")
def confirm_carpool_dropoff(
    route_id: str,
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm an individual carpool passenger reached their destination."""
    ensure_active_driver(current_user)
    try:
        run = CarpoolRun.open(db, route_id, current_user)
        ride = run.confirm_dropoff(ride_id)
    except CarpoolRefused as refused:
        raise _carpool_http(refused) from refused
    db.commit()
    return _rider_ack(route_id, ride)


@router.post("/{route_id}/carpool/mark-arrived/{ride_id}")
def mark_carpool_arrived(
    route_id: str,
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver reached the pickup stop; the passenger may now board."""
    ensure_active_driver(current_user)
    try:
        run = CarpoolRun.open(db, route_id, current_user)
        ride = run.mark_arrived(ride_id)
    except CarpoolRefused as refused:
        raise _carpool_http(refused) from refused
    db.commit()
    return _rider_ack(route_id, ride)


@router.post("/{route_id}/carpool/depart")
def depart_carpool_route(
    route_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver starts driving: every boarded rider moves to IN_TRANSIT."""
    ensure_active_driver(current_user)
    try:
        run = CarpoolRun.open(db, route_id, current_user)
        boarded = run.depart()
    except CarpoolRefused as refused:
        raise _carpool_http(refused) from refused
    db.commit()
    return {
        "status": RIDE_IN_PROGRESS,
        "carpool_status": CARPOOL_IN_TRANSIT,
        "ride_ids": [ride.id for ride in boarded],
        "route_id": route_id,
    }


@router.post("/{route_id}/carpool/complete")
def complete_carpool_route(
    route_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Close a carpool run and release its vehicle; the only endpoint that ends a driver-run, since drop-offs alone never do."""
    ensure_active_driver(current_user)
    try:
        run = CarpoolRun.open(db, route_id, current_user, statuses=CLOSABLE_ROUTE_STATUSES)
        completed_now = run.complete()
    except CarpoolRefused as refused:
        raise _carpool_http(refused) from refused
    db.commit()
    response = {"status": RIDE_COMPLETED, "route_id": route_id}
    if not completed_now:
        response["already_completed"] = True
    return response
