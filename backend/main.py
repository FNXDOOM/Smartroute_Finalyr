import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import engine, run_startup_migrations, SessionLocal
from routers import auth, rides, cluster, route, routing, geocode, maps, vehicle, predict, tracking, notifications
from routers import analytics
from routers import jobs
from routers import payments
from config import (
    ALLOWED_ORIGINS,
    APP_ENV,
    ENABLE_TRACKING_BROADCAST,
    ENABLE_BACKGROUND_JOBS_IN_API,
    LOG_LEVEL,
)
from utils.rate_limit import RateLimitBodyGuardMiddleware
from services import metrics
from services.background_jobs import start_background_jobs, stop_background_jobs

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown tasks."""
    # Additive backfill in case `alembic upgrade head` was skipped. A DB blip must not stop the
    # API from booting, so the failure is logged and the process still serves.
    try:
        run_startup_migrations()
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).error("Startup schema backfill failed: %s", exc)
    # Jobs run in the worker; the API only owns the WS broadcast loop.
    if ENABLE_TRACKING_BROADCAST:
        tracking.start_simulation()
    if ENABLE_BACKGROUND_JOBS_IN_API:
        start_background_jobs()
    yield
    if ENABLE_BACKGROUND_JOBS_IN_API:
        await stop_background_jobs()


def local_origin_regex(app_env: str) -> str | None:
    """Permit any localhost port only outside production; deploy.sh already forbids localhost origins there."""
    if app_env == "production":
        return None
    return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


app = FastAPI(title="SmartRouteAI", version="1.0.0", lifespan=lifespan)

# Added first, so Starlette's prepend leaves it innermost; it still runs before any endpoint work.
# NOT DDoS protection — volumetric attacks are handled at the proxy/edge.
app.add_middleware(RateLimitBodyGuardMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=local_origin_regex(APP_ENV),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _maybe_add_dev_csp(request: Request, call_next):
    """Relaxed CSP for local dev only."""
    response = await call_next(request)
    is_local_dev = APP_ENV == "development"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if is_local_dev:
        response.headers["Content-Security-Policy"] = (
            # Allow Clerk assets (local dev only).
            "default-src 'self' https://*.clerk.accounts.dev; "
            "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://*.clerk.accounts.dev; "
            "style-src 'self' 'unsafe-inline' https://*.clerk.accounts.dev; "
            "connect-src 'self' https://*.clerk.accounts.dev; "
            "frame-src https://*.clerk.accounts.dev; "
            "img-src 'self' data: https://*.clerk.accounts.dev;"
        )
    return response

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(rides.router, prefix="/rides", tags=["Rides"])
app.include_router(cluster.router, prefix="/cluster", tags=["Cluster"])
app.include_router(route.router, prefix="/route", tags=["Route"])
app.include_router(routing.router, prefix="/routing", tags=["Routing"])
app.include_router(geocode.router, prefix="/geocode", tags=["Geocoding"])
app.include_router(maps.router, prefix="/maps/stadia", tags=["Maps"])
app.include_router(vehicle.router, prefix="/vehicle", tags=["Vehicle"])
app.include_router(predict.router, prefix="/predict", tags=["Predict"])
app.include_router(tracking.router, prefix="/tracking", tags=["Tracking"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
app.include_router(payments.router, prefix="/payments", tags=["Payments"])


# Registered last, so it is outermost and also sees requests the rate limiter rejects.
@app.middleware("http")
async def _record_request_metrics(request: Request, call_next):
    """Count and time every request against its matched route template."""
    if request.url.path == "/metrics":
        return await call_next(request)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = metrics.route_label(request)
        metrics.HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
        metrics.HTTP_LATENCY.labels(route).observe(time.perf_counter() - started)


metrics.register_job_collector(SessionLocal)


@app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def prometheus_metrics():
    """Scrape endpoint: unauthenticated because a scraper holds no JWT, safe because nothing publishes it."""
    return PlainTextResponse(metrics.render(), media_type=metrics.CONTENT_TYPE_LATEST)


@app.get("/")
def root():
    """Return basic API service metadata."""
    return {"message": "SmartRouteAI API is running"}


@app.get("/health/live", tags=["Health"])
def liveness():
    """Liveness probe."""
    return {"status": "ok", "environment": APP_ENV}


@app.get("/health/ready", tags=["Health"])
def readiness():
    """Readiness probe."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).warning("readiness check failed: %s", exc.__class__.__name__)
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "ok"}
