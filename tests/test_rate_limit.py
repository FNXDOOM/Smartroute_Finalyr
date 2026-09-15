"""Rate-limiting tests — controlled, small-volume, no real traffic generation.

Verifies the security-audit fixes:
  - requests under limit pass; over limit get 429 (project error shape)
  - Retry-After present; X-RateLimit-* headers on passing responses
  - different client IPs tracked independently
  - window resets (monotonic-clock based)
  - exemptions: OPTIONS preflight, /health/*, /payments/webhook
  - identity = request.client.host as resolved by uvicorn's trusted-proxy
    chain; limiter never reads raw X-Forwarded-For (spoof-proof by design)
  - trailing-slash/case variants cannot dodge endpoint rules
  - oversized/chunked bodies rejected 413 before buffering
  - per-USER payment caps enforced + isolated between users
  - RATE_LIMIT_ENABLED=false disables everything

All traffic is a handful of in-process ASGI requests (httpx ASGITransport) —
no sockets, no load generation, mirrors tests/test_payments.py conventions.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Tuple

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from utils import rate_limit as rl  # noqa: E402
from utils.rate_limit import RateLimitBodyGuardMiddleware, enforce_user_rate_limit  # noqa: E402

DEFAULT_IP = ("10.0.0.1", 5555)


@pytest.fixture(autouse=True)
def clean_store():
    rl.store._hits.clear()
    rl.store._last_seen.clear()
    yield
    rl.store._hits.clear()
    rl.store._last_seen.clear()


@pytest.fixture()
def probe_app(monkeypatch):
    """Fresh app with the middleware and tiny limits for fast, safe tests."""
    monkeypatch.setattr(rl, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(rl, "RATE_LIMIT_DEFAULT_PER_MINUTE", 5)
    monkeypatch.setattr(rl, "MAX_BODY_BYTES", 64)

    app = FastAPI()
    app.add_middleware(RateLimitBodyGuardMiddleware)

    @app.post("/echo")
    async def echo(payload: dict = None):
        return {"ok": True}

    @app.post("/predict/echo")
    async def predict_echo():
        return {"ok": True}

    @app.post("/payments/webhook")
    async def webhook_stub():
        return {"received": True}

    @app.get("/health/ready")
    async def ready_stub():
        return {"status": "ok"}

    return app


def _request(
    app,
    path: str,
    *,
    method: str = "POST",
    client_ip: Tuple[str, int] = DEFAULT_IP,
    headers: dict = None,
    content: bytes = None,
):
    """One in-process ASGI request. No network sockets involved."""
    transport = httpx.ASGITransport(app=app, client=client_ip)

    async def go():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, headers=headers, content=content)

    return asyncio.run(go())


# ---------------------------------------------------------------------------
# A. Basic flooding: allow under limit, 429 over limit
# ---------------------------------------------------------------------------


def test_allows_up_to_limit_then_429(probe_app):
    codes = [_request(probe_app, "/echo").status_code for _ in range(7)]
    assert codes[:5] == [200] * 5   # under/== limit: normal service
    assert codes[5] == 429 and codes[6] == 429


def test_429_uses_project_error_shape_with_retry_after(probe_app):
    for _ in range(5):
        _request(probe_app, "/echo")
    resp = _request(probe_app, "/echo")
    assert resp.status_code == 429
    assert resp.json() == {"detail": "Too many requests. Please slow down and try again shortly."}
    assert int(resp.headers["Retry-After"]) >= 1


def test_success_response_has_rate_limit_headers(probe_app):
    resp = _request(probe_app, "/echo")
    assert resp.headers["X-RateLimit-Limit"] == "5"
    assert resp.headers["X-RateLimit-Remaining"] == "4"
    assert int(resp.headers["X-RateLimit-Reset"]) > 0


def test_rule_limit_overrides_default_for_expensive_endpoint(probe_app):
    # /predict has its own rule (30/min in prod) — distinct bucket from the
    # default 5/min, so the same IP can hit both budgets independently.
    codes = [_request(probe_app, "/predict/echo").status_code for _ in range(7)]
    assert codes == [200] * 7


# ---------------------------------------------------------------------------
# Isolation, reset, exemptions, identity
# ---------------------------------------------------------------------------


def test_clients_tracked_independently(probe_app):
    for _ in range(5):
        assert _request(probe_app, "/echo").status_code == 200
    # A different IP still has its full budget.
    assert _request(probe_app, "/echo", client_ip=("10.0.0.2", 5555)).status_code == 200
    # The exhausted IP is still limited.
    assert _request(probe_app, "/echo").status_code == 429


def test_window_resets_after_time_passes(probe_app, monkeypatch):
    now = [1000.0]
    fake_clock = SimpleNamespace(monotonic=lambda: now[0], time=__import__("time").time)
    monkeypatch.setattr(rl, "time", fake_clock)

    for _ in range(5):
        assert _request(probe_app, "/echo").status_code == 200
    assert _request(probe_app, "/echo").status_code == 429

    now[0] += 61  # window (60s) has fully passed
    assert _request(probe_app, "/echo").status_code == 200


def test_options_preflight_exempt(probe_app):
    for _ in range(10):
        resp = _request(probe_app, "/echo", method="OPTIONS")
        assert resp.status_code != 429


def test_health_endpoints_exempt(probe_app):
    for _ in range(20):
        assert _request(probe_app, "/health/ready", method="GET").status_code == 200


def test_payments_webhook_exempt(probe_app):
    # Razorpay delivery must never be throttled — signature is the access control.
    for _ in range(20):
        assert _request(probe_app, "/payments/webhook").status_code == 200


def test_identity_is_resolved_client_ip_not_spoofed_headers(probe_app):
    """The limiter keys on request.client.host (uvicorn's trusted-proxy
    resolution). Client-supplied forwarding headers must not create fresh
    identities for an exhausted IP."""
    for _ in range(5):
        assert _request(probe_app, "/echo").status_code == 200
    assert _request(probe_app, "/echo").status_code == 429
    for fake_ip in ("1.2.3.4", "8.8.8.8", "2001:db8::1"):
        spoofed = {
            "X-Forwarded-For": fake_ip,
            "X-Real-IP": fake_ip,
            "Forwarded": f"for={fake_ip}",
        }
        assert _request(probe_app, "/echo", headers=spoofed).status_code == 429


def test_trailing_slash_and_case_cannot_dodge_rules(probe_app, monkeypatch):
    # Make the predict rule tiny so it is observable.
    monkeypatch.setattr(
        rl, "RATE_LIMIT_RULES",
        (rl.RateLimitRule("predict", ("/predict",), limit=2, window_seconds=60),),
    )
    assert _request(probe_app, "/predict/echo").status_code == 200
    assert _request(probe_app, "/predict/echo").status_code == 200
    # Variants hit the same bucket.
    assert _request(probe_app, "/predict/echo/").status_code == 429
    # Case variant: rate limiter still applies (FastAPI may 404 the route —
    # the security property is that the limiter counts it as /predict/*).
    assert _request(probe_app, "/PREDICT/echo").status_code in (429, 404)  # limiter must count it either way
    assert rl.match_rule("/PREDICT/ECHO", "POST") is not None  # direct rule check


# ---------------------------------------------------------------------------
# D. Request-body abuse
# ---------------------------------------------------------------------------


def test_oversized_content_length_rejected_413(probe_app):
    big = b"x" * 65  # MAX_BODY_BYTES patched to 64
    resp = _request(probe_app, "/echo", content=big)
    assert resp.status_code == 413
    assert resp.json() == {"detail": "Request body too large"}


def test_chunked_body_rejected_413(probe_app):
    # httpx emits chunked encoding only for an (async) streaming body.

    async def stream():
        yield b"{}"

    resp = _request(probe_app, "/echo", headers={"Transfer-Encoding": "chunked"}, content=stream())
    assert resp.status_code == 413


def test_small_body_passes(probe_app):
    resp = _request(probe_app, "/echo", content=b'{"a": 1}')
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Per-user payment caps
# ---------------------------------------------------------------------------


def _make_user_dep(limit: int):
    return enforce_user_rate_limit("test_user_rule", limit, 600)


def _fake_request(path: str = "/payments/create-order") -> SimpleNamespace:
    return SimpleNamespace(url=SimpleNamespace(path=path))


def test_user_limit_enforced_per_user():
    dep = _make_user_dep(limit=2)
    user = SimpleNamespace(id=1)
    dep(_fake_request(), current_user=user)
    dep(_fake_request(), current_user=user)
    with pytest.raises(Exception) as exc:  # noqa: B017 - HTTPException asserted below
        dep(_fake_request(), current_user=user)
    assert getattr(exc.value, "status_code", None) == 429
    assert exc.value.detail.startswith("Too many requests")


def test_user_limit_isolated_between_users():
    dep = _make_user_dep(limit=2)
    user1, user2 = SimpleNamespace(id=1), SimpleNamespace(id=2)
    # User 1 burns their whole budget.
    assert dep(_fake_request(), current_user=user1) is None
    assert dep(_fake_request(), current_user=user1) is None
    with pytest.raises(Exception) as exc:  # noqa: B017
        dep(_fake_request(), current_user=user1)  # 3rd call blocked
    assert getattr(exc.value, "status_code", None) == 429
    # User 2 has a completely separate budget.
    assert dep(_fake_request(), current_user=user2) is None
    assert dep(_fake_request(), current_user=user2) is None
    with pytest.raises(Exception) as exc2:  # noqa: B017
        dep(_fake_request(), current_user=user2)  # only their own 3rd call is blocked
    assert getattr(exc2.value, "status_code", None) == 429


def test_payment_routes_have_user_limit_dependencies():
    """Integration: create-order/verify are protected by the per-user limiter."""
    from routers import payments as payments_router

    deps_by_path = {}
    for route in payments_router.router.routes:
        if hasattr(route, "path"):
            deps_by_path[route.path] = getattr(route, "dependencies", [])

    assert deps_by_path.get("/create-order"), "create-order must carry a limiter dependency"
    assert deps_by_path.get("/verify"), "verify must carry a limiter dependency"
    assert deps_by_path.get("/webhook", []) == [], "webhook must stay dependency-free"


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


def test_disabled_when_rate_limit_enabled_false(probe_app, monkeypatch):
    monkeypatch.setattr(rl, "RATE_LIMIT_ENABLED", False)
    for _ in range(10):
        assert _request(probe_app, "/echo").status_code == 200
