"""Reads the monitoring stack for the admin panel.

Prometheus is optional *by deployment*: it only runs under the `monitoring`
compose profile, so everything here degrades to a clear "not running" answer
instead of an exception. This endpoint sits on an admin's critical path; an
absent or slow Prometheus must not take the panel down with it.

Only a fixed whitelist of queries is ever sent. Accepting caller-supplied PromQL
would hand out a full expression language over the metrics store, where one
`rate(x[1000d])` is enough to pin a CPU.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx
from sqlalchemy import case, func

from models.job_run import JobRun

# Short: the panel renders this inline, so an unreachable Prometheus must fail
# fast rather than hold a request.
PROMETHEUS_TIMEOUT_SECONDS = 2.0
JOB_WINDOW_HOURS = 24

# name -> (PromQL, what the admin should read from it)
QUERIES: Dict[str, str] = {
    "request_rate": 'sum(rate(http_requests_total[5m]))',
    "server_error_rate": 'sum(rate(http_requests_total{status=~"5.."}[5m]))',
    "throttled_rate": 'sum(rate(http_requests_total{status="429"}[5m]))',
    "p95_latency_seconds": (
        'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))'
    ),
    "busiest_routes": 'topk(6, sum by (route) (rate(http_requests_total[5m])))',
    "resident_memory_bytes": "process_resident_memory_bytes",
    "job_staleness_seconds": "time() - job_last_success_timestamp_seconds",
}


def _parse(result: List[dict]) -> List[Dict[str, Any]]:
    """Flatten Prometheus' vector response into JSON-friendly samples."""
    rows = []
    for item in result:
        raw = item.get("value") or []
        try:
            value = float(raw[1])
        except (IndexError, TypeError, ValueError):
            continue
        rows.append({"labels": dict(item.get("metric") or {}), "value": value})
    return rows


def query_prometheus(base_url: str) -> Dict[str, Any]:
    """Run every whitelisted query once. Never raises."""
    if not base_url:
        return {"reachable": False, "detail": "PROMETHEUS_BASE_URL is not configured", "series": {}}

    series: Dict[str, Any] = {}
    try:
        with httpx.Client(timeout=PROMETHEUS_TIMEOUT_SECONDS) as client:
            for name, expression in QUERIES.items():
                response = client.get(
                    f"{base_url.rstrip('/')}/api/v1/query", params={"query": expression}
                )
                if response.status_code != 200:
                    return {
                        "reachable": False,
                        "detail": f"Prometheus answered {response.status_code}",
                        "series": {},
                    }
                payload = response.json()
                if payload.get("status") != "success":
                    return {
                        "reachable": False,
                        "detail": str(payload.get("error") or "Prometheus query failed")[:200],
                        "series": {},
                    }
                series[name] = _parse(payload.get("data", {}).get("result", []))
    except Exception as exc:  # noqa: BLE001 — down/not installed/blocked are all the same answer
        return {
            "reachable": False,
            "detail": f"{type(exc).__name__}: {exc}"[:200],
            "series": {},
        }

    return {"reachable": True, "detail": None, "series": series}


def job_health(db) -> Dict[str, Any]:
    """Job outcomes straight from Postgres.

    This half works with no monitoring stack installed at all, and it is the
    only view of the worker: that container publishes no port, so nothing can
    scrape it. `job_runs` is what it leaves behind.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=JOB_WINDOW_HOURS)
    rows = (
        db.query(
            JobRun.job_name,
            func.count(JobRun.id),
            func.sum(case((JobRun.status == "success", 1), else_=0)),
            func.sum(case((JobRun.status == "failed", 1), else_=0)),
            func.max(JobRun.started_at),
        )
        .filter(JobRun.started_at >= cutoff)
        .group_by(JobRun.job_name)
        .order_by(func.max(JobRun.started_at).desc())
        .all()
    )

    now = datetime.now(timezone.utc)
    jobs = []
    for name, total, succeeded, failed, newest in rows:
        age = None
        if newest is not None:
            reference = newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc)
            age = round(max(0.0, (now - reference).total_seconds()), 1)
        jobs.append(
            {
                "job_name": name,
                "runs": total or 0,
                "succeeded": int(succeeded or 0),
                "failed": int(failed or 0),
                "seconds_since_last_run": age,
            }
        )

    recent_failures = (
        db.query(JobRun)
        .filter(JobRun.started_at >= cutoff, JobRun.status == "failed")
        .order_by(JobRun.started_at.desc())
        .limit(5)
        .all()
    )
    return {
        "window_hours": JOB_WINDOW_HOURS,
        "jobs": jobs,
        "recent_failures": [
            {
                "job_name": run.job_name,
                "started_at": run.started_at,
                "error_message": (run.error_message or "")[:280],
            }
            for run in recent_failures
        ],
    }
