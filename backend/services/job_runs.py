"""JobRun bookkeeping: one owner for starting a run and recording its failure.

Every pipeline job opened a ``JobRun``, did its work, recorded a success summary
and committed; on any exception it rolled the session back, re-loaded the run,
recorded the failure and re-raised. That dance was copied into each job body, so
the mechanics live here once.

Job bodies keep their own success: they call :func:`finish` with the summary
they produced. Only the failure path is automatic.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional

from sqlalchemy.orm import Session

from models.job_run import JobRun


def start(
    db: Session,
    job_name: str,
    triggered_by_user_id: Optional[int] = None,
    is_scheduled: bool = True,
) -> JobRun:
    """Persist a running job record and return it."""
    job_run = JobRun(
        job_name=job_name,
        status="running",
        triggered_by_user_id=triggered_by_user_id,
        is_scheduled=is_scheduled,
        summary={},
    )
    db.add(job_run)
    db.flush()
    return job_run


def finish(
    db: Session,
    job_run: JobRun,
    status: str,
    summary: Dict,
    error_message: Optional[str] = None,
) -> None:
    """Record the outcome of a job run. The caller owns the commit."""
    job_run.status = status
    job_run.summary = summary
    job_run.error_message = error_message
    job_run.finished_at = datetime.now(timezone.utc)
    db.add(job_run)


@contextmanager
def running(
    db: Session,
    job_name: str,
    *,
    triggered_by_user_id: Optional[int] = None,
    is_scheduled: bool = True,
) -> Iterator[JobRun]:
    """Open a job run and fail it automatically if the body raises.

    The body records its own success via :func:`finish` and commits; an
    exception rolls back, records the failure and propagates.
    """
    job_run = start(db, job_name, triggered_by_user_id, is_scheduled)
    try:
        yield job_run
    except Exception as exc:
        db.rollback()
        job_run = db.merge(job_run)
        finish(db, job_run, "failed", {}, error_message=str(exc))
        db.commit()
        raise
