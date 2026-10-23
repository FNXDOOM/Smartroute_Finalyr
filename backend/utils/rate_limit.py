"""Application-level rate limiting and request-size guard.

Per-client throttling only — NOT DDoS protection, which belongs at the edge.
The sliding window lives in process memory, which is correct only while a single
`api` container runs: at N replicas every per-IP limit multiplies by N, so move
the store to Redis before scaling out. Client IP comes from uvicorn's
--proxy-headers, which stops at the first untrusted XFF hop — reading
X-Forwarded-For directly here would let a client spoof its own key.
"""

import json
import logging
import math
import time
from collections import deque
from typing import Callable, Optional, Tuple

from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config import RATE_LIMIT_ENABLED, RATE_LIMIT_DEFAULT_PER_MINUTE, MAX_BODY_BYTES
from models.user import User
from utils.auth_utils import get_current_user

logger = logging.getLogger(__name__)

# First matching prefix wins; paths are normalised so case, trailing slash and query strings cannot dodge a rule.


class RateLimitRule:
    __slots__ = ("name", "prefixes", "limit", "window_seconds", "methods")

    def __init__(self, name: str, prefixes: Tuple[str, ...], limit: int, window_seconds: int, methods: Tuple[str, ...] = ("*",)):
        self.name = name
        self.prefixes = prefixes
        self.limit = limit
        self.window_seconds = window_seconds
        self.methods = methods

    def matches(self, path: str, method: str) -> bool:
        if "*" not in self.methods and method not in self.methods:
            return False
        for prefix in self.prefixes:
            if path == prefix or path.startswith(prefix + "/"):
                return True
        return False


# Stricter where abuse is expensive: bcrypt, CPU-heavy ML/OR-Tools, paid Stadia quota, real money.
RATE_LIMIT_RULES = (
    RateLimitRule("auth_login", ("/auth/login",), limit=15, window_seconds=300, methods=("POST",)),
    RateLimitRule("auth_register", ("/auth/register",), limit=5, window_seconds=3600, methods=("POST",)),
    RateLimitRule("payments_create_order", ("/payments/create-order",), limit=10, window_seconds=600, methods=("POST",)),
    RateLimitRule("payments_verify", ("/payments/verify",), limit=20, window_seconds=600, methods=("POST",)),
    RateLimitRule("predict", ("/predict",), limit=30, window_seconds=60),
    RateLimitRule("cluster", ("/cluster/create", "/cluster/run"), limit=10, window_seconds=60, methods=("POST",)),
    RateLimitRule("route_optimize", ("/route/optimize",), limit=10, window_seconds=60, methods=("POST",)),
    RateLimitRule("routing", ("/routing",), limit=60, window_seconds=60),
    RateLimitRule("geocode", ("/geocode",), limit=60, window_seconds=60),
    RateLimitRule("maps_stadia", ("/maps/stadia",), limit=300, window_seconds=60),
    RateLimitRule("rides_request", ("/rides/request", "/rides/batch", "/rides/demo-batch", "/rides/demo-shared-batch"), limit=20, window_seconds=60, methods=("POST",)),
    RateLimitRule("jobs_run", ("/jobs/run",), limit=10, window_seconds=60, methods=("POST",)),
)

# Never throttled: probes, Razorpay webhook delivery (the signature is the access control), and the Prometheus scrape.
RATE_LIMIT_EXEMPT_PREFIXES = ("/payments/webhook", "/health", "/metrics")

_BODY_METHODS = ("POST", "PUT", "PATCH")


def normalize_path(path: str) -> str:
    """Lower-case, strip trailing slash — prevents cheap rule-dodging variants."""
    return (path.rstrip("/") or "/").lower()


def match_rule(path: str, method: str) -> Optional[RateLimitRule]:
    normalized = normalize_path(path)
    for rule in RATE_LIMIT_RULES:
        if rule.matches(normalized, method):
            return rule
    return None


def is_exempt(path: str) -> bool:
    normalized = normalize_path(path)
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in RATE_LIMIT_EXEMPT_PREFIXES
    )


# Sliding-window store, per-process memory.


class SlidingWindowStore:
    """Sliding-window log per key. Bounded memory via lazy purge + key sweep."""

    MAX_KEYS = 50_000  # ~50k concurrent client identities before eviction

    def __init__(self) -> None:
        self._hits: dict[str, deque] = {}
        self._last_seen: dict[str, float] = {}

    def check(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int, float]:
        """Return (allowed, remaining, seconds_until_reset)."""
        now = time.monotonic()
        hits = self._hits.get(key)
        if hits is None:
            self._maybe_sweep(now)
            hits = self._hits[key] = deque()

        cutoff = now - window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            reset_after = max(0.0, hits[0] + window_seconds - now)
            self._last_seen[key] = now
            return False, 0, reset_after

        hits.append(now)
        self._last_seen[key] = now
        return True, limit - len(hits), window_seconds

    def _maybe_sweep(self, now: float) -> None:
        if len(self._hits) <= self.MAX_KEYS:
            return
        # Evict least-recently-seen identities (abuse-memory guard).
        keep = sorted(self._last_seen.items(), key=lambda kv: kv[1], reverse=True)[: self.MAX_KEYS // 2]
        keep_keys = {k for k, _ in keep}
        self._hits = {k: v for k, v in self._hits.items() if k in keep_keys}
        self._last_seen = {k: ts for k, ts in self._last_seen.items() if k in keep_keys}


store = SlidingWindowStore()


def client_ip(request: Request) -> str:
    """uvicorn's already-resolved client host; never read raw X-Forwarded-For, it is spoofable."""
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host


def _limit_key(scope: str, identifier: str, rule_name: str) -> str:
    return f"{scope}|{identifier}|{rule_name}"


def check_ip_limit(request: Request) -> Tuple[bool, int, int, float]:
    """Apply the endpoint rule (or default) for this client IP: (allowed, limit, remaining, reset_after)."""
    ip = client_ip(request)
    rule = match_rule(request.url.path, request.method)
    if rule is not None:
        limit, window, name = rule.limit, rule.window_seconds, rule.name
    else:
        limit, window, name = RATE_LIMIT_DEFAULT_PER_MINUTE, 60, "default"
    allowed, remaining, reset_after = store.check(_limit_key("ip", ip, name), limit, window)
    return allowed, limit, remaining, reset_after


def enforce_user_rate_limit(name: str, limit: int, window_seconds: int) -> Callable:
    """Per-USER limit for endpoints where per-IP is not enough (authenticated payments).

    Depends on get_current_user so FastAPI's request-scoped dependency cache resolves
    the user first without repeating the auth lookup.
    """

    def _dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> None:
        allowed, _remaining, reset_after = store.check(
            _limit_key("user", str(current_user.id), name), limit, window_seconds
        )
        if not allowed:
            logger.warning(
                "Rate limit exceeded: scope=user user_id=%d rule=%s path=%s",
                current_user.id,
                name,
                normalize_path(request.url.path),
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(int(math.ceil(reset_after)))},
            )

    return _dependency


def _json_error(status_code: int, detail: str, headers: Optional[dict] = None) -> Response:
    return Response(
        content=json.dumps({"detail": detail}),
        status_code=status_code,
        media_type="application/json",
        headers=headers or {},
    )


class RateLimitBodyGuardMiddleware(BaseHTTPMiddleware):
    """Size cap + per-IP limit. Registered first in main.py, so it is the innermost middleware and its 429s get counted."""

    async def dispatch(self, request: Request, call_next):
        # Preflight must always pass or browsers cannot call the API at all.
        if request.method == "OPTIONS":
            return await call_next(request)

        if not RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = normalize_path(request.url.path)

        # 1. Request-size guard (before rate limit: reject junk instantly).
        if request.method in _BODY_METHODS:
            content_length = request.headers.get("content-length")
            if content_length is not None and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
                return _json_error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "Request body too large",
                )
            elif content_length is None and "chunked" in request.headers.get("transfer-encoding", "").lower():
                # This API is JSON-only; no legitimate chunked senders exist.
                return _json_error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "Chunked request bodies are not accepted",
                )

        # 2. Rate limit (exempt paths skip entirely).
        if is_exempt(path):
            return await call_next(request)

        allowed, limit, remaining, reset_after = check_ip_limit(request)
        if not allowed:
            return _json_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(max(1, int(math.ceil(reset_after))))},
            )

        response = await call_next(request)
        # Visibility for clients and for log-based monitoring.
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + reset_after))
        return response
