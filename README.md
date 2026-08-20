# SmartRoute AI

An Uber-like AI-powered shared ride dispatch system built for Bengaluru. Uses HDBSCAN clustering, OR-Tools VRP optimization, and Hungarian assignment to pre-compute optimized multi-passenger routes before dispatch.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19 + Vite, MapLibre GL, Clerk (auth) |
| Backend | FastAPI (Python), SQLAlchemy, PostgreSQL (Supabase) |
| Auth | Clerk (JWT RS256 via JWKS) |
| Algorithms | HDBSCAN clustering, OR-Tools CVRP, Hungarian algorithm (scipy), H3 spatial indexing |
| ML | XGBoost demand model (heuristic fallback if model file absent) |
| Maps | Stadia/MapTiler vector maps via MapLibre, CARTO fallback, OSMnx road graph for stop snapping |
| Real-time | WebSockets (FastAPI) for live vehicle tracking + per-user notifications |

---

## Running the Project

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Requires `backend/.env` — copy `backend/.env.example` and fill in the values.
`DATABASE_URL` is required; the backend no longer uses a built-in database
credential fallback.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Requires `frontend/.env` with:
```
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_STADIA_API_KEY=your_stadia_key
VITE_GEOCODER_PROVIDER=stadia
VITE_ROUTER_URL=https://api.stadiamaps.com/route/v1
VITE_ROUTER_ENGINE=valhalla
```

Stadia hosts the Valhalla routing engine, so Valhalla does not need to be
installed or maintained on the VPS. The frontend sends route validation and
ETA requests to Stadia using `VITE_STADIA_API_KEY`. Restrict the Stadia key to
your production domains because `VITE_*` values are visible in the browser.

For local development, the map can also use the Photon geocoder and CARTO
raster fallback. For production, configure Stadia or MapTiler using
[`frontend/.env.example`](frontend/.env.example).

### Seed the database (first run)

```bash
cd backend
python seed.py          # insert demo data
python seed.py --reset  # wipe and re-seed
```

---

## What Works Right Now ✅

### Authentication
- Clerk sign-up / sign-in with JWT verification on every backend request
- Auto-provisions a DB user on first login (role = `passenger` by default)
- Role-based access control: `passenger`, `driver`, `admin`
- WebSocket auth via `?token=<jwt>` query param

### Passenger
- Book a ride — creates a `RideRequest` in DB, fires notification
- Select ride tier (SwiftX, SwiftXL, Lux Black, Moto) with flat fare display
- Cancel pending/clustered rides
- Trip history with status badges
- Live tracking map — polls vehicle GPS every 5 seconds
- Trip detail view showing assigned vehicle, cluster ID, H3 cell

### Driver
- Dashboard with fleet stats pulled from real DB
- Drivers only see and update vehicles assigned to their application user; admins assign a vehicle with `PATCH /vehicle/{id}` and `{ "driver_user_id": <driver-user-id> }`
- Live fleet map — WebSocket connection to `/tracking/ws`, updates every 2 seconds
- Push own GPS location to backend (uses device geolocation, falls back to simulated coords)
- View and manage assigned rides — Start / Arriving / Complete buttons
- Route waypoint detail with map overlay showing optimized stops

### Admin (8 panels)
- **Overview** — real-time stats: total rides, vehicles, clusters, routes, utilisation %
- **Rides** — list all rides with status filter, manually advance any ride through the pipeline
- **Fleet** — create vehicles, set idle/active/offline, view GPS positions
- **Cluster** — run HDBSCAN clustering on pending rides, view run history with summaries
- **Routes** — run OR-Tools VRP optimization, view waypoint maps for each route
- **Analytics** — daily bar chart + table (7/14/30 day), overview metrics
- **Jobs** — scheduler status, manual trigger for clustering/demand/rebalance jobs, run history
- **Heatmap** — demand prediction heatmap on a MapLibre map using H3 cells

### Background Jobs (auto-run on backend startup)
- Clustering every 60 seconds — groups `pending` rides into virtual stops via HDBSCAN
- Demand refresh every 300 seconds — updates DemandSnapshot table with XGBoost/heuristic predictions
- Fleet rebalance every 300 seconds — generates VehicleRebalanceSuggestion records
- **Ride simulation every 5 seconds** — automatically advances active rides through the status pipeline (`pending → assigned → arriving → in_progress → completed`) and pushes WebSocket notifications — this is what makes the live tracking feel real

---

## What Still Needs to Be Built 🚧

### High Priority (breaks the Uber-like flow)

- [ ] **Connect Notifications WebSocket in Passenger and Admin views**
  - `createNotificationsWS` is defined in `api.js` but only the Driver view connects to it
  - Passengers should get real-time push notifications (ride status changes, vehicle assigned) without having to navigate to the Inbox
  - File: `frontend/src/SwiftApp.jsx` — add WS connection similar to how DriverView does it for tracking

- [ ] **Auto-dispatch pipeline on ride booking**
  - Currently a passenger books a ride → it stays `pending` until the 60-second cluster job runs, then waits for an admin to run route optimization
  - Need a trigger in `POST /rides/request` that immediately queues clustering + routing for new rides
  - File: `backend/routers/rides.py` → `create_ride_request()`

### Medium Priority (important features that are partially done)

- [ ] **Act on vehicle rebalance suggestions**
  - Suggestions are generated and stored but never acted on
  - Add a "Move Vehicle" button in Admin → Jobs panel that updates the vehicle's lat/lng to the suggested target
  - Or add a driver-facing "Suggested Move" card in the Driver dashboard

- [ ] **Wire road routing into VRP solver for real road distances**
  - `services/routing/astar_router.py` exists but is dead code — VRP uses straight haversine distance
  - Replace the haversine distance matrix in `vrp_solver.py` with cached road distances from Valhalla or OSMnx
  - Warning: this is slow for large route sets — consider caching the road graph

- [ ] **Role management UI**
  - `PATCH /auth/users/{user_id}/role` endpoint exists (admin only)
  - No frontend UI to promote a user to `driver` or `admin`
  - Add a User Management page in Admin panel that lists users and lets you change their role

- [ ] **Driver assignment UI**
  - The backend now supports assigning a vehicle with `driver_user_id`
  - Add an admin-facing control instead of requiring the API directly

- [ ] **Rating system**
  - `RatingView` component was in the old code (removed)
  - No `ratings` table in the DB
  - Add a rating model, POST endpoint, and a post-trip rating screen for passengers

- [ ] **Payment flow**
  - Fare amounts are display-only strings (`₹12–15`) — no payment processing
  - Need a `payments` table, Razorpay/Stripe integration, and a checkout screen
  - `PaymentView` view exists in the nav but renders nothing

- [ ] **Train and deploy the XGBoost demand model**
  - `backend/services/prediction/demand_model.py` loads from `ml/models/demand_model.pkl`
  - The file doesn't exist — prediction silently falls back to a time-of-day heuristic
  - Create a training script in `ml/` that trains on historical `ride_requests` data

### Low Priority (polish and production-readiness)

- [ ] **Passenger notification WebSocket badge counter**
  - The sidebar notification badge updates on load but doesn't auto-increment when new notifications arrive via WebSocket
  - Need to connect the notifications WS in `SwiftApp.jsx` and update `unreadCount` state on new messages

- [ ] **Refresh notifications and trips automatically**
  - After booking a ride, the "Recent Rides" list doesn't update until the user navigates away and back
  - Add a polling mechanism or WebSocket trigger to refresh the ride list when status changes

- [ ] **Driver can only see their own assigned rides**
  - Currently the driver panel loads all rides with `status=assigned`
  - Should filter by `vehicle.assigned_route_id` matching the driver's vehicle

- [ ] **Map: show route polyline on passenger tracking screen**
  - The passenger tracking map shows the vehicle marker and pickup/destination pins
  - Once a route is assigned, load the route waypoints and draw the VRP polyline

- [ ] **Responsive / mobile layout**
  - The sidebar + main panel layout breaks on screens narrower than ~800px
  - No mobile-specific ride booking flow (Uber's core UX is mobile-first)

- [ ] **Error boundaries**
  - The React app crashes completely on unhandled component errors
  - Add `<ErrorBoundary>` wrappers around each view

- [ ] **Backend tests**
  - `scripts/test_models_schemas.py` exists but is incomplete
  - No pytest tests for the routers or services
  - Key areas to cover: auth token validation, ride status transitions, VRP solver output

- [ ] **Production deployment**
  - No Dockerfile or docker-compose
  - No environment separation (dev / staging / prod)
- Backend secrets belong in `backend/.env` and should be rotated before any public deployment

---

## Architecture Overview

```
Passenger books ride
        ↓
POST /rides/request  ──→  RideRequest (status=pending)
        ↓  [background job every 60s]
HDBSCAN clustering   ──→  VirtualStop + ClusterRun (status=clustered)
        ↓  [admin triggers or background job]
OR-Tools VRP         ──→  RoutePlan + RouteWaypoints (status=assigned)
        ↓  [Hungarian algorithm]
Vehicle assignment   ──→  Vehicle.assigned_route_id set
        ↓  [simulation job every 5s]
Status progression   ──→  arriving → in_progress → completed
        ↓  [WebSocket broadcast every 2s]
Passenger tracking   ──→  Live map updates in browser
```

---

## API Reference

Full interactive docs available at `http://localhost:8000/docs` when backend is running.

Key endpoint groups:
- `POST /rides/request` — book a ride
- `GET /rides/my-rides` — passenger trip history
- `POST /cluster/run` — run HDBSCAN clustering (admin/driver)
- `POST /route/optimize` — run VRP route optimization (admin/driver)
- `WS /tracking/ws?token=` — live vehicle tracking stream
- `WS /notifications/ws?token=` — per-user notification stream
- `GET /analytics/overview` — fleet-wide statistics
- `GET /predict/heatmap` — demand prediction over a bounding box

---

## Security and production notes

- All protected REST and WebSocket endpoints require a verified Clerk session token.
- Tracking data is scoped server-side: passengers see only their assigned ride vehicle, drivers see only their assigned vehicle, and admins see the fleet.
- Admins assign a driver to a vehicle with `PATCH /vehicle/{vehicle_id}`:

  ```json
  { "driver_user_id": 123 }
  ```

- Keep database credentials, Clerk secrets, and Supabase service-role keys out of the frontend and all `VITE_*` variables.
- Set explicit production `ALLOWED_ORIGINS` values and serve the frontend/backend over HTTPS/WSS.
- Run database migrations before deployment and rotate any credentials that have been exposed during development.
