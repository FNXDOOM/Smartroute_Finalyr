import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
import os

from database import create_db_tables
from routers import auth, rides, cluster, route, vehicle, predict, tracking, notifications
from routers import analytics
from routers import jobs
from services.background_jobs import start_background_jobs, stop_background_jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_tables()
    # Startup: launch GPS simulation background task
    tracking.start_simulation()
    start_background_jobs()
    yield
    # Shutdown
    await stop_background_jobs()


app = FastAPI(title="SmartRouteAI", version="1.0.0", lifespan=lifespan)

# CORS — wildcard origins are incompatible with allow_credentials=True.
# Read explicit origins from the environment; fall back to localhost dev only.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
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
        origins = allowed_origins
    except NameError:
        origins = []

    is_local_dev = any("localhost" in o or "127.0.0.1" in o for o in origins)
    if is_local_dev:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-eval' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline';"
        )
    return response

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(rides.router, prefix="/rides", tags=["Rides"])
app.include_router(cluster.router, prefix="/cluster", tags=["Cluster"])
app.include_router(route.router, prefix="/route", tags=["Route"])
app.include_router(vehicle.router, prefix="/vehicle", tags=["Vehicle"])
app.include_router(predict.router, prefix="/predict", tags=["Predict"])
app.include_router(tracking.router, prefix="/tracking", tags=["Tracking"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])


@app.get("/")
def root():
    return {"message": "SmartRouteAI API is running"}
