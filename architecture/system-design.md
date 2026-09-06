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

The web application uses MapLibre GL with a Stadia-only vector style served through the authenticated FastAPI proxy. There is no tile fallback.

Map data flows through the FastAPI backend (all require Clerk JWT; all geo endpoints reject points outside India via `is_india_location`):

- `/maps/stadia/style.json` + `/maps/stadia/resource/*` supply the Stadia style/tiles/sprites with the server-side `api_key` stripped and rewritten to the proxy prefix (prevents key leakage to the browser)
- `/geocode/suggest|search|reverse` supply Stadia autocomplete/forward/reverse geocoding (India-filtered)
- `/routing/route|nearest-road|map-match|matrix` supply Stadia road routing, snapping, map matching, and ≤25×25 cost matrices
- `/tracking/feed` supplies vehicle locations and recent tracking events.
- `/tracking/ws` with the `bearer` WebSocket subprotocol supplies scoped live vehicle snapshots: admins see
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

3. ROUTE OPTIMIZATION (manual POST /route/optimize, or POST /jobs/run/auto-dispatch)
         │
         ▼
    Select vehicle_ids + virtual_stop_ids (live scope; drivers are scoped to their own driver_user_id vehicles)
         │
         ▼
    Build distance matrix — 3-tier cascade in vrp_solver.py:
      1) Stadia road matrix (sources/targets ≤25 each)
      2) local OSM road graph (Dijkstra over build_road_graph radius)
      3) haversine fallback (always available)
         │
         ▼
    OR-Tools CVRP Solver (per-vehicle capacities, PATH_CHEAPEST_ARC + GUIDED_LOCAL_SEARCH, 10 s limit)
    → respects vehicle capacities
    → assigns stop sequences to minimize total distance
         │
         ▼
    Best-effort geometry enrichment via Stadia route_many (routing_provider = "stadia" | "local-road-matrix")
         │
         ▼
    For each route solution:
      RoutePlan saved (route_id, vehicle_id, distance, duration, metadata + geometry/maneuvers)
      RouteWaypointRecords saved (ordered stop sequence)
      Vehicle updated (assigned_route_id, status = "active")
      RideRequests updated (status = "assigned")
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
    pending → clustered happens in clustering / auto-dispatch only.
    clustered → assigned happens in route optimization / auto-dispatch only.
    assigned → arriving → in_progress → completed is driven by the simulation job (every 5s, live + demo scopes; completes a demo ride in ~25 s) and by driver Start/Arriving/Complete buttons.
    Each transition fires a notification to the passenger.
    Live and presentation_demo rows are isolated by ride_mode + demo_run_id (see alembic 0002_demo_scope); live queries default to mode=live.
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
  auth.py          → utils/auth_utils.py, models/user.py, services/clerk_service.py
  rides.py         → services/clustering/h3_partitioner.py
                     services/notifications.py, utils/ride_scope.py, utils/geo.py (India guard)
  cluster.py       → services/clustering/h3_partitioner.py
                     services/clustering/hdbscan_clusterer.py
                     services/stops/virtual_stop_generator.py
                     services/stops/road_snapper.py
  route.py         → services/routing/vrp_solver.py (Stadia → OSM → haversine)
                     services/stadia_client.py (route_many geometry)
                     services/notifications.py
  vehicle.py       → services/assignment/hungarian_assigner.py
                     utils/geo.py
  routing.py       → services/stadia_client.py (route/matrix/nearest_roads/map_match)
                     utils/geo.py (India guard)
  geocode.py       → services/stadia_client.py (autocomplete/forward/reverse)
                     utils/geo.py (India guard)
  maps.py          → services/stadia_client.py (style/tiles proxy, api_key stripping)
                     utils/auth_utils.py (auth required for tiles)
  tracking.py      → services/notifications.py
                     utils/auth_utils.py (WebSocket JWT)
  notifications.py → services/notifications.py
                     utils/auth_utils.py (WebSocket JWT)
  analytics.py     → utils/geo.py
  predict.py       → services/prediction/demand_model.py
                     services/prediction/feature_engineering.py
                     services/clustering/h3_partitioner.py
  jobs.py          → services/background_jobs.py (cluster/demand/rebalance/simulate/auto-dispatch)

services/
  background_jobs.py → ALL clustering, prediction, routing services + ride_scope
  stadia_client.py   → config.py Stadia URLs/key (server-side only, never VITE_*)
  clerk_service.py   → CLERK_SECRET_KEY publicMetadata sync
  notifications.py   → models/notification.py (WebSocket manager)
  clustering/
    h3_partitioner.py    → h3 library
    hdbscan_clusterer.py → hdbscan / sklearn.DBSCAN, utils/geo.py
  stops/
    virtual_stop_generator.py → sklearn_extra.KMedoids
    road_snapper.py            → osmnx
  routing/
    vrp_solver.py    → ortools, services/stadia_client.py, utils/geo.py
    astar_router.py  → osmnx, networkx (implemented, unused by pipeline)
  assignment/
    hungarian_assigner.py → scipy.optimize
  prediction/
    demand_model.py       → xgboost, ml/models/demand_model.pkl
    feature_engineering.py → h3_partitioner.py

utils/
   auth_utils.py → Clerk JWKS, PyJWT, config.py (get_current_user, require_roles, get_websocket_token bearer only)
  geo.py        → math (haversine_meters) + INDIA_BOUNDS guard (no external deps)
  ride_scope.py → LIVE_MODE / PRESENTATION_DEMO_MODE, apply_ride_scope / validate_ride_mode
```

---

## CORS and Security

- `ALLOWED_ORIGINS` env var controls which frontend origins are permitted (production must be the public `https://` domain, not localhost)
- `CLERK_AUTHORIZED_PARTIES` must match the same public domain for Clerk session validation
- Credentials (`Authorization` headers) are allowed only for listed origins
- Wildcard `*` with credentials is intentionally blocked (browser would reject it)
- Clerk controls session expiration and token rotation; `CLERK_ALLOW_NATIVE_CLIENTS` gates native-client tokens
- FastAPI validates Clerk issuer, signature, and optional audience
- Passwords are managed by Clerk; FastAPI verifies Clerk session JWTs; `CLERK_SECRET_KEY` (not in `.env.example` — add it to enable real-time `publicMetadata` sync) keeps DB role + Clerk metadata in sync
- WebSocket auth uses the `bearer` subprotocol only — `?token=` query params and cookies are rejected (see `get_websocket_token`, tested in `tests/test_health_and_ws_auth.py`)
- All map/geocode/routing traffic goes through the authenticated Stadia proxy so the `STADIA_API_KEY` never reaches the browser (`VITE_*` must never contain secrets)
- All geo writes are India-guarded server-side (`utils/geo.py:is_india_location`)
- Admin role cannot be self-assigned at registration — requires promotion by existing admin via `PATCH /auth/users/{id}/role`
