"""The Prometheus surface: what it records, what it must never leak, and who
can reach it.

The route-template assertion is the important one. Labelling by concrete path
would let any scanner mint an unbounded series per URL and grow Prometheus
forever.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from main import app
from models.job_run import JobRun
from services import metrics
from utils.rate_limit import is_exempt


def _request(path: str):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    return asyncio.run(run())


def _scrape() -> str:
    return _request("/metrics").text


def test_metrics_endpoint_is_public_and_in_prometheus_format():
    body = _scrape()
    assert "# HELP" in body
    assert "# TYPE http_requests_total counter" in body
    assert "# TYPE http_request_duration_seconds histogram" in body


def test_process_metrics_only_exist_where_proc_does():
    """Documented rather than asserted as a requirement.

    prometheus_client's ProcessCollector reads /proc, so it yields nothing on
    Windows dev machines without psutil. Production is a Linux container and
    does emit these, which is what the Grafana memory panel relies on -- but a
    laptop scrape will legitimately show no process_* at all.
    """
    import platform

    body = _scrape()
    if platform.system() != "Windows":
        assert "process_resident_memory_bytes" in body
    else:
        assert "python_gc_objects_collected_total" in body


def test_counters_and_latency_use_the_route_template_not_the_concrete_path():
    _request("/health/live")
    assert 'http_requests_total{method="GET",route="/health/live",status="200"}' in _scrape()

    _request("/a-route-that-does-not-exist-424242")
    body = _scrape()
    assert 'route="unmatched"' in body
    assert "a-route-that-does-not-exist-424242" not in body


def test_job_collector_reports_worker_written_runs():
    """The worker has no port, so job_runs is the only way its health is visible."""
    session = SessionLocal()
    marker = "metrics_probe_job"
    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    try:
        session.add_all(
            [
                JobRun(job_name=marker, status="success", started_at=started, finished_at=started),
                JobRun(job_name=marker, status="failed", started_at=started, finished_at=started),
                JobRun(job_name=marker, status="failed", started_at=started, finished_at=started),
            ]
        )
        session.commit()

        body = _scrape()
        assert f'job_runs_recent_total{{job="{marker}",status="failed"}} 2.0' in body
        assert f'job_runs_recent_total{{job="{marker}",status="success"}} 1.0' in body
        assert f'job_last_run_timestamp_seconds{{job="{marker}"}}' in body
        assert f'job_last_success_timestamp_seconds{{job="{marker}"}}' in body
        assert "app_database_up 1.0" in body
    finally:
        session.query(JobRun).filter(JobRun.job_name == marker).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_a_run_outside_the_window_is_not_counted():
    session = SessionLocal()
    marker = "metrics_probe_old_job"
    try:
        old = datetime.now(timezone.utc) - timedelta(hours=metrics.JOB_WINDOW_HOURS + 2)
        session.add(JobRun(job_name=marker, status="success", started_at=old, finished_at=old))
        session.commit()
        assert marker not in _scrape()
    finally:
        session.query(JobRun).filter(JobRun.job_name == marker).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_registering_the_collector_is_idempotent():
    """A second registration would emit every job series twice."""
    def emitted() -> int:
        return _scrape().count("\napp_database_up ")

    assert emitted() == 1
    metrics.register_job_collector(SessionLocal)
    assert emitted() == 1


def test_metrics_is_exempt_from_rate_limiting():
    """A scraper polls from one container IP; throttling it reads as an outage."""
    assert is_exempt("/metrics")
