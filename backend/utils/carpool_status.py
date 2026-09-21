"""Per-rider carpool lifecycle stage.

The backend's ``RideRequest.status`` is a coarse, client-agnostic axis
(pending -> clustered -> assigned -> arriving -> ready_for_pickup ->
in_progress -> completed). Carpool needs a finer, *per-rider* stage: the driver
confirms one rider at a time, so two riders on the same route are legitimately
at different points. This module owns that finer stage and keeps the coarse
``status`` in lockstep, so every existing client that only reads ``status``
keeps working unchanged.
"""

from typing import Optional

# -- Stages (wire values) ----------------------------------------------------
CARPOOL_PENDING = "pending"
CARPOOL_SEARCHING = "searching"
CARPOOL_CLUSTERED = "clustered"
CARPOOL_ASSIGNED = "assigned"
CARPOOL_DRIVER_ACCEPTED = "driver_accepted"
CARPOOL_DRIVER_ARRIVING = "driver_arriving"
CARPOOL_PICKUP_READY = "pickup_ready"
CARPOOL_PASSENGER_CONFIRMED = "passenger_confirmed_pickup_stop"
CARPOOL_BOARDED = "boarded"
CARPOOL_IN_TRANSIT = "in_transit"
CARPOOL_DROPPED_OFF = "dropped_off"
CARPOOL_COMPLETED = "completed"
CARPOOL_CANCELLED = "cancelled"

CARPOOL_STAGES = (
    CARPOOL_PENDING,
    CARPOOL_SEARCHING,
    CARPOOL_CLUSTERED,
    CARPOOL_ASSIGNED,
    CARPOOL_DRIVER_ACCEPTED,
    CARPOOL_DRIVER_ARRIVING,
    CARPOOL_PICKUP_READY,
    CARPOOL_PASSENGER_CONFIRMED,
    CARPOOL_BOARDED,
    CARPOOL_IN_TRANSIT,
    CARPOOL_DROPPED_OFF,
    CARPOOL_COMPLETED,
    CARPOOL_CANCELLED,
)

# Fine stage -> coarse status. Every stage maps to exactly one coarse status.
CARPOOL_TO_RIDE_STATUS = {
    CARPOOL_PENDING: "pending",
    CARPOOL_SEARCHING: "pending",
    CARPOOL_CLUSTERED: "clustered",
    CARPOOL_ASSIGNED: "assigned",
    CARPOOL_DRIVER_ACCEPTED: "assigned",
    CARPOOL_DRIVER_ARRIVING: "arriving",
    CARPOOL_PICKUP_READY: "arriving",
    CARPOOL_PASSENGER_CONFIRMED: "ready_for_pickup",
    CARPOOL_BOARDED: "in_progress",
    CARPOOL_IN_TRANSIT: "in_progress",
    CARPOOL_DROPPED_OFF: "completed",
    CARPOOL_COMPLETED: "completed",
    CARPOOL_CANCELLED: "cancelled",
}

# Coarse status -> the stage a manual status write implies. Keeps a legacy
# PATCH /rides/{id}/status from desyncing the two axes.
RIDE_STATUS_TO_CARPOOL = {
    "pending": CARPOOL_PENDING,
    "clustered": CARPOOL_CLUSTERED,
    "assigned": CARPOOL_ASSIGNED,
    "arriving": CARPOOL_DRIVER_ARRIVING,
    "ready_for_pickup": CARPOOL_PASSENGER_CONFIRMED,
    "in_progress": CARPOOL_BOARDED,
    "completed": CARPOOL_COMPLETED,
    "cancelled": CARPOOL_CANCELLED,
}


def set_carpool_stage(ride, stage: str) -> None:
    """Advance a shared ride to ``stage`` and keep its coarse status in sync.

    A no-op for private rides: they are never tracked on the carpool axis and
    keep ``carpool_status`` null.
    """
    if not getattr(ride, "is_shared", False):
        return
    if stage not in CARPOOL_TO_RIDE_STATUS:
        raise ValueError(f"Unknown carpool stage: {stage}")
    ride.carpool_status = stage
    ride.status = CARPOOL_TO_RIDE_STATUS[stage]


def sync_carpool_from_status(ride) -> None:
    """Derive the carpool stage from a coarse status (legacy PATCH path)."""
    if not getattr(ride, "is_shared", False):
        return
    stage = RIDE_STATUS_TO_CARPOOL.get(ride.status)
    if stage is not None:
        ride.carpool_status = stage


def normalize_carpool_status(value: Optional[str]) -> Optional[str]:
    """Echo a known stage, else None (defensive for older/corrupt rows)."""
    if value in CARPOOL_TO_RIDE_STATUS:
        return value
    return None
