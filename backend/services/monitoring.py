"""Admin-panel reads of the monitoring stack: degrade to "not running" off-profile, and only the fixed QUERIES whitelist is ever sent."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import case, func

from models.job_run import JobRun

# The panel renders inline, so an unreachable Prometheus must fail fast.
PROMETHEUS_TIMEOUT_SECONDS = 2.0
JOB_WINDOW_HOURS = 24
RECENT_FAILURES_SHOWN = 5

# Fixed whitelist: caller-supplied PromQL is a CPU-DoS vector.
QUERIES: Dict[str, str] = {
    "request_rate": 'sum(rate(http_requests_total[5m]))',
    "server_error_rate": 'sum(rate(http_requests_total{status=~"5.."}[5m]))',
    "throttled_rate": 'sum(rate(http_requests_total{status="429"}[5m]))',
    "p95_latency_seconds": (
        'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))'
    ),
    "busiest_routes": 'topk(6, sum by (route) (rate(http_requests_total[5m])))',
    "resident_memory_bytes": "process_resident_memory_bytes",
}


def _unreachable(detail: str) -> Dict[str, Any]:
    return {"reachable": False, "detail": detail[:200], "series": {}}


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
        return _unreachable("PROMETHEUS_BASE_URL is not configured")

    series: Dict[str, Any] = {}
    try:
        with httpx.Client(timeout=PROMETHEUS_TIMEOUT_SECONDS) as client:
            for name, expression in QUERIES.items():
                response = client.get(f"{base_url}/api/v1/query", params={"query": expression})
                if response.status_code != 200:
                    return _unreachable(f"Prometheus answered {response.status_code}")
                payload = response.json()
                if payload.get("status") != "success":
                    return _unreachable(str(payload.get("error") or "Prometheus query failed"))
                series[name] = _parse(payload.get("data", {}).get("result", []))
    except Exception as exc:  # noqa: BLE001 — down, absent and blocked are the same answer
        return _unreachable(f"{type(exc).__name__}: {exc}")

    return {"reachable": True, "detail": None, "series": series}


def _age_seconds(moment: Optional[datetime], now: datetime) -> Optional[float]:
    """Seconds since moment; SQLite hands back naive datetimes, so read them as UTC."""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return round(max(0.0, (now - moment).total_seconds()), 1)


def job_health(db) -> Dict[str, Any]:
    """Job outcomes derived from job_runs, the only view of the portless worker."""
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
    jobs = [
        {
            "job_name": name,
            "runs": int(total or 0),
            "succeeded": int(succeeded or 0),
            "failed": int(failed or 0),
            "seconds_since_last_run": _age_seconds(newest, now),
        }
        for name, total, succeeded, failed, newest in rows
    ]

    recent_failures = (
        db.query(JobRun)
        .filter(JobRun.started_at >= cutoff, JobRun.status == "failed")
        .order_by(JobRun.started_at.desc())
        .limit(RECENT_FAILURES_SHOWN)
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
