from typing import Optional

from sqlalchemy.orm import Query


LIVE_MODE = "live"
PRESENTATION_DEMO_MODE = "presentation_demo"
VALID_RIDE_MODES = {LIVE_MODE, PRESENTATION_DEMO_MODE}


def validate_ride_mode(mode: str) -> str:
    normalized = (mode or LIVE_MODE).strip().lower()
    if normalized not in VALID_RIDE_MODES:
        raise ValueError(f"Invalid ride mode: {mode}")
    return normalized


def apply_ride_scope(query: Query, mode: str = LIVE_MODE, demo_run_id: Optional[str] = None) -> Query:
    """Scope a ride query so live and presentation data cannot mix."""
    normalized = validate_ride_mode(mode)
    query = query.filter_by(mode=normalized)
    if normalized == PRESENTATION_DEMO_MODE:
        if not demo_run_id:
            raise ValueError("demo_run_id is required for presentation_demo mode")
        query = query.filter_by(demo_run_id=demo_run_id)
    return query
