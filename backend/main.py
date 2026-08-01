from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import create_db_tables
from backend.routers import auth, rides, cluster, route, vehicle, predict, tracking, notifications
from backend.routers import analytics
from backend.routers import jobs
from backend.services.background_jobs import start_background_jobs, stop_background_jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_tables()
    # Startup: launch GPS simulation background task
    tracking.start_simulation()
    start_background_jobs()
    yield
    # Shutdown: nothing special needed
    await stop_background_jobs()


app = FastAPI(title="SmartRouteAI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(rides.router, prefix="/rides", tags=["Rides"])
app.include_router(cluster.router, prefix="/cluster", tags=["Cluster"])
app.include_router(route.router, prefix="/route", tags=["Route"])
app.include_router(vehicle.router, prefix="/vehicle", tags=["Vehicle"])
app.include_router(predict.router, prefix="/predict", tags=["Predict"])
app.include_router(tracking.router, tags=["Tracking"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])


@app.get("/")
def root():
    return {"message": "SmartRouteAI API is running"}
