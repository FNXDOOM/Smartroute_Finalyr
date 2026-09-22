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

from utils.ride_states import (
    RIDE_ARRIVING,
    RIDE_ASSIGNED,
    RIDE_CANCELLED,
    RIDE_CLUSTERED,
    RIDE_COMPLETED,
    RIDE_IN_PROGRESS,
    RIDE_PENDING,
    RIDE_READY_FOR_PICKUP,
)

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

# Fine stage -> coarse status. Every stage maps to exactly one coarse status.
CARPOOL_TO_RIDE_STATUS = {
    CARPOOL_PENDING: RIDE_PENDING,
    CARPOOL_SEARCHING: RIDE_PENDING,
    CARPOOL_CLUSTERED: RIDE_CLUSTERED,
    CARPOOL_ASSIGNED: RIDE_ASSIGNED,
    CARPOOL_DRIVER_ACCEPTED: RIDE_ASSIGNED,
    CARPOOL_DRIVER_ARRIVING: RIDE_ARRIVING,
    CARPOOL_PICKUP_READY: RIDE_ARRIVING,
    CARPOOL_PASSENGER_CONFIRMED: RIDE_READY_FOR_PICKUP,
    CARPOOL_BOARDED: RIDE_IN_PROGRESS,
    CARPOOL_IN_TRANSIT: RIDE_IN_PROGRESS,
    CARPOOL_DROPPED_OFF: RIDE_COMPLETED,
    CARPOOL_COMPLETED: RIDE_COMPLETED,
    CARPOOL_CANCELLED: RIDE_CANCELLED,
}

# Coarse status -> the stage a manual status write implies. Keeps a legacy
# PATCH /rides/{id}/status from desyncing the two axes.
RIDE_STATUS_TO_CARPOOL = {
    RIDE_PENDING: CARPOOL_PENDING,
    RIDE_CLUSTERED: CARPOOL_CLUSTERED,
    RIDE_ASSIGNED: CARPOOL_ASSIGNED,
    RIDE_ARRIVING: CARPOOL_DRIVER_ARRIVING,
    RIDE_READY_FOR_PICKUP: CARPOOL_PASSENGER_CONFIRMED,
    RIDE_IN_PROGRESS: CARPOOL_BOARDED,
    RIDE_COMPLETED: CARPOOL_COMPLETED,
    RIDE_CANCELLED: CARPOOL_CANCELLED,
}

# The forward ladder a rider walks. ``cancelled`` is terminal and deliberately
# off it, so an unknown or cancelled stage never satisfies a minimum.
CARPOOL_PROGRESS_STAGES = (
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
)

def stage_at_least(stage: Optional[str], minimum: str) -> bool:
    """Whether ``stage`` has already reached ``minimum`` on the forward ladder."""
    if stage not in CARPOOL_PROGRESS_STAGES:
        return False
    return CARPOOL_PROGRESS_STAGES.index(stage) >= CARPOOL_PROGRESS_STAGES.index(minimum)

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
