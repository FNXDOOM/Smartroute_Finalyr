from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models.demand_snapshot import DemandSnapshot
from models.job_run import JobRun
from models.user import User
from models.vehicle_rebalance_suggestion import VehicleRebalanceSuggestion
from schemas.jobs import (
    BackgroundJobStatusResponse,
    DemandSnapshotResponse,
    JobRunResponse,
    VehicleRebalanceSuggestionResponse,
)
from services.background_jobs import (
    get_background_job_state,
    run_auto_dispatch_pipeline,
    run_cluster_job,
    run_demand_refresh_job,
    run_vehicle_rebalance_job,
)
from utils.auth_utils import get_current_user
from utils.ride_scope import LIVE_MODE, PRESENTATION_DEMO_MODE, validate_ride_mode

router = APIRouter()


def _require_admin_or_driver(current_user: User) -> None:
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can access job controls",
        )


def _require_job_access(current_user: User, mode: str) -> None:
    """Keep live controls restricted while allowing isolated demo playback."""
    if current_user.role in {"admin", "driver"} or mode == PRESENTATION_DEMO_MODE:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only admin or driver users can access live job controls",
    )


@router.get("/status", response_model=BackgroundJobStatusResponse)
def get_job_status(current_user: User = Depends(get_current_user)):
    _require_admin_or_driver(current_user)
    state = get_background_job_state()
    return BackgroundJobStatusResponse(
        status="ok",
        scheduler_running=state["running"],
        cluster_interval_seconds=state["cluster_interval_seconds"],
        demand_interval_seconds=state["demand_interval_seconds"],
        rebalance_interval_seconds=state["rebalance_interval_seconds"],
        last_cluster_run_at=state["last_cluster_run_at"],
        last_demand_run_at=state["last_demand_run_at"],
        last_rebalance_run_at=state["last_rebalance_run_at"],
        active_tasks=state["active_tasks"],
    )


@router.get("/runs", response_model=List[JobRunResponse])
def list_job_runs(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_or_driver(current_user)
    runs = db.query(JobRun).order_by(JobRun.started_at.desc()).limit(limit).all()
    return [JobRunResponse.model_validate(run) for run in runs]


@router.get("/demand-snapshots", response_model=List[DemandSnapshotResponse])
def list_demand_snapshots(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_or_driver(current_user)
    snapshots = db.query(DemandSnapshot).order_by(DemandSnapshot.created_at.desc()).limit(limit).all()
    return [DemandSnapshotResponse.model_validate(snapshot) for snapshot in snapshots]


@router.get("/rebalance-suggestions", response_model=List[VehicleRebalanceSuggestionResponse])
def list_rebalance_suggestions(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_or_driver(current_user)
    suggestions = (
        db.query(VehicleRebalanceSuggestion)
        .order_by(VehicleRebalanceSuggestion.created_at.desc())
        .limit(limit)
        .all()
    )
    return [VehicleRebalanceSuggestionResponse.model_validate(suggestion) for suggestion in suggestions]


@router.post("/run/auto-dispatch", response_model=dict)
def run_auto_dispatch_now(
    mode: str = Query(LIVE_MODE, description="live | presentation_demo"),
    demo_run_id: Optional[str] = Query(None, min_length=1, max_length=64),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        mode = validate_ride_mode(mode)
        _require_job_access(current_user, mode)
        return run_auto_dispatch_pipeline(
            db,
            triggered_by_user_id=current_user.id,
            is_scheduled=False,
            mode=mode,
            demo_run_id=demo_run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/run/clustering", response_model=dict)
def run_cluster_now(
    mode: str = Query(LIVE_MODE, description="live | presentation_demo"),
    demo_run_id: Optional[str] = Query(None, min_length=1, max_length=64),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        mode = validate_ride_mode(mode)
        _require_job_access(current_user, mode)
        return run_cluster_job(
            db,
            triggered_by_user_id=current_user.id,
            is_scheduled=False,
            mode=mode,
            demo_run_id=demo_run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/run/demand", response_model=dict)
def run_demand_now(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_or_driver(current_user)
    return run_demand_refresh_job(db, triggered_by_user_id=current_user.id, is_scheduled=False)


@router.post("/run/rebalance", response_model=dict)
def run_rebalance_now(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_or_driver(current_user)
    return run_vehicle_rebalance_job(db, triggered_by_user_id=current_user.id, is_scheduled=False)

