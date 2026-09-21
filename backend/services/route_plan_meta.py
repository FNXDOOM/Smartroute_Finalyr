"""The typed interface to a route plan's ``metadata`` JSON bag.

``RoutePlan.route_metadata`` is an untyped dict that nine modules read and write,
each with its own ``(metadata or {}).get(key, default)`` and its own idea of the
key set, the value types and the invariants. Nothing could tell a caller what is
in the bag, and renaming a key was a silent breakage.

This module is the single interface to the bag. Creation (``persist_shared_route``)
is the one place allowed to write the initial shape wholesale; everything after
that reads and mutates through here.

The wire keys are part of the API contract — the frontend reads
``route_metadata`` directly — so they must not change.
"""

from typing import Any, Dict, List, Optional

# Wire keys.
_PROBLEM = "problem"
_CARPOOL_RUN = "carpool_run"
_DRIVER_ACCEPTED = "driver_accepted"
_DRIVER_ACCEPTED_AT = "driver_accepted_at"
_RUN_STATUS = "carpool_run_status"
_COMPLETED_AT = "completed_at"
_ASSIGNED_STOP_IDS = "assigned_stop_ids"
_ASSIGNED_DROPOFF_IDS = "assigned_dropoff_request_ids"
_NEEDS_REOPTIMIZATION = "needs_reoptimization"
_GEOMETRY = "geometry"
_LEGS = "legs"
_MANEUVERS = "maneuvers"
_ROUTING_PROVIDER = "routing_provider"
_GEOMETRY_RESOLVED = "geometry_resolved"
_CANCELLED_REASON = "cancelled_reason"

DEFAULT_PROBLEM = "pdp"
ACCEPTED = "accepted"
COMPLETED = "completed"


def _bag(route_plan) -> Dict[str, Any]:
    """A writable copy of the bag; hand it back through ``_store``."""
    metadata = route_plan.route_metadata
    return dict(metadata) if isinstance(metadata, dict) else {}


def _store(route_plan, bag: Dict[str, Any]) -> None:
    route_plan.route_metadata = bag


# -- reads -------------------------------------------------------------------

def problem(route_plan) -> str:
    """The routing problem this plan was solved for; ``pdp`` when unset."""
    return str(_bag(route_plan).get(_PROBLEM) or DEFAULT_PROBLEM)


def is_carpool(route_plan) -> bool:
    """Whether the plan carries pooled (shared) riders."""
    return bool(_bag(route_plan).get(_CARPOOL_RUN))


def is_driver_accepted(route_plan) -> bool:
    """Whether the serving driver has accepted the assigned plan."""
    return bool(_bag(route_plan).get(_DRIVER_ACCEPTED))


def run_status(route_plan) -> Optional[str]:
    """The carpool run's own status, or ``None`` for a plain route."""
    return _bag(route_plan).get(_RUN_STATUS)


def assigned_stop_ids(route_plan) -> List[int]:
    return list(_bag(route_plan).get(_ASSIGNED_STOP_IDS) or [])


def assigned_dropoff_request_ids(route_plan) -> List[int]:
    return list(_bag(route_plan).get(_ASSIGNED_DROPOFF_IDS) or [])


def geometry(route_plan) -> List[Any]:
    return _bag(route_plan).get(_GEOMETRY) or []


def legs(route_plan) -> List[Any]:
    return _bag(route_plan).get(_LEGS) or []


def routing_provider(route_plan) -> str:
    return str(_bag(route_plan).get(_ROUTING_PROVIDER) or "unknown")


def is_geometry_resolved(route_plan) -> bool:
    """Whether a geometry fetch was already attempted (success or failure)."""
    return bool(_bag(route_plan).get(_GEOMETRY_RESOLVED))


# -- writes ------------------------------------------------------------------

def mark_driver_accepted(route_plan, accepted_at: str) -> None:
    """Record acceptance, which also closes a carpool run to new riders."""
    bag = _bag(route_plan)
    bag[_DRIVER_ACCEPTED] = True
    bag[_DRIVER_ACCEPTED_AT] = accepted_at
    if bag.get(_CARPOOL_RUN):
        bag[_RUN_STATUS] = ACCEPTED
    _store(route_plan, bag)


def mark_run_completed(route_plan, completed_at: str) -> None:
    """Record completion, preserving an earlier ``completed_at`` if present."""
    bag = _bag(route_plan)
    bag[_RUN_STATUS] = COMPLETED
    bag[_COMPLETED_AT] = bag.get(_COMPLETED_AT) or completed_at
    _store(route_plan, bag)


def mark_cancelled(route_plan, reason: str) -> None:
    """Record why a plan was cancelled before it was served."""
    bag = _bag(route_plan)
    bag[_CANCELLED_REASON] = reason
    _store(route_plan, bag)


def record_detach(route_plan, *, remaining: bool, dropoff_request_ids: List[int]) -> None:
    """Record a rider leaving the itinerary and whether others remain."""
    bag = _bag(route_plan)
    bag[_ASSIGNED_DROPOFF_IDS] = dropoff_request_ids
    bag[_NEEDS_REOPTIMIZATION] = remaining
    _store(route_plan, bag)


def record_geometry_resolved(route_plan) -> None:
    """Mark a geometry fetch as attempted so it is not retried every poll."""
    bag = _bag(route_plan)
    bag[_GEOMETRY_RESOLVED] = True
    _store(route_plan, bag)


def record_geometry(route_plan, *, geometry, legs, maneuvers, provider: str) -> None:
    bag = _bag(route_plan)
    bag[_GEOMETRY] = geometry
    bag[_LEGS] = legs
    bag[_MANEUVERS] = maneuvers
    bag[_ROUTING_PROVIDER] = provider
    _store(route_plan, bag)
