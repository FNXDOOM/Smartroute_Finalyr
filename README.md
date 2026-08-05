# SmartRouteAI

An AI-powered shared mobility optimization platform. It groups nearby passengers into clusters, generates virtual pickup stops on real road networks, solves vehicle routing problems, predicts zone-level demand, and streams live vehicle positions — all through a single FastAPI backend with a React frontend.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Algorithms](#algorithms)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running the Backend](#running-the-backend)
- [Running the Frontend](#running-the-frontend)
- [Training the Demand Model](#training-the-demand-model)
- [Seeding Demo Data](#seeding-demo-data)
- [API Overview](#api-overview)
- [Background Jobs](#background-jobs)
- [Database Tables](#database-tables)
- [WebSocket Endpoints](#websocket-endpoints)

---

## Features

- **Passenger clustering** — H3 spatial partitioning + HDBSCAN groups nearby ride requests into shared trips
- **Virtual stop generation** — K-Medoids picks representative pickup points, snapped to real road nodes via OSMnx
- **Route optimization** — Capacitated VRP solved with Google OR-Tools assigns stop sequences to vehicles
- **Vehicle assignment** — Hungarian algorithm optimally matches idle vehicles to routes by distance
- **Demand prediction** — XGBoost model forecasts ride demand per H3 zone per hour
- **Real-time tracking** — WebSocket feed broadcasts vehicle GPS positions every 2 seconds
- **Notifications** — Every ride, route, and tracking event fires a real-time push notification
- **Analytics** — Aggregated stats and per-day breakdowns across rides, routes, and vehicles
- **Background scheduler** — Auto-runs clustering (60s), demand refresh (300s), rebalancing (300s), and ride lifecycle simulation (5s)

---

## Tech Stack

**Backend**
- Python 3.10+, FastAPI, SQLAlchemy 2.0, Pydantic v2
- PostgreSQL + PostGIS (production) / SQLite (dev fallback)
- WebSockets via Starlette

**AI / Optimization**
- H3 — hexagonal spatial indexing
- HDBSCAN — density-based passenger clustering
- OR-Tools — Google's capacitated VRP solver
- XGBoost — gradient boosting demand forecaster
- OSMnx + NetworkX — OpenStreetMap road graph and snapping
- SciPy — Hungarian algorithm for vehicle assignment
- scikit-learn-extra — K-Medoids for virtual stop placement

**Frontend**
- React + Vite, React Leaflet, Tailwind CSS

---

## Algorithms

| Problem | Algorithm |
|---|---|
| Spatial partitioning | H3 hexagonal indexing (resolution 9) |
| Passenger clustering | HDBSCAN with haversine metric |
| Virtual stop placement | K-Medoids (falls back to centroid) |
| Road snapping | OSMnx nearest-node lookup |
| Route optimization | OR-Tools CVRP solver |
| Vehicle assignment | Hungarian algorithm (scipy) |
| Demand forecasting | XGBoost regressor |
| Shortest path | A* via NetworkX |

---

## Project Structure

```
finalyr_project/
├── .env.example                   # Environment variable template
├── requirements.txt               # Python dependencies
│
├── backend/
│   ├── main.py                    # FastAPI app, CORS, lifespan
│   ├── config.py                  # Env config — fails fast if SECRET_KEY missing
│   ├── database.py                # SQLAlchemy engine, session, PortableGeometry type
│   │
│   ├── models/                    # SQLAlchemy ORM models (12 tables)
│   │   ├── user.py
│   │   ├── ride_request.py
│   │   ├── vehicle.py
│   │   ├── virtual_stop.py
│   │   ├── cluster_run.py
│   │   ├── route_plan.py
│   │   ├── route_waypoint.py
│   │   ├── tracking_event.py
│   │   ├── notification.py
│   │   ├── job_run.py
│   │   ├── demand_snapshot.py
│   │   └── vehicle_rebalance_suggestion.py
│   │
│   ├── schemas/                   # Pydantic v2 request/response schemas
│   │   ├── user.py
│   │   ├── ride_request.py
│   │   ├── vehicle.py
│   │   ├── cluster.py
│   │   ├── route.py
│   │   ├── tracking.py
│   │   ├── notification.py
│   │   ├── analytics.py
│   │   ├── predict.py
│   │   ├── jobs.py
│   │   └── virtual_stop.py
│   │
│   ├── routers/                   # API route handlers
│   │   ├── auth.py                # Register, login, profile, role management
│   │   ├── rides.py               # Ride request CRUD
│   │   ├── cluster.py             # Trigger clustering, view history
│   │   ├── route.py               # VRP optimization, route history
│   │   ├── vehicle.py             # Vehicle CRUD, assignment
│   │   ├── tracking.py            # GPS updates, live feed, WebSocket
│   │   ├── notifications.py       # Notification list, mark read, WebSocket
│   │   ├── analytics.py           # Overview and daily stats
│   │   ├── predict.py             # Demand prediction, heatmap
│   │   └── jobs.py                # Background job status and manual triggers
│   │
│   ├── services/
│   │   ├── background_jobs.py     # Async scheduler — clustering, demand, rebalance, dispatch sim
│   │   ├── notifications.py       # Notification creation + WebSocket broadcast
│   │   │
│   │   ├── clustering/
│   │   │   ├── h3_partitioner.py      # H3 spatial bucketing
│   │   │   └── hdbscan_clusterer.py   # HDBSCAN grouping
│   │   │
│   │   ├── stops/
│   │   │   ├── virtual_stop_generator.py  # K-Medoids stop selection
│   │   │   └── road_snapper.py            # OSMnx road snapping
│   │   │
│   │   ├── routing/
│   │   │   ├── vrp_solver.py          # OR-Tools CVRP
│   │   │   └── astar_router.py        # A* path finding
│   │   │
│   │   ├── assignment/
│   │   │   └── hungarian_assigner.py  # Vehicle-to-route matching
│   │   │
│   │   └── prediction/
│   │       ├── demand_model.py        # XGBoost load + predict + fallback heuristic
│   │       └── feature_engineering.py # Feature building and H3 encoding
│   │
│   └── utils/
│       ├── auth_utils.py          # bcrypt hashing, JWT create/decode, FastAPI deps
│       └── geo.py                 # Shared haversine_meters utility
│
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.jsx
│       └── ...
│
├── ml/
│   └── models/
│       └── demand_model.pkl       # Trained XGBoost model (generated by train script)
│
└── scripts/
    ├── seed_db.py                         # Populate DB with realistic demo data
    ├── train_demand_model_synthetic.py    # Train XGBoost on synthetic demand data
    ├── test_auth.py
    ├── test_rides.py
    └── test_models_schemas.py
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ with PostGIS (or use the SQLite dev fallback)

### Clone and install

```bash
git clone https://github.com/FNXDOOM/Smartroute_Finalyr.git
cd Smartroute_Finalyr

pip install -r requirements.txt
```

---

## Environment Variables

Copy the template and fill in your values:

```bash
cp .env.example .env
```

```env
# PostgreSQL connection (app falls back to SQLite if this fails)
DATABASE_URL=postgresql://postgres:password@localhost:5432/smartrouteai

# Required — generate with: python -c "import secrets; print(secrets.token_hex(32))"
# Server will refuse to start if this is empty
SECRET_KEY=replace-with-a-strong-random-secret

ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Comma-separated allowed frontend origins for CORS
ALLOWED_ORIGINS=http://localhost:5173
```

---

## Running the Backend

```bash
uvicorn backend.main:app --reload
```

The API will be at `http://localhost:8000`  
Interactive docs at `http://localhost:8000/docs`

On startup the app:
1. Creates all DB tables (`CREATE TABLE IF NOT EXISTS`)
2. Starts the WebSocket live-tracking broadcast loop
3. Launches 4 background job workers

---

## Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`

---

## Training the Demand Model

The demand prediction endpoints work out of the box using a heuristic fallback. To use the trained XGBoost model instead:

```bash
python scripts/train_demand_model_synthetic.py
```

This generates 172,800 rows of realistic synthetic demand data (rush hours, weekends, spatial hotspots), trains an XGBoost regressor, and saves the model to `ml/models/demand_model.pkl`.

The backend loads the model automatically on the first prediction request — no restart needed.

---

## Seeding Demo Data

Populate the database with users, vehicles, ride requests, clusters, routes, and tracking events:

```bash
# Seed with Dubai coordinates (default)
python scripts/seed_db.py

# Seed a different city
python scripts/seed_db.py --city bengaluru

# Drop all tables and re-seed fresh
python scripts/seed_db.py --reset

# Available cities: bengaluru, new_york, london
```

Default accounts created:

| Role | Email | Password |
|---|---|---|
| Admin | admin@smartrouteai.local | admin1234 |
| Driver | driver1@smartrouteai.local | driver1234 |
| Passenger | passenger1@smartrouteai.local | passenger1234 |

---

## API Overview

All protected routes require `Authorization: Bearer <token>`.

### Auth `/auth`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register — role limited to `passenger` or `driver` |
| POST | `/auth/login` | Login, returns JWT |
| POST | `/auth/token` | Swagger UI form login |
| GET | `/auth/me` | Get own profile |
| PATCH | `/auth/me` | Update name, email, phone |
| PATCH | `/auth/users/{id}/role` | Change user role (admin only) |

### Rides `/rides`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/rides/request` | Submit a ride request |
| GET | `/rides/my-rides` | My ride history |
| GET | `/rides/{id}` | Get ride by ID |
| GET | `/rides/` | List all rides (admin/driver) |
| PATCH | `/rides/{id}/status` | Update ride status |
| DELETE | `/rides/{id}` | Cancel a ride |

### Clustering `/cluster`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/cluster/run` | Trigger HDBSCAN clustering on pending rides |
| GET | `/cluster/history` | List past cluster runs |
| GET | `/cluster/history/{id}` | Get cluster run detail |

### Route Optimization `/route`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/route/optimize` | Run CVRP on virtual stops |
| GET | `/route/history` | List route plans |
| GET | `/route/history/{route_id}` | Get route plan + waypoints |

### Vehicles `/vehicle`
| Method | Endpoint | Description |
|---|---|---|
| GET | `/vehicle/` | List all vehicles |
| GET | `/vehicle/idle` | List idle vehicles |
| POST | `/vehicle/` | Create vehicle (admin) |
| PATCH | `/vehicle/{id}` | Update vehicle status/location |
| POST | `/vehicle/assign` | Hungarian assignment of vehicles to routes |

### Tracking `/tracking`
| Method | Endpoint | Description |
|---|---|---|
| GET | `/tracking/feed` | Vehicle snapshot + recent events |
| GET | `/tracking/events` | Raw tracking event list |
| POST | `/tracking/vehicles/{id}/location` | Push GPS update, broadcasts to WebSocket |

### Notifications `/notifications`
| Method | Endpoint | Description |
|---|---|---|
| GET | `/notifications/` | List notifications |
| GET | `/notifications/unread-count` | Count unread |
| PATCH | `/notifications/{id}/read` | Mark one as read |
| PATCH | `/notifications/read-all` | Mark all as read |

### Demand Prediction `/predict`
| Method | Endpoint | Description |
|---|---|---|
| GET | `/predict/demand` | Predict demand for a lat/lng point |
| GET | `/predict/heatmap` | Demand heatmap for a bounding box |

### Analytics `/analytics`
| Method | Endpoint | Description |
|---|---|---|
| GET | `/analytics/overview` | System-wide aggregated stats |
| GET | `/analytics/daily` | Per-day breakdown (up to 90 days) |

### Background Jobs `/jobs`
| Method | Endpoint | Description |
|---|---|---|
| GET | `/jobs/status` | Scheduler state and last run times |
| GET | `/jobs/runs` | Job execution history |
| GET | `/jobs/demand-snapshots` | Demand prediction snapshots |
| GET | `/jobs/rebalance-suggestions` | Vehicle rebalancing suggestions |
| POST | `/jobs/run/clustering` | Trigger cluster job manually |
| POST | `/jobs/run/demand` | Trigger demand job manually |
| POST | `/jobs/run/rebalance` | Trigger rebalance job manually |

---

## Background Jobs

Four jobs run automatically on startup:

| Job | Interval | What it does |
|---|---|---|
| `cluster_pending_rides` | every 60s | HDBSCAN clusters all pending rides |
| `refresh_demand_snapshots` | every 300s | Predicts demand per active H3 zone |
| `rebalance_idle_vehicles` | every 300s | Suggests idle vehicle repositioning |
| `simulate_ride_dispatch` | every 5s | Advances ride lifecycle for demo |

All jobs write to `job_runs` for audit, and can be triggered manually via `/jobs/run/*`.

---

## Database Tables

| Table | Purpose |
|---|---|
| `users` | Accounts (passenger, driver, admin) |
| `ride_requests` | Individual ride requests with GPS + status |
| `virtual_stops` | Clustered pickup points snapped to roads |
| `cluster_runs` | HDBSCAN run history and summaries |
| `route_plans` | Optimized vehicle routes |
| `route_waypoints` | Ordered stop sequence per route |
| `vehicles` | Fleet — location, capacity, status |
| `tracking_events` | GPS event log per vehicle |
| `notifications` | Per-user push notification inbox |
| `job_runs` | Background job audit log |
| `demand_snapshots` | Predicted demand per H3 zone |
| `vehicle_rebalance_suggestions` | Recommended repositioning targets |

---

## WebSocket Endpoints

Both require `?token=<jwt>` query parameter for authentication.

| Endpoint | Broadcast |
|---|---|
| `ws://localhost:8000/tracking/ws?token=<jwt>` | Vehicle positions + events every 2s |
| `ws://localhost:8000/notifications/ws?token=<jwt>` | Real-time notification push |

---

## License

Apache 2.0 — free to use, modify, and distribute.
