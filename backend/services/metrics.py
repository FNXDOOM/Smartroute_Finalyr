"""Prometheus exposition for the API: job health comes from job_runs, the only channel to the portless worker; /proc metrics are absent on Windows."""

from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from sqlalchemy import case, func

from models.job_run import JobRun

# Covers a stalled 60s schedule while staying narrow enough for the index.
JOB_WINDOW_HOURS = 24

# Unroutable paths collapse to this one label so a scanner cannot mint a series per URL.
UNMATCHED_ROUTE = "unmatched"

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "API requests by method, matched route template and status code.",
    ("method", "route", "status"),
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "API request latency by matched route template.",
    ("route",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)


def route_label(request) -> str:
    """The matched route template, so path parameters never become labels."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or UNMATCHED_ROUTE


def _epoch(value: Optional[datetime]) -> float:
    """Seconds since the epoch; SQLite hands back naive datetimes."""
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


class JobRunCollector:
    """Emits job_runs-derived series, computed at scrape time."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def collect(self) -> Iterator:
        last_success = GaugeMetricFamily(
            "job_last_success_timestamp_seconds",
            "Start of the most recent successful run of a background job.",
            labels=["job"],
        )
        last_run = GaugeMetricFamily(
            "job_last_run_timestamp_seconds",
            "Start of the most recent run of a background job, any outcome.",
            labels=["job"],
        )
        recent = CounterMetricFamily(
            "job_runs_recent_total",
            f"Background job runs recorded in the last {JOB_WINDOW_HOURS} hours.",
            labels=["job", "status"],
        )
        db_up = GaugeMetricFamily("app_database_up", "1 when the scrape could read job_runs.")

        try:
            rows = self._query()
        except Exception:  # noqa: BLE001 — one bad query must not void the whole payload
            db_up.add_metric([], 0)
            yield db_up
            return

        db_up.add_metric([], 1)
        for job_name, succeeded, failed, running, newest, newest_success in rows:
            name = job_name or "unknown"
            if newest is not None:
                last_run.add_metric([name], _epoch(newest))
            if newest_success is not None:
                last_success.add_metric([name], _epoch(newest_success))
            for status, count in (("success", succeeded), ("failed", failed), ("running", running)):
                recent.add_metric([name, status], count or 0)

        yield db_up
        yield last_run
        yield last_success
        yield recent

    def _query(self):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=JOB_WINDOW_HOURS)
        db = self._session_factory()
        try:
            return (
                db.query(
                    JobRun.job_name,
                    func.sum(case((JobRun.status == "success", 1), else_=0)),
                    func.sum(case((JobRun.status == "failed", 1), else_=0)),
                    func.sum(case((JobRun.status == "running", 1), else_=0)),
                    func.max(JobRun.started_at),
                    func.max(case((JobRun.status == "success", JobRun.started_at))),
                )
                .filter(JobRun.started_at >= cutoff)
                .group_by(JobRun.job_name)
                .all()
            )
        finally:
            db.close()


_registered = False


def register_job_collector(session_factory) -> None:
    """Attach the job collector to the default registry, at most once."""
    global _registered
    if _registered:
        return
    REGISTRY.register(JobRunCollector(session_factory))
    _registered = True


def render() -> bytes:
    return generate_latest(REGISTRY)
