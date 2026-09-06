# SmartRouteAI — Architecture Documentation

This folder contains detailed technical documentation for every layer of the SmartRouteAI system.

---

## Quick Navigation

| File | What it covers |
|---|---|
| [system-design.md](./system-design.md) | How every component connects — full data flow from passenger request to vehicle dispatch |
| [api-reference.md](./api-reference.md) | Every endpoint — method, path, auth, request body, response shape, status codes |
| [db-schema.md](./db-schema.md) | All 12 database tables — columns, types, constraints, indexes, foreign keys, relationships |
| [algorithms.md](./algorithms.md) | How each AI/optimization algorithm works and where it fits in the pipeline |
| [background-jobs.md](./background-jobs.md) | The 4 background workers — what they do, when they run, what they write |
| [websockets.md](./websockets.md) | Real-time WebSocket channels — connection, authentication, message formats |
| [supabase.md](./supabase.md) | Supabase setup, PostgreSQL migration, Auth, RLS, environment variables, and deployment |

---

## System Overview at a Glance

```
Passenger App / Driver App / Admin Dashboard
              ↓  HTTP + WebSocket
         FastAPI Backend (Python 3.10)
              ↓
    ┌──────────────────────────────────────────────┐
    │  H3 Spatial Partitioning                     │  groups ride requests by hex cell
    │  HDBSCAN Clustering                          │  finds passenger groups within cells
    │  K-Medoids Stop Selection                    │  picks optimal pickup point per group
    │  OSMnx Road Snapping                         │  moves pickup point onto nearest road
    │  OR-Tools VRP Solver                         │  assigns stop sequences to vehicles
    │  Hungarian Assignment                        │  matches idle vehicles to routes
    │  XGBoost Demand Predictor                    │  forecasts future ride demand by zone
    └──────────────────────────────────────────────┘
              ↓
    Supabase PostgreSQL + PostGIS  (SQLite only for local development)
```

### Request → Dispatch Flow

1. **Passenger Books Ride** → `POST /rides/request`
2. **RideRequest stored** with `status=pending`
3. **[Every 60s] Clustering Job** → Groups pending rides into virtual stops
4. **[Admin or auto trigger] VRP Optimization** → Assigns ride groups to vehicles with waypoint sequences
5. **Hungarian Assignment** → Matches idle drivers to optimized routes
6. **[Every 5s] Simulation Job** → Auto-advances ride status (arriving → in_progress → completed)
7. **WebSocket Broadcast** → Notifies passengers of vehicle arrival + tracking updates
8. **Ride Completion** → Marks route as completed, vehicle becomes idle

---

## Key Design Decisions

### Why Separate Processes for API and Worker?

- **API (`uvicorn main:app`)**: Handles HTTP requests and WebSocket connections; optimized for request latency
- **Worker (`python worker.py`)**: Runs scheduled jobs (clustering, demand prediction, rebalancing) in the background; no HTTP overhead
- This separation allows scaling independently: add more API instances behind a load balancer while keeping a single worker

### Why HDBSCAN?

- Unlike K-Means, HDBSCAN doesn't require pre-specifying the number of clusters
- Handles variable-density clusters (dense urban areas vs. sparse suburbs)
- Identifies "noise" points (outlier ride requests) that don't cluster well
- Pairs well with spatial partitioning (H3) to limit clustering scope

### Why H3 Spatial Grid?

- Divides Bengaluru into hexagonal cells at a fixed resolution (res=9 ≈ 0.105 km² per cell, ~200 m across)
- Clustering only happens within a cell (or adjacent cells), reducing computational cost
- Enables efficient demand prediction (one prediction per H3 cell)
- Makes caching and incremental updates easier

### Why OR-Tools CVRP Solver?

- Google's production-grade solver handles complex constraints (vehicle capacity, time windows, etc.)
- Significantly better routes than greedy algorithms
- Distance matrix is 3-tier: Stadia road matrix (≤25×25) → local OSM road graph (Dijkstra) → haversine fallback (`backend/services/routing/vrp_solver.py`)
- Reasonable solve time for our fleet size (10 s hard limit via `GUIDED_LOCAL_SEARCH` + `PATH_CHEAPEST_ARC`)
- Alternative: Local search (LKH) or Genetic Algorithms, but those have longer solve times

### Why Hungarian Algorithm for Vehicle Assignment?

- Optimal matching between idle vehicles and waiting routes (1:1 assignment)
- O(n³) complexity is acceptable for small fleets (< 100 vehicles)
- Ensures vehicles are assigned fairly and never left idle if a route is waiting

---

## Tech Stack Summary

| Layer | Technology | Why? |
|---|---|---|
| API framework | FastAPI 0.104 | Fast, async-native, built-in WebSocket support, auto-generated docs |
| ORM | SQLAlchemy 2.0 | Type-safe, powerful query builder, works with any SQL dialect |
| Schema validation | Pydantic v2 | Fast, automatic OpenAPI docs, strong typing |
| Database (prod) | Supabase PostgreSQL + PostGIS | Managed PostgreSQL, geospatial queries, built-in auth |
| Database (dev) | SQLite only when explicitly configured | No external dependencies for local development |
| Auth | Clerk session JWTs (RS256) | Industry standard, JWT verification without hitting Clerk on every request |
| Spatial indexing | H3 (Uber) res=9 | Hierarchical hexagonal grid for efficient partitioning |
| Clustering | HDBSCAN | Density-based, finds variable-density clusters, no K specification needed |
| Stop placement | scikit-learn-extra K-Medoids | Picks an actual point (from data) vs. K-Means' arbitrary centroid |
| Road snapping | OSMnx + NetworkX | Snaps pickups to nearest road, handles complex street networks |
| Route optimization | Google OR-Tools (CVRP) | Industry-standard VRP solver, fast and reliable |
| Vehicle assignment | SciPy Hungarian algorithm | Optimal 1:1 matching between vehicles and routes |
| Demand prediction | XGBoost regressor | Fast inference, handles seasonal patterns + holidays |
| Real-time | WebSockets via Starlette | Full-duplex, low latency, multiple subprotocol support |
| Frontend | React 19 + Vite | Fast build, HMR, modern JSX, excellent dev experience |
| Map library | MapLibre GL | Open-source, vector tiles, lightweight |
| Map tiles & routing | Stadia/Stadia routing | Commercial service, fast & reliable; always behind backend proxy |

---

## Data Flow Examples

### Passenger Booking a Ride

```
1. User opens map on passenger app
2. FE: User clicks "Book Ride" → Selects destination → Chooses tier (SwiftX, SwiftXL, Lux Black, Moto)
3. FE: POST /rides/request { pickup_lat, pickup_lng, dest_lat, dest_lng, pickup_label, destination_label, ride_option_* }
4. BE: Validate Clerk token → resolve user_id; reject points outside India (`is_india_location`)
5. BE: Create RideRequest record { status='pending', mode='live', user_id, h3_index (res 9) }
6. BE: Broadcast notification via /notifications/ws to passenger: "Ride booking confirmed, waiting for vehicle assignment"
7. BE: Return response with ride_id to FE
8. [Repeat every 5s] FE polls GET /rides/my-rides (live mode only) or subscribes to /notifications/ws for status updates
9. [Every 60s] Worker runs clustering job (live scope)
   → Finds all pending rides in passenger's H3 cell
   → Runs HDBSCAN to group nearby passengers
   → Creates VirtualStop + ClusterRun records { status='clustered' }
   → Updates RideRequest.status='clustered', virtual_stop_id=X
10. [Admin/driver trigger POST /route/optimize, or POST /jobs/run/auto-dispatch] Worker runs VRP optimization
    → Reads all clustered rides in live scope
    → Builds distance matrix (Stadia ≤25×25 → OSM Dijkstra → haversine fallback)
    → Calls OR-Tools solver with per-vehicle capacities
    → Creates RoutePlan + RouteWaypoint records (geometry via Stadia `route_many` when configured)
    → Assigns RideRequest.status='assigned'
11. [Hungarian assignment] Matches idle vehicles to routes (drivers only see/optimise their own `driver_user_id` vehicles)
    → Updates Vehicle.assigned_route_id = route_id, status='active'
12. [Every 5s] Simulation advances assigned → arriving → in_progress → completed (pending/clustered are NOT touched by sim job)
    → Vehicle.status = 'arriving' / returns to 'idle' when its stop completes
    → Broadcasts /tracking/ws update to passenger (vehicle location, ETA)
    → Eventually completes ride
13. FE: Passenger sees live vehicle tracking on map, arrival notification
```

> Live vs presentation data never mix: every dispatch table carries `ride_mode` (`live` | `presentation_demo`) + `demo_run_id`. Live endpoints default to `mode=live`; the isolated demo flow uses `PresentationDemoView.jsx` + `POST /rides/demo-batch` and `POST /jobs/run/auto-dispatch?mode=presentation_demo`.

### Admin Viewing Fleet Analytics

```
1. Admin navigates to Admin → Analytics
2. FE: GET /analytics/overview (fleet-wide aggregate, no date params)
3. BE: Query database for fleet stats:
   - Total ride requests (all statuses)
   - Total unique vehicles
   - Total clusters created
   - Average cluster size
   - Total routes planned
   - Fleet utilization %
4. BE: Return JSON { total_rides, total_vehicles, ... }
5. FE: Render overview metrics + bar chart
6. FE: GET /analytics/daily?days=14 (1–90) for per-day breakdown
7. BE: Group RideRequest by date, compute stats per day
8. FE: Render table + chart
```

### Driver Receiving Assignment

```
1. Driver is idle (Vehicle.status='idle', assigned_route_id=null)
2. [Hungarian assignment job] Matches driver's vehicle to a RoutePlan
3. BE: Updates Vehicle.assigned_route_id = route_123
4. BE: Broadcasts via /tracking/ws to all subscribed admins (fleet map updates)
5. [Every 5s] Simulation job reads the route and updates ride statuses
6. FE (Driver View): Driver is subscribed to /tracking/ws
   → Receives "Your vehicle is now assigned to route_123 with X waypoints"
   → Shows upcoming pickup/dropoff sequence on map
7. Driver hits "Start" button → Updates ride status to 'arriving'
8. BE: Broadcasts to passenger via /notifications/ws + /tracking/ws
9. BE: Broadcasts to admin (fleet utilization %)
```

---

## Common Patterns

### Adding a New Endpoint

1. Create a schema in `backend/schemas/` (request/response)
2. Add the route in `backend/routers/` (import schema, define handler)
3. Include proper auth (check token via `current_user` dependency)
4. Return meaningful status codes (201 for created, 400 for validation, 403 for forbidden)
5. Add to API docs at `GET /docs` (automatic via FastAPI)

### Running a Background Job

1. Define the job function in `backend/services/background_jobs.py` (e.g., `run_cluster_job()`, `run_auto_dispatch_pipeline()`)
2. Wire it into the asyncio scheduler (`start_background_jobs()` in the same file; intervals: cluster 60 s, demand 300 s, rebalance 300 s, sim 5 s) — jobs run in `backend/worker.py`, optionally in-API via `ENABLE_BACKGROUND_JOBS_IN_API=true` for single-process dev
3. Scope every query with `apply_ride_scope(query, mode, demo_run_id)` so `live` and `presentation_demo` never mix
4. Use `logger` for observability
5. Handle exceptions gracefully (rollback, mark `job_runs.status='failed'`, don't crash the worker)
6. Update relevant database records with results + write a `job_runs` audit row (`is_scheduled=False` for manual `POST /jobs/run/*` triggers)

### Broadcasting Real-Time Updates

1. Identify which WebSocket endpoint should receive the update (`/tracking/ws` for vehicle positions, `/notifications/ws` for ride status changes)
2. Collect the target audience (which user_ids should see this?) — tracking is scoped server-side (admin=fleet, driver=own vehicle, passenger=own ride vehicle); notifications are keyed by `user_id`
3. Use the managers: `ConnectionManager.broadcast()` in `backend/routers/tracking.py` and `NotificationConnectionManager` in `backend/services/notifications.py` (dead connections are pruned silently)
4. Frontend subscribes via `frontend/src/hooks/useWebSocket.js` / `services/api.js:createTrackingWS|createNotificationsWS` with `['bearer', clerkJwt]` subprotocol and handles the message (update state, show notification, etc.)

---

## File Organization

```
backend/
├── config.py                    # Settings (env vars, defaults; Stadia + Clerk + CORS)
├── database.py                  # SQLAlchemy engine + session factory + PortableGeometry + compat migrations
├── main.py                      # FastAPI app + CORS + security headers + lifespan (tracking broadcast loop)
├── worker.py                    # Dedicated asyncio worker (start_background_jobs loop)
├── seed.py                      # Demo data for development (see also scripts/seed_db.py)
│
├── models/                      # SQLAlchemy ORM models (12 tables)
│   ├── user.py, vehicle.py, ride_request.py, virtual_stop.py, cluster_run.py
│   ├── route_plan.py, route_waypoint.py, tracking_event.py, notification.py
│   ├── job_run.py, demand_snapshot.py, vehicle_rebalance_suggestion.py
│
├── routers/                     # API endpoints (one file per resource)
│   ├── auth.py, rides.py, cluster.py, route.py, vehicle.py
│   ├── tracking.py, notifications.py, analytics.py, predict.py, jobs.py
│   ├── routing.py, geocode.py, maps.py   # Stadia-backed road/geocode/tile proxy (India-only)
│
├── schemas/                     # Pydantic request/response validators
│   ├── user.py, ride_request.py, route.py, vehicle.py, virtual_stop.py
│   ├── cluster.py, tracking.py, notification.py, analytics.py, predict.py, jobs.py
│
├── services/                    # Business logic + algorithms
│   ├── background_jobs.py       # asyncio scheduler + run_cluster/demand/rebalance/simulate/auto-dispatch
│   ├── stadia_client.py         # Server-side Stadia/Valhalla client (geocode, route, matrix, tiles)
│   ├── clerk_service.py         # Clerk publicMetadata sync (requires CLERK_SECRET_KEY)
│   ├── clustering/
│   │   ├── h3_partitioner.py
│   │   └── hdbscan_clusterer.py
│   ├── routing/
│   │   ├── vrp_solver.py        # OR-Tools optimization (Stadia → OSM → haversine matrix, 10 s limit)
│   │   └── astar_router.py      # A* pathfinding (implemented, currently unused by pipeline)
│   ├── prediction/
│   │   ├── demand_model.py      # XGBoost loader (ml/models/demand_model.pkl + heuristic fallback)
│   │   └── feature_engineering.py
│   ├── assignment/
│   │   └── hungarian_assigner.py
│   ├── stops/
│   │   ├── virtual_stop_generator.py  # K-Medoids
│   │   └── road_snapper.py            # OSMnx snapping
│   └── notifications.py         # WebSocket broadcast helpers
│
├── utils/                       # Helpers
│   ├── auth_utils.py (Clerk JWKS verify, get_current_user, require_roles, WS bearer token)
│   ├── geo.py (haversine_meters, is_india_location 6.5–35.7 / 68.1–97.4)
│   ├── ride_scope.py (LIVE_MODE / PRESENTATION_DEMO_MODE, apply_ride_scope)
│
├── ../alembic/                  # Database migrations (project root)
│   ├── env.py
│   └── versions/
│       ├── 0001_initial_schema.py
│       └── 0002_separate_presentation_demo_runs.py  # ride_mode + demo_run_id
│
├── ../ml/models/demand_model.pkl
└── ../requirements.txt          # Project-root pip requirements
```

---

## Performance Considerations

### Clustering (HDBSCAN)
- Time complexity: O(n log n) to O(n²) depending on data
- For 1000 pending rides in a cell: ~100-500ms
- Limit to one H3 cell per job to keep predictable

### VRP Optimization (OR-Tools)
- Time: typically 100-500ms for 10-15 stops per route
- Timeout set to 10s (`params.time_limit.seconds = 10` in `vrp_solver.py`) to prevent long-running solves
- Matrix build order: Stadia (≤25×25) → OSM Dijkstra → haversine; geometry enrichment via Stadia `route_many` is best-effort only
- Quality degrades gracefully if timeout reached

### Road Snapping (OSMnx)
- First call loads the street network (~2-5s for Bengaluru)
- Subsequent calls use cached graph (~10-50ms per snap)
- Cache is in-memory; restart clears it

### Demand Prediction (XGBoost)
- Inference: ~1-5ms per H3 cell
- Runs every 300s for full grid (entire city)
- Total time: typically < 2 seconds for entire city

---

## Debugging Tips

1. **Enable verbose logging**: Set `LOG_LEVEL=DEBUG` in `.env`
2. **Inspect WebSocket traffic**: Use browser DevTools → Network → WS tabs
3. **Query database directly**: `psql -U postgres -d smartrouteai` or use Supabase dashboard
4. **Check async task queue**: Review `background_jobs.py` and worker logs
5. **Profile slow endpoints**: Add `@router.middleware()` with timing logic
6. **Test algorithms in isolation**: Use Jupyter notebooks in `ml/` folder with sample data
