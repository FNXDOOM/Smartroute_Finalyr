# System Design

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        CLIENTS                               │
│   Passenger App    Driver App    Admin Dashboard             │
│        │                │               │                    │
│        └────────────────┴───────────────┘                   │
│                         │                                    │
│              HTTP REST + WebSocket                           │
└─────────────────────────┼────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────┐
│                   FastAPI Backend                            │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   Auth   │  │  Rides   │  │ Cluster  │  │  Route   │   │
│  │  Router  │  │  Router  │  │  Router  │  │  Router  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Vehicle  │  │Tracking  │  │ Notif.   │  │Analytics │   │
│  │  Router  │  │  Router  │  │  Router  │  │  Router  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐                                 │
│  │ Predict  │  │  Jobs    │                                 │
│  │  Router  │  │  Router  │                                 │
│  └──────────┘  └──────────┘                                 │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Background Job Scheduler                 │  │
│  │  cluster(60s)  demand(300s)  rebalance(300s)  sim(5s) │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │          WebSocket Broadcast Loop (2s)                │  │
│  └───────────────────────────────────────────────────────┘  │
└────────────────────────────┬─────────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │ Supabase PostgreSQL + PostGIS │
              │ (SQLite only if configured)   │
              │   12 tables                 │
              └─────────────────────────────┘
```

## Frontend Mapping

The web application uses MapLibre GL. Production deployments should provide a
Stadia Maps or MapTiler vector style/key; local development falls back to
CARTO raster tiles. Address search supports MapTiler or Stadia autocomplete,
with Photon as a keyless development fallback.

Map data flows through the FastAPI backend:

- `/tracking/feed` supplies vehicle locations and recent tracking events.
- `/tracking/ws?token=<jwt>` supplies scoped live vehicle snapshots: admins see
  the fleet, drivers see their assigned vehicle, and passengers see only a
  vehicle assigned to one of their active rides.
- `/predict/heatmap` supplies demand cells rendered as map circles.
- Ride pickup and destination coordinates are rendered as markers and a route
  line after the ride form resolves addresses through the configured geocoder.

---

## Core Data Flow — Ride to Dispatch

This is the full lifecycle of a passenger ride from request to completion.

```
1. PASSENGER SUBMITS RIDE
   POST /rides/request
        │
        ▼
   RideRequest saved (status = "pending")
   H3 index computed from pickup coords
   Notification fired → passenger

2. CLUSTERING (every 60s auto, or manual POST /cluster/run)
        │
        ▼
   Fetch all pending rides
        │
        ▼
   H3 Partitioner
   → groups rides by hexagonal cell (resolution 9)
        │
        ▼
   HDBSCAN Clusterer (per H3 bucket)
   → groups nearby passengers within each cell
   → noise points (isolated riders) marked with label -1
        │
        ▼
   For each cluster:
     K-Medoids → picks best pickup point among cluster members
     OSMnx     → downloads road graph around centroid (2.5km radius)
     snap_to_road → moves pickup point to nearest drivable road node
        │
        ▼
   VirtualStop saved (snapped lat/lng, cluster_id, passenger_count)
   RideRequests updated (status = "clustered", virtual_stop_id set)
   ClusterRun saved (audit record with cluster_summary JSON)

3. ROUTE OPTIMIZATION (manual POST /route/optimize)
        │
        ▼
   Select vehicle_ids + virtual_stop_ids
        │
        ▼
   Build distance matrix (haversine between all stops)
        │
        ▼
   OR-Tools CVRP Solver
   → respects vehicle capacities
   → assigns stop sequences to minimize total distance
   → 10 second time limit
        │
        ▼
   For each route solution:
     RoutePlan saved (route_id, vehicle_id, distance, duration, metadata)
     RouteWaypointRecords saved (ordered stop sequence)
     Vehicle updated (assigned_route_id, status = "active")
     Notifications fired → all passengers on that route

4. VEHICLE ASSIGNMENT (manual POST /vehicle/assign)
        │
        ▼
   Fetch idle vehicles + route candidates
        │
        ▼
   Build cost matrix (haversine: vehicle current pos → route depot)
        │
        ▼
   Hungarian Algorithm (scipy.optimize.linear_sum_assignment)
   → globally optimal one-to-one assignment
        │
        ▼
   Vehicles updated (assigned_route_id, status = "active")

5. LIVE TRACKING (POST /tracking/vehicles/{id}/location)
        │
        ▼
   Vehicle lat/lng updated
   TrackingEvent saved
   Notifications fired → all passengers on vehicle's route
   Scoped WebSocket broadcast → each authorized client receives only permitted data

6. RIDE COMPLETION
   Status transitions: pending → clustered → assigned → arriving
                       → in_progress → completed
   Each transition fires a notification to the passenger
   Simulation job (every 5s) auto-advances rides for demo
```

---

## Demand Prediction Flow

```
Background job (every 300s) or GET /predict/demand
        │
        ▼
   For each active H3 zone:
        │
        ▼
   Count historical ride requests in zone (last N days)
        │
        ▼
   Feature engineering:
     hour          = reference_time.hour
     day_of_week   = reference_time.weekday()
     h3_zone       = abs(hash(h3_index)) % 10_000
     historical_count = DB count
     is_weekend    = 1 if day_of_week >= 5
        │
        ▼
   XGBoost model (ml/models/demand_model.pkl)
   → if no model file: heuristic fallback (time-of-day multipliers)
        │
        ▼
   DemandSnapshot saved (job_run_id, h3_index, predicted_demand)

   Results used by:
   → Vehicle rebalance job (move idle vehicles to high-demand zones)
   → GET /predict/heatmap (frontend map overlay)
```

---

## Vehicle Rebalancing Flow

```
Background job (every 300s) or POST /jobs/run/rebalance
        │
        ▼
   Fetch idle vehicles
        │
        ▼
   Count ride requests per H3 zone (last 30 days)
        │
        ▼
   For each zone → predict demand (XGBoost)
   Rank zones by predicted_demand (top 10)
        │
        ▼
   For each idle vehicle:
     Find nearest high-demand zone (haversine)
     Create VehicleRebalanceSuggestion record
        │
        ▼
   Frontend/admin can act on suggestions
   (suggestions are advisory — vehicles not moved automatically)
```

---

## Authentication Flow

```
Clerk sign-in/sign-up
        │
        ▼
   Clerk session JWT
        │
        ▼
   Client sends: Authorization: Bearer <token>
        │
        ▼
   get_current_user dependency:
     verify Clerk JWT → extract clerk_user_id
     load application profile and role
     query users table → return User ORM object
     if not found or expired → 401
```

---

## Component Dependency Map

```
routers/
  auth.py          → utils/auth_utils.py, models/user.py
  rides.py         → services/clustering/h3_partitioner.py
                     services/notifications.py
  cluster.py       → services/clustering/h3_partitioner.py
                     services/clustering/hdbscan_clusterer.py
                     services/stops/virtual_stop_generator.py
                     services/stops/road_snapper.py
  route.py         → services/routing/vrp_solver.py
                     services/notifications.py
  vehicle.py       → services/assignment/hungarian_assigner.py
                     utils/geo.py
  tracking.py      → services/notifications.py
                     utils/auth_utils.py (WebSocket JWT)
  notifications.py → services/notifications.py
                     utils/auth_utils.py (WebSocket JWT)
  analytics.py     → utils/geo.py
  predict.py       → services/prediction/demand_model.py
                     services/prediction/feature_engineering.py
                     services/clustering/h3_partitioner.py
  jobs.py          → services/background_jobs.py

services/
  background_jobs.py → ALL clustering, prediction, routing services
  notifications.py   → models/notification.py (WebSocket manager)
  clustering/
    h3_partitioner.py    → h3 library
    hdbscan_clusterer.py → hdbscan / sklearn.DBSCAN, utils/geo.py
  stops/
    virtual_stop_generator.py → sklearn_extra.KMedoids
    road_snapper.py            → osmnx
  routing/
    vrp_solver.py    → ortools, utils/geo.py
    astar_router.py  → osmnx, networkx
  assignment/
    hungarian_assigner.py → scipy.optimize
  prediction/
    demand_model.py       → xgboost, ml/models/demand_model.pkl
    feature_engineering.py → h3_partitioner.py

utils/
   auth_utils.py → Clerk JWKS, PyJWT, config.py
  geo.py        → math (no external deps)
```

---

## CORS and Security

- `ALLOWED_ORIGINS` env var controls which frontend origins are permitted
- Credentials (`Authorization` headers) are allowed only for listed origins
- Wildcard `*` with credentials is intentionally blocked (browser would reject it)
- Clerk controls session expiration and token rotation
- FastAPI validates Clerk issuer, signature, and optional audience
- Passwords are managed by Clerk; FastAPI verifies Clerk session JWTs
- Admin role cannot be self-assigned at registration — requires promotion by existing admin via `PATCH /auth/users/{id}/role`
