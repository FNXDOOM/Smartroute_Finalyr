import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import engine
from routers import auth, rides, cluster, route, routing, geocode, maps, vehicle, predict, tracking, notifications
from routers import analytics
from routers import jobs
from config import ALLOWED_ORIGINS, APP_ENV, ENABLE_TRACKING_BROADCAST, ENABLE_BACKGROUND_JOBS_IN_API
from services.background_jobs import start_background_jobs, stop_background_jobs

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Scheduled jobs normally run in the dedicated worker process (see
    # backend/worker.py + docker-compose.yml) so the API process only owns
    # the broadcast loop needed by its connected WebSocket clients.
    #
    # ENABLE_BACKGROUND_JOBS_IN_API is an opt-in for local/single-process dev:
    # without a worker process running, rides that reach "assigned" never
    # auto-advance to arriving/in_progress/completed, since that transition
    # is entirely driven by the periodic simulate_ride_dispatch job.
    if ENABLE_TRACKING_BROADCAST:
        tracking.start_simulation()
    if ENABLE_BACKGROUND_JOBS_IN_API:
        start_background_jobs()
    yield
    if ENABLE_BACKGROUND_JOBS_IN_API:
        await stop_background_jobs()


app = FastAPI(title="SmartRouteAI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _maybe_add_dev_csp(request: Request, call_next):
    """During local development, add a relaxed CSP that allows `unsafe-eval` so
    dev tools and certain dev-only bundles don't trigger CSP errors when the
    frontend is served through the backend. This middleware enables the relaxed
    header only when `allowed_origins` appears to include a localhost dev URL.

    IMPORTANT: Do NOT ship this to production. The header reduces CSP security.
    """
    response = await call_next(request)
    try:
        origins = ALLOWED_ORIGINS
    except NameError:
        origins = []

    is_local_dev = any("localhost" in o or "127.0.0.1" in o for o in origins)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if is_local_dev:
        response.headers["Content-Security-Policy"] = (
            # Allow Clerk's hosted assets and API across all relevant directives.
            # This only applies during local development (see is_local_dev guard above).
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


@app.get("/")
def root():
    return {"message": "SmartRouteAI API is running"}


@app.get("/health/live", tags=["Health"])
def liveness():
    """Process liveness probe; does not require the database."""
    return {"status": "ok", "environment": APP_ENV}


@app.get("/health/ready", tags=["Health"])
def readiness():
    """Readiness probe used by load balancers and orchestrators."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).warning("readiness check failed: %s", exc.__class__.__name__)
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "ok"}
