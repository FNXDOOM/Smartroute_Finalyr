"""Carpool run lifecycle: one owner for live-run statuses, the rider stage ladder, the roster, and completion."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional, Sequence

from sqlalchemy.orm import Session

from models.ride_request import RideRequest
from models.route_plan import RoutePlan
from models.route_waypoint import RouteWaypointRecord
from models.user import User
from models.vehicle import Vehicle
from models.virtual_stop import VirtualStop
from services import route_plan_meta
from services.notifications import create_notification, create_notifications_for_users
from utils.ride_states import (
    LIVE_ROUTE_STATUSES,
    RIDE_BOUND_STATUSES,
    RIDE_ASSIGNED,
    RIDE_CANCELLED,
    RIDE_CLUSTERED,
    RIDE_COMPLETED,
    ROUTE_CANCELLED,
    ROUTE_COMPLETED,
    ROUTE_NEEDS_REOPTIMIZATION,
    VEHICLE_ACTIVE,
    VEHICLE_IDLE,
)
from utils.carpool_status import (
    CARPOOL_ASSIGNED,
    CARPOOL_BOARDED,
    CARPOOL_CANCELLED,
    CARPOOL_CLUSTERED,
    CARPOOL_COMPLETED,
    CARPOOL_DRIVER_ACCEPTED,
    CARPOOL_DRIVER_ARRIVING,
    CARPOOL_DROPPED_OFF,
    CARPOOL_IN_TRANSIT,
    CARPOOL_PASSENGER_CONFIRMED,
    CARPOOL_PICKUP_READY,
    RIDE_STATUS_TO_CARPOOL,
    set_carpool_stage,
    stage_at_least,
)
from utils.ride_scope import LIVE_MODE

# Single source for refusal code -> HTTP status; routers read ``status_code`` below instead of re-declaring it.
HTTP_STATUS_FOR_CODE = {"not_found": 404, "forbidden": 403, "conflict": 409, "invalid": 400}


class CarpoolRefused(Exception):
    """A lifecycle intent was refused. ``code`` is domain-level, not HTTP."""

    def __init__(self, code: str, detail: str, *, ride_id: Optional[int] = None) -> None:
        self.code = code
        self.detail = detail
        self.ride_id = ride_id
        super().__init__(detail)

    @property
    def status_code(self) -> int:
        return HTTP_STATUS_FOR_CODE[self.code]


@dataclass(frozen=True)
class _Hop:
    """One legal per-rider move: to ``target``, never from before ``source``."""

    target: str
    source: str
    detail: str


_RIDER_HOPS = {
    "announce": _Hop(CARPOOL_DRIVER_ARRIVING, CARPOOL_ASSIGNED, "Passenger is not awaiting pickup"),
    "arrive": _Hop(CARPOOL_PICKUP_READY, CARPOOL_DRIVER_ARRIVING, "Passenger is not being picked up right now"),
    "ready": _Hop(CARPOOL_PASSENGER_CONFIRMED, CARPOOL_DRIVER_ARRIVING, "This ride is not waiting at a carpool pickup stop"),
    "board": _Hop(CARPOOL_BOARDED, CARPOOL_PASSENGER_CONFIRMED, "Passenger has not confirmed arrival"),
    "dropoff": _Hop(CARPOOL_DROPPED_OFF, CARPOOL_BOARDED, "Passenger is not onboard"),
}


# -- roster ------------------------------------------------------------------

def route_rides(db: Session, route_plan: RoutePlan) -> List[RideRequest]:
    """Non-cancelled rides on the route; a stale cancelled id must never be advanced or counted."""
    ride_ids = {
        passenger_id
        for waypoint in route_plan.waypoints or []
        for passenger_id in (waypoint.passenger_ids or [])
    }
    if not ride_ids:
        return []
    return (
        db.query(RideRequest)
        .filter(RideRequest.id.in_(ride_ids), RideRequest.status != RIDE_CANCELLED)
        .order_by(RideRequest.id.asc())
        .all()
    )


def riders_not_dropped_off(rides: List[RideRequest]) -> List[RideRequest]:
    """Riders still owed a drop-off; takes route_rides output, so cancelled riders are already out."""
    return [ride for ride in rides if ride.status != RIDE_COMPLETED]


def pickup_waypoint_serving_ride(db: Session, ride: RideRequest) -> Optional[RouteWaypointRecord]:
    """The rider's pickup on the vehicle's current reservation, not a historical plan."""
    if not ride.virtual_stop_id:
        return None
    candidates = (
        db.query(RouteWaypointRecord)
        .join(RoutePlan)
        .join(Vehicle, Vehicle.id == RoutePlan.vehicle_id)
        .filter(
            RouteWaypointRecord.stop_id == ride.virtual_stop_id,
            RouteWaypointRecord.waypoint_type == "pickup",
            RoutePlan.status.in_(LIVE_ROUTE_STATUSES),
            RoutePlan.mode == ride.mode,
            Vehicle.assigned_route_id == RoutePlan.route_id,
        )
        .all()
    )
    return next(
        (waypoint for waypoint in candidates if ride.id in (waypoint.passenger_ids or [])),
        None,
    )


def route_plan_serving_ride(db: Session, ride: RideRequest) -> Optional[RoutePlan]:
    match = pickup_waypoint_serving_ride(db, ride)
    return db.get(RoutePlan, match.route_plan_id) if match else None


def run_is_open_to_riders(route_plan: RoutePlan) -> bool:
    """New riders join only before driver acceptance; after that the itinerary is fixed, not silently rewritten."""
    if route_plan_meta.is_driver_accepted(route_plan):
        return False
    return route_plan_meta.run_status(route_plan) not in {route_plan_meta.ACCEPTED, route_plan_meta.COMPLETED}


# -- completion --------------------------------------------------------------

def close_carpool_run(
    db: Session,
    route_plan: RoutePlan,
    rides: List[RideRequest],
    *,
    notify: bool = True,
) -> None:
    """Close run, riders, vehicle. rides must already be fully dropped off; notify=False keeps read paths side-effect free."""
    route_plan_meta.mark_run_completed(route_plan, datetime.now(timezone.utc).isoformat())
    route_plan.status = ROUTE_COMPLETED

    for ride in rides:
        if ride.status == RIDE_COMPLETED:
            set_carpool_stage(ride, CARPOOL_COMPLETED)

    vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
    if vehicle and vehicle.assigned_route_id == route_plan.route_id:
        vehicle.status = VEHICLE_IDLE
        vehicle.assigned_route_id = None

    passenger_user_ids = {ride.user_id for ride in rides}
    if notify and passenger_user_ids:
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


def settle_carpool_run(db: Session, route_plan: RoutePlan, *, notify: bool = True) -> bool:
    """Close a fully dropped-off run, if it is time. Idempotent, so listing endpoints may call it."""
    if not route_plan_meta.is_carpool(route_plan) or route_plan.status == ROUTE_COMPLETED:
        return False
    rides = route_rides(db, route_plan)
    if not rides or riders_not_dropped_off(rides):
        return False
    close_carpool_run(db, route_plan, rides, notify=notify)
    return True


def reconcile_reoptimization_run(db: Session, route_plan: RoutePlan) -> bool:
    """Repair old cancellation state without releasing an occupied vehicle.

    Older cancellations demoted accepted, not-yet-boarded riders to clustered.
    Restore only that legacy state; readiness/onboard progress is never rewound.
    The caller owns flush/commit. Historical/non-owning plans are never repaired.
    """
    if route_plan.status != ROUTE_NEEDS_REOPTIMIZATION:
        return False
    vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
    if not vehicle or vehicle.assigned_route_id != route_plan.route_id:
        return False
    rides = route_rides(db, route_plan)
    if not rides:
        route_plan.status = ROUTE_CANCELLED
        vehicle.assigned_route_id = None
        vehicle.status = VEHICLE_IDLE
        return True
    if not riders_not_dropped_off(rides):
        close_carpool_run(db, route_plan, rides, notify=False)
        return True
    if not route_plan_meta.is_driver_accepted(route_plan):
        return False
    changed = False
    for ride in rides:
        if ride.status == RIDE_CLUSTERED:
            if ride.is_shared:
                stage = ride.carpool_status
                set_carpool_stage(
                    ride, stage if stage_at_least(stage, CARPOOL_DRIVER_ACCEPTED) else CARPOOL_DRIVER_ACCEPTED
                )
            else:
                ride.status = RIDE_ASSIGNED
            changed = True
    return changed


# -- membership --------------------------------------------------------------

def detach_ride(db: Session, ride: RideRequest) -> None:
    """Remove a rider, preserving accepted co-passengers' lifecycle progress."""
    if not ride.virtual_stop_id:
        ride.cluster_id = None
        return

    stop = db.query(VirtualStop).filter(VirtualStop.id == ride.virtual_stop_id).first()
    pickup_waypoints = db.query(RouteWaypointRecord).filter(
        RouteWaypointRecord.stop_id == ride.virtual_stop_id,
    ).all()
    route_plans = {}
    for pickup_waypoint in pickup_waypoints:
        route_plan = db.query(RoutePlan).filter(RoutePlan.id == pickup_waypoint.route_plan_id).first()
        if not route_plan or route_plan.status not in LIVE_ROUTE_STATUSES:
            continue
        route_plans[route_plan.id] = route_plan
        for waypoint in route_plan.waypoints or []:
            waypoint.passenger_ids = [
                passenger_id
                for passenger_id in (waypoint.passenger_ids or [])
                if passenger_id != ride.id
            ]

    ride.virtual_stop_id = None
    ride.cluster_id = None
    if stop:
        stop.passenger_count = max(0, int(stop.passenger_count or 0) - 1)

    for route_plan in route_plans.values():
        remaining = [
            passenger_id
            for waypoint in route_plan.waypoints or []
            for passenger_id in (waypoint.passenger_ids or [])
        ]
        route_plan_meta.record_detach(
            route_plan,
            remaining=bool(remaining),
            dropoff_request_ids=[
                passenger_id
                for passenger_id in route_plan_meta.assigned_dropoff_request_ids(route_plan)
                if passenger_id != ride.id
            ],
        )
        if remaining:
            route_plan.status = ROUTE_NEEDS_REOPTIMIZATION
            if not route_plan_meta.is_driver_accepted(route_plan):
                db.query(RideRequest).filter(
                    RideRequest.id.in_(set(remaining)),
                    RideRequest.status.in_(RIDE_BOUND_STATUSES),
                ).update(
                    {
                        RideRequest.status: RIDE_CLUSTERED,
                        RideRequest.carpool_status: CARPOOL_CLUSTERED,
                    },
                    synchronize_session=False,
                )
        else:
            route_plan.status = ROUTE_CANCELLED
            vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
            if vehicle and vehicle.assigned_route_id == route_plan.route_id:
                vehicle.status = VEHICLE_IDLE
                vehicle.assigned_route_id = None


def cancel_ride(db: Session, ride: RideRequest) -> None:
    """Detach a rider from its run and mark it cancelled."""
    detach_ride(db, ride)
    if getattr(ride, "is_shared", False):
        set_carpool_stage(ride, CARPOOL_CANCELLED)
    else:
        ride.status = RIDE_CANCELLED


# -- the run -----------------------------------------------------------------

def _stage_of(ride: RideRequest) -> Optional[str]:
    """The fine stage, derived from the coarse status for pre-ladder rows."""
    if ride.carpool_status:
        return ride.carpool_status
    return RIDE_STATUS_TO_CARPOOL.get(ride.status)


class CarpoolRun:
    """One live carpool run and the intents its driver may apply to it."""

    def __init__(self, db: Session, route_plan: RoutePlan, actor: User) -> None:
        self._db = db
        self._actor = actor
        self.route_plan = route_plan

    @classmethod
    def _load(
        cls,
        db: Session,
        route_id: str,
        actor: User,
        *,
        statuses: Sequence[str],
        require_accepted: bool,
        require_carpool: bool = True,
    ) -> "CarpoolRun":
        if actor is None or actor.role not in {"admin", "driver"}:
            raise CarpoolRefused("forbidden", "Driver access required")
        route_plan = db.query(RoutePlan).filter(
            RoutePlan.route_id == route_id,
            RoutePlan.mode == LIVE_MODE,
            RoutePlan.status.in_(statuses),
        ).first()
        if not route_plan or (require_carpool and not route_plan_meta.is_carpool(route_plan)):
            raise CarpoolRefused("not_found", "Carpool route not found")
        vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
        if not vehicle or (actor.role == "driver" and vehicle.driver_user_id != actor.id):
            raise CarpoolRefused("not_found", "Carpool route not found")
        if route_plan.status in LIVE_ROUTE_STATUSES and vehicle.assigned_route_id != route_plan.route_id:
            raise CarpoolRefused("conflict", "This route is no longer assigned to its vehicle")
        if require_accepted and not route_plan_meta.is_driver_accepted(route_plan):
            raise CarpoolRefused("conflict", "Accept the carpool run first")
        return cls(db, route_plan, actor)

    @classmethod
    def open(
        cls,
        db: Session,
        route_id: str,
        actor: User,
        *,
        statuses: Sequence[str] = LIVE_ROUTE_STATUSES,
    ) -> "CarpoolRun":
        """Resolve a run the actor may drive; it must already be accepted."""
        return cls._load(db, route_id, actor, statuses=statuses, require_accepted=True)

    @classmethod
    def for_ride(cls, db: Session, ride: RideRequest, actor: User) -> "CarpoolRun":
        """Resolve the live run serving a rider (passenger entry point)."""
        route_plan = route_plan_serving_ride(db, ride)
        if not route_plan or not route_plan_meta.is_carpool(route_plan):
            raise CarpoolRefused(
                "not_found", "This ride is not waiting at a carpool pickup stop", ride_id=ride.id
            )
        return cls(db, route_plan, actor)

    @classmethod
    def accept(cls, db: Session, route_id: str, actor: User) -> RoutePlan:
        """Accept a run so riders start progressing. Retry-safe: riders at or past driver_accepted are neither moved nor re-notified."""
        run = cls._load(
            db,
            route_id,
            actor,
            statuses=LIVE_ROUTE_STATUSES,
            require_accepted=False,
            require_carpool=False,
        )
        route_plan = run.route_plan
        route_plan_meta.mark_driver_accepted(route_plan, datetime.now(timezone.utc).isoformat())

        vehicle = db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
        if vehicle:
            vehicle.status = VEHICLE_ACTIVE

        if route_plan_meta.is_carpool(route_plan):
            advancing = [
                rider
                for rider in route_rides(db, route_plan)
                if not stage_at_least(_stage_of(rider), CARPOOL_DRIVER_ACCEPTED)
            ]
            for rider in advancing:
                set_carpool_stage(rider, CARPOOL_DRIVER_ACCEPTED)
            if advancing:
                create_notifications_for_users(
                    db,
                    user_ids={rider.user_id for rider in advancing},
                    notification_type="carpool_driver_accepted",
                    title="Driver accepted your carpool run",
                    message="Your driver has accepted the run. Be ready at your pickup stop when they arrive.",
                    related_entity_type="route_plan",
                    related_entity_id=route_plan.id,
                    metadata={"route_id": route_plan.route_id},
                )
        return route_plan

    def roster(self) -> List[RideRequest]:
        return route_rides(self._db, self.route_plan)

    def _rider(self, ride_id: int) -> RideRequest:
        ride = self._db.query(RideRequest).filter(
            RideRequest.id == ride_id, RideRequest.is_shared.is_(True)
        ).first()
        if not ride:
            raise CarpoolRefused("not_found", "Carpool passenger not found", ride_id=ride_id)
        if not any(ride.id in (waypoint.passenger_ids or []) for waypoint in self.route_plan.waypoints):
            raise CarpoolRefused("not_found", "Passenger is not on this route", ride_id=ride_id)
        if ride.status == RIDE_CANCELLED:
            raise CarpoolRefused("invalid", "This rider cancelled their carpool request", ride_id=ride_id)
        return ride

    def _hop(self, name: str, ride: RideRequest, emit: Callable[[RideRequest], None]) -> RideRequest:
        """Apply one monotonic hop, or refuse it. Never moves a rider backwards."""
        hop = _RIDER_HOPS[name]
        current = _stage_of(ride)
        if stage_at_least(current, hop.target):
            return ride  # already there: a retry, not a rewind
        if not stage_at_least(current, hop.source):
            raise CarpoolRefused("conflict", hop.detail, ride_id=ride.id)
        set_carpool_stage(ride, hop.target)
        emit(ride)
        return ride

    def announce(self, ride_id: int) -> RideRequest:
        """Tell one passenger to walk to their pickup stop."""
        ride = self._rider(ride_id)
        route_plan = self.route_plan

        def emit(ride: RideRequest) -> None:
            pickup = next(
                (
                    waypoint for waypoint in route_plan.waypoints
                    if waypoint.waypoint_type == "pickup" and ride.id in (waypoint.passenger_ids or [])
                ),
                None,
            )
            create_notification(
                self._db,
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

        return self._hop("announce", ride, emit)

    def mark_arrived(self, ride_id: int) -> RideRequest:
        """Record that the driver reached one rider's pickup stop."""
        ride = self._rider(ride_id)
        route_plan = self.route_plan

        def emit(ride: RideRequest) -> None:
            create_notification(
                self._db,
                user_id=ride.user_id,
                notification_type="carpool_driver_arrived",
                title="Your driver has arrived",
                message="Your driver is at the pickup stop. Confirm when you are ready to board.",
                related_entity_type="ride_request",
                related_entity_id=ride.id,
                metadata={"route_id": route_plan.route_id},
            )

        return self._hop("arrive", ride, emit)

    def passenger_ready(self, ride_id: int) -> RideRequest:
        """The passenger confirms they reached the assigned pickup stop."""
        ride = self._rider(ride_id)
        if ride.user_id != self._actor.id and self._actor.role != "admin":
            raise CarpoolRefused("forbidden", "Not authorized to update this ride", ride_id=ride.id)
        route_plan = self.route_plan

        def emit(ride: RideRequest) -> None:
            vehicle = self._db.query(Vehicle).filter(Vehicle.id == route_plan.vehicle_id).first()
            if vehicle and vehicle.driver_user_id:
                create_notification(
                    self._db,
                    user_id=vehicle.driver_user_id,
                    notification_type="carpool_passenger_ready",
                    title="Passenger is ready at the pickup stop",
                    message=f"Passenger for ride #{ride.id} has arrived at the assigned carpool pickup stop.",
                    related_entity_type="ride_request",
                    related_entity_id=ride.id,
                    metadata={"route_id": route_plan.route_id, "ride_id": ride.id},
                )

        return self._hop("ready", ride, emit)

    def confirm_pickup(self, ride_id: int) -> RideRequest:
        """Confirm that a ready passenger boarded at the assigned stop."""
        ride = self._rider(ride_id)
        route_plan = self.route_plan

        def emit(ride: RideRequest) -> None:
            create_notification(
                self._db,
                user_id=ride.user_id,
                notification_type="carpool_pickup_confirmed",
                title="You are onboard",
                message="Your driver confirmed pickup. You are now travelling to your destination.",
                related_entity_type="ride_request",
                related_entity_id=ride.id,
                metadata={"route_id": route_plan.route_id},
            )
            other_user_ids = {other.user_id for other in self.roster() if other.id != ride.id}
            if other_user_ids:
                create_notifications_for_users(
                    self._db,
                    user_ids=other_user_ids,
                    notification_type="carpool_co_passenger_boarded",
                    title="A co-passenger boarded",
                    message="Another rider boarded the carpool at their pickup stop.",
                    related_entity_type="route_plan",
                    related_entity_id=route_plan.id,
                    metadata={"route_id": route_plan.route_id, "ride_id": ride.id},
                )

        return self._hop("board", ride, emit)

    def confirm_dropoff(self, ride_id: int) -> RideRequest:
        """Record one passenger's drop-off; the driver still closes the run explicitly."""
        ride = self._rider(ride_id)
        route_plan = self.route_plan

        def emit(ride: RideRequest) -> None:
            create_notification(
                self._db,
                user_id=ride.user_id,
                notification_type="carpool_dropoff_confirmed",
                title="You reached your destination",
                message="Your driver confirmed that you were dropped off. Your carpool ride is complete.",
                related_entity_type="ride_request",
                related_entity_id=ride.id,
                metadata={"route_id": route_plan.route_id},
            )

        return self._hop("dropoff", ride, emit)

    def depart(self) -> List[RideRequest]:
        """Start the trip: every boarded rider moves to IN_TRANSIT."""
        boarded = [ride for ride in self.roster() if _stage_of(ride) == CARPOOL_BOARDED]
        if not boarded:
            raise CarpoolRefused("conflict", "No passenger has boarded at a pickup stop yet")
        route_plan = self.route_plan
        for ride in boarded:
            set_carpool_stage(ride, CARPOOL_IN_TRANSIT)
            create_notification(
                self._db,
                user_id=ride.user_id,
                notification_type="carpool_ride_started",
                title="Your ride has started",
                message="The car is on the move towards your destination.",
                related_entity_type="ride_request",
                related_entity_id=ride.id,
                metadata={"route_id": route_plan.route_id},
            )
        return boarded

    def complete(self) -> bool:
        """Close the run and release its vehicle. Returns True if it closed now."""
        rides = self.roster()
        if not rides:
            raise CarpoolRefused("conflict", "This carpool run has no riders")
        outstanding = riders_not_dropped_off(rides)
        if outstanding:
            raise CarpoolRefused(
                "conflict",
                "Ride(s) "
                + ", ".join(str(ride.id) for ride in outstanding)
                + " still need to be dropped off before the run can be completed",
            )
        # Atomic claim via the conditional UPDATE, not a status check: two racers that both read "not completed" would each notify every rider.
        claimed = self._db.query(RoutePlan).filter(
            RoutePlan.id == self.route_plan.id,
            RoutePlan.status != ROUTE_COMPLETED,
        ).update({RoutePlan.status: ROUTE_COMPLETED}, synchronize_session=False)
        if not claimed:
            return False
        close_carpool_run(self._db, self.route_plan, rides)
        return True
