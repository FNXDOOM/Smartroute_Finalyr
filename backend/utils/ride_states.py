"""Status vocabularies for the ride, route and vehicle axes, plus their shared predicates.

These were re-listed as string literals across routers, services and jobs, so renaming a value
broke silently. The values are part of the wire contract — clients and the frontend read them —
so they must not change. The fine per-rider carpool ladder lives in utils/carpool_status.py.
"""

from typing import Optional, Tuple

# -- RideRequest.status (coarse) ---------------------------------------------
RIDE_PENDING = "pending"
RIDE_CLUSTERED = "clustered"
RIDE_ASSIGNED = "assigned"
RIDE_ARRIVING = "arriving"
RIDE_READY_FOR_PICKUP = "ready_for_pickup"
RIDE_IN_PROGRESS = "in_progress"
RIDE_COMPLETED = "completed"
RIDE_CANCELLED = "cancelled"

RIDE_STATUSES: Tuple[str, ...] = (
    RIDE_PENDING,
    RIDE_CLUSTERED,
    RIDE_ASSIGNED,
    RIDE_ARRIVING,
    RIDE_READY_FOR_PICKUP,
    RIDE_IN_PROGRESS,
    RIDE_COMPLETED,
    RIDE_CANCELLED,
)

# A ride that has left the pipeline: never advanced, rewritten or counted as outstanding again.
RIDE_TERMINAL_STATUSES = frozenset({RIDE_COMPLETED, RIDE_CANCELLED})
# A ride still in the pipeline (anything not terminal).
RIDE_IN_PIPELINE_STATUSES: Tuple[str, ...] = tuple(
    status for status in RIDE_STATUSES if status not in RIDE_TERMINAL_STATUSES
)
# Bound to a route and not yet finished — what a detach demotes when an itinerary goes stale.
RIDE_BOUND_STATUSES = (RIDE_ASSIGNED, RIDE_ARRIVING)
# A ride the simulator/serving path considers on board a route.
RIDE_SERVING_STATUSES = (RIDE_ASSIGNED, RIDE_ARRIVING, RIDE_IN_PROGRESS)

def is_terminal_ride(status: Optional[str]) -> bool:
    return status in RIDE_TERMINAL_STATUSES

# -- RoutePlan.status --------------------------------------------------------
ROUTE_SOLVED = "solved"
ROUTE_NEEDS_REOPTIMIZATION = "needs_reoptimization"
ROUTE_COMPLETED = "completed"
ROUTE_CANCELLED = "cancelled"
ROUTE_SUPERSEDED = "superseded"

# A co-passenger cancellation leaves a plan needs_reoptimization while other riders are on board, so it stays live; only completed ends the run.
LIVE_ROUTE_STATUSES: Tuple[str, ...] = (ROUTE_SOLVED, ROUTE_NEEDS_REOPTIMIZATION)
CLOSABLE_ROUTE_STATUSES: Tuple[str, ...] = (*LIVE_ROUTE_STATUSES, ROUTE_COMPLETED)

# -- Vehicle.status ----------------------------------------------------------
VEHICLE_IDLE = "idle"
VEHICLE_ACTIVE = "active"
VEHICLE_EN_ROUTE = "en_route"
VEHICLE_OFFLINE = "offline"

# A vehicle that may be handed a route.
DISPATCHABLE_VEHICLE_STATUSES = frozenset({VEHICLE_IDLE, VEHICLE_ACTIVE, VEHICLE_EN_ROUTE})

def vehicle_is_dispatchable(status: Optional[str]) -> bool:
    return status in DISPATCHABLE_VEHICLE_STATUSES
