from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.demand_snapshot import DemandSnapshot
from backend.models.job_run import JobRun
from backend.models.user import User
from backend.models.vehicle_rebalance_suggestion import VehicleRebalanceSuggestion
from backend.schemas.jobs import (
    BackgroundJobStatusResponse,
    DemandSnapshotResponse,
    JobRunResponse,
    VehicleRebalanceSuggestionResponse,
)
from backend.services.background_jobs import (
    get_background_job_state,
    run_cluster_job,
    run_demand_refresh_job,
    run_vehicle_rebalance_job,
)
from backend.utils.auth_utils import get_current_user

router = APIRouter()


def _require_admin_or_driver(current_user: User) -> None:
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can access job controls",
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


@router.post("/run/clustering", response_model=dict)
def run_cluster_now(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_or_driver(current_user)
    return run_cluster_job(db, triggered_by_user_id=current_user.id, is_scheduled=False)


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

