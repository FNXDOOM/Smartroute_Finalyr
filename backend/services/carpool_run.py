"""Shared ownership of a carpool run's roster and its single closing path.

A run can be reached from several endpoints (the driver's carpool routes in
``routers/route.py`` and the generic ride-status PATCH in ``routers/rides.py``),
so the mechanics of "every rider is off, wind the run down" live here once.
"""

from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session

from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.vehicle import Vehicle
from services.notifications import create_notifications_for_users
from utils.carpool_status import CARPOOL_COMPLETED, set_carpool_stage

# A co-passenger cancellation leaves the plan in ``needs_reoptimization`` while
# the rest of its riders are still being served, so the driver's own endpoints
# must keep working on it; only ``completed`` ends the run.
CARPOOL_LIVE_ROUTE_STATUSES = ("solved", "needs_reoptimization")
CARPOOL_CLOSABLE_ROUTE_STATUSES = (*CARPOOL_LIVE_ROUTE_STATUSES, "completed")


def route_rides(db: Session, route_plan: RoutePlan) -> List[RideRequest]:
    """Every non-cancelled passenger ride served by a carpool route.

    Cancelled riders are excluded because a stale ``passenger_ids`` entry must
    never be advanced, notified, or counted as outstanding work.
    """
    ride_ids = {
        passenger_id
        for waypoint in route_plan.waypoints or []
        for passenger_id in (waypoint.passenger_ids or [])
    }
    if not ride_ids:
        return []
    return (
        db.query(RideRequest)
        .filter(
            RideRequest.id.in_(ride_ids),
            RideRequest.status != "cancelled",
        )
        .order_by(RideRequest.id.asc())
        .all()
    )


def riders_not_dropped_off(rides: List[RideRequest]) -> List[RideRequest]:
    """Riders still owed a drop-off, i.e. anything blocking completion.

    Takes the output of :func:`route_rides`, so cancelled riders are already out.
    """
    return [ride for ride in rides if ride.status != "completed"]


def is_carpool_run(route_plan: RoutePlan) -> bool:
    return bool((route_plan.route_metadata or {}).get("carpool_run"))


def close_carpool_run(db: Session, route_plan: RoutePlan, rides: List[RideRequest]) -> None:
    """Complete the run, its riders and the vehicle serving it.

    ``rides`` is the roster the caller already established as fully dropped off,
    so this does not re-read it.
    """
    metadata = dict(route_plan.route_metadata or {})
    metadata["carpool_run_status"] = "completed"
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    route_plan.route_metadata = metadata
    route_plan.status = "completed"

    for ride in rides:
        if ride.status == "completed":
            set_carpool_stage(ride, CARPOOL_COMPLETED)

    vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
    if vehicle and vehicle.assigned_route_id == route_plan.route_id:
        vehicle.status = "idle"
        vehicle.assigned_route_id = None

    passenger_user_ids = {ride.user_id for ride in rides}
    if passenger_user_ids:
        create_notifications_for_users(
            db,
            user_ids=passenger_user_ids,
            notification_type="carpool_route_completed",
            title="Carpool ride completed",
            message="All passengers have been dropped off. Your carpool ride is complete.",
            related_entity_type="route_plan",
            related_entity_id=route_plan.id,
            metadata={"route_id": route_plan.route_id},
        )
