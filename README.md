# SmartRoute AI

An Uber-like AI-powered shared ride dispatch system built for Bengaluru. Uses HDBSCAN clustering, OR-Tools VRP optimization, and Hungarian assignment to pre-compute optimized multi-passenger routes before dispatch.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Tech Stack](#tech-stack)
- [Running the Project](#running-the-project)
- [What Works Right Now](#what-works-right-now-)
- [What Still Needs to Be Built](#what-still-needs-to-be-built-)
- [Architecture Overview](#architecture-overview)
- [API Reference](#api-reference)
- [Security and Production Notes](#security-and-production-notes)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Quick Start

Get the system running locally in 5 minutes:

```bash
# Clone and setup
git clone <repo>
cd finalyr_project

# Backend setup
cd backend
pip install -r ../requirements.txt
cp .env.example .env
# Edit .env with your DATABASE_URL, CLERK credentials, and STADIA_API_KEY

# Run migrations
alembic -c ../alembic.ini upgrade head

# Seed database (optional demo data)
python seed.py

# Start API
uvicorn main:app --reload --port 8000

# In another terminal, start worker
python worker.py
```

```bash
# Frontend setup (in new terminal from root)
cd frontend
npm install
cp .env.example .env
# Edit .env with VITE_CLERK_PUBLISHABLE_KEY and VITE_API_BASE_URL

# Start dev server
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Prerequisites

**System Requirements:**
- Python 3.10+
- Node.js 18+
- PostgreSQL (or use Supabase)
- Docker & Docker Compose (optional, for containerized deployment)

**Services:**
- [Clerk](https://clerk.com) — Authentication (sign up for free account)
- [Supabase](https://supabase.com) — PostgreSQL hosting (optional; local PostgreSQL works too)
- [Stadia Maps](https://stadiamaps.com) — Maps, geocoding, routing (free tier available)

**Local Database Alternative:**
For local development without Supabase, install PostgreSQL and create a local database:
```bash
createdb smartrouteai
```

Then use `DATABASE_URL=postgresql://postgres:password@localhost:5432/smartrouteai`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19 + Vite, MapLibre GL, Clerk (auth) |
| Backend | FastAPI (Python), SQLAlchemy, PostgreSQL (Supabase) |
| Auth | Clerk (JWT RS256 via JWKS) |
| Algorithms | HDBSCAN clustering, OR-Tools CVRP, Hungarian algorithm (scipy), H3 spatial indexing |
| ML | XGBoost demand model (heuristic fallback if model file absent) |
| Maps | Stadia Maps via MapLibre, with OSMnx road graph support for dispatch distances |
| Real-time | WebSockets (FastAPI) for live vehicle tracking + per-user notifications |

---

## Running the Project

### Backend

```bash
cd backend
pip install -r ../requirements.txt
uvicorn main:app --reload --port 8000
```

Requires `backend/.env` — copy `backend/.env.example` and fill in the values.
`DATABASE_URL` is required; the backend no longer uses a built-in database
credential fallback.

Run database migrations before starting the API:

```bash
alembic -c ../alembic.ini upgrade head
```

Alembic migration resources:

- [Official Alembic documentation](https://alembic.sqlalchemy.org/en/latest/)
- [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Alembic autogenerate guide](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)

When the SQLAlchemy models change, create a migration and review it before
applying it:

```bash
alembic -c ../alembic.ini revision --autogenerate -m "describe the schema change"
alembic -c ../alembic.ini upgrade head
```

The API and scheduled jobs are separate processes. Start the API with
`uvicorn main:app --host 0.0.0.0 --port 8000` from `backend/`, and start one
worker with `python worker.py` from `backend/`. Set `APP_ENV` to `development`,
`staging`, or `production`; never reuse a production `backend/.env` locally.

Health probes are available at `/health/live` and `/health/ready`.

### Docker

```bash
docker compose up --build
docker compose exec api alembic upgrade head
```

The compose file runs four services: `db` (Postgres), `api`, `worker`, and
`nginx-proxy-manager` (reverse proxy/TLS termination in front of `api`). See
[Running behind Nginx Proxy Manager](#running-behind-nginx-proxy-manager) for
how to configure the proxy host. Provide the production database and Clerk
settings through `backend/.env` or your deployment platform's secret manager;
do not bake them into the image.

For Amazon ECS/Fargate deployment with Docker Hub, use the task-definition
templates in [`deploy/ecs`](deploy/ecs). They define separate API and worker
services, Secrets Manager injection, CloudWatch logging, and ECS health checks.
See the [ECS deployment guide](deploy/ecs/README.md) for Docker Hub publishing,
Secrets Manager, IAM, migrations, and ALB setup.

Useful AWS references:

- [ECS standalone tasks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/standalone-tasks.html)
- [ECS private registry authentication](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/private-auth.html)
- [ECS task health checks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/healthcheck.html)

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
```

Keep the Stadia key server-side in `backend/.env` as `STADIA_API_KEY`. The
frontend calls FastAPI for geocoding, road snapping, routing, matrix, traffic,
and map matching; never place the Stadia secret in a `VITE_*` variable because
Vite publishes those values in the browser bundle.

Configure the private Stadia API key in `backend/.env` as `STADIA_API_KEY`.
The frontend map uses the authenticated FastAPI Stadia proxy, so no Stadia key
is required in `frontend/.env`. The map is Stadia-only and has no tile
fallback.

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
- WebSocket auth via the `bearer` subprotocol; tokens are not placed in URLs

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

### Passenger Real-Time Features
- **Notifications WebSocket** — Connected to `/notifications/ws` for instant ride status changes (assigned, vehicle arriving, completed)
- **Live route tracking** — WebSocket connection updates vehicle GPS every 5 seconds with real-time vehicle animation on map
- **Route polyline rendering** — Displays optimized VRP route path on map once vehicle is assigned to a ride group
- **Automatic ride status progression** — Simulation job advances rides through pipeline (`pending → clustered → assigned → arriving → in_progress → completed`) every 5 seconds with WebSocket push

### Admin (8 panels)
- **Overview** — real-time stats: total rides, vehicles, clusters, routes, utilisation %
- **Rides** — list all rides with status filter, manually advance any ride through the pipeline
- **Fleet** — create vehicles, set idle/active/offline, view GPS positions
- **Cluster** — run HDBSCAN clustering on pending rides, view run history with summaries; also auto-triggers on new ride bookings
- **Routes** — run OR-Tools VRP optimization with real road distances (via Stadia routing API + OSM fallback), view waypoint maps for each route
- **Analytics** — daily bar chart + table (7/14/30 day), overview metrics
- **Jobs** — scheduler status, manual trigger for clustering/demand/rebalance jobs, run history
- **Heatmap** — XGBoost demand predictions (pre-trained model deployed) visualized on MapLibre map using H3 cells

### Background Jobs (auto-run on backend startup)
- **Auto-dispatch pipeline** — on new ride booking, immediately queues clustering + VRP optimization + Hungarian assignment (no admin intervention needed)
- Clustering every 60 seconds — groups `pending` rides into virtual stops via HDBSCAN + K-Medoids + OSMnx road snapping
- Demand refresh every 300 seconds — updates DemandSnapshot table with XGBoost predictions (trained model at `ml/models/demand_model.pkl`)
- Fleet rebalance every 300 seconds — generates VehicleRebalanceSuggestion records for idle vehicles
- **Ride simulation every 5 seconds** — automatically advances active rides through the status pipeline and pushes WebSocket notifications

---

## What Still Needs to Be Built 🚧

### High Priority

- [ ] **Act on vehicle rebalance suggestions**
  - Suggestions are generated and stored (see `/jobs/rebalance-suggestions` endpoint) but never acted on
  - Add a "Move Vehicle" button in Admin → Jobs panel that updates vehicle's lat/lng to suggested location
  - **Effort:** Low (2-3 hours; backend ready)

### Medium Priority (important features that are partially done)

- [ ] **Optimize VRP solver road distance caching**
  - Road routing **is already implemented** via Stadia routing API (up to 25×25 matrices) with OSMnx fallback for larger sets
  - Enhancement: Add persistent cache layer to avoid repeated road graph loads on restart
  - Or: Replace in-memory OSM graph with cached GeoParquet dataset for faster initialization

- [ ] **Role management UI**
  - `PATCH /auth/users/{user_id}/role` endpoint exists (admin only)
  - No frontend UI to promote a user to `driver` or `admin`
  - Add a User Management page in Admin panel that lists users and lets you change their role
  - **Effort:** Medium (4-5 hours)

- [ ] **Driver assignment UI**
  - Backend supports assigning a vehicle with `driver_user_id` (see `PATCH /vehicle/{id}`)
  - Add an admin-facing dropdown in Fleet panel to assign drivers
  - **Effort:** Low (2-3 hours)

- [ ] **Rating system**
  - No `ratings` table in the DB; no model or endpoints
  - Add a rating model, POST endpoint, and a post-trip rating screen for passengers
  - **Effort:** High (8-10 hours)

- [ ] **Payment flow**
  - Fare amounts are display-only strings (`₹12–15`) — no payment processing
  - Requires `payments` table, Razorpay/Stripe API integration, checkout flow, webhook handling
  - **Effort:** Very High (20-30 hours, requires payment provider setup)

### Low Priority (polish and production-readiness)

- [ ] **Notification badge auto-increment on WebSocket**
  - Sidebar notification badge updates on page load but doesn't auto-update when new messages arrive via WS
  - **Effort:** Low (1-2 hours)

- [ ] **Driver view: auto-filter to own assigned rides**
  - Backend endpoint already scopes rides by driver; frontend just needs the filter
  - **Effort:** Low (1-2 hours)

- [ ] **Notification inbox auto-refresh on new messages**
  - Passenger trips already auto-poll every 4s; just needs WebSocket trigger instead
  - **Effort:** Low (1-2 hours)

- [ ] **Responsive / mobile layout**
  - The sidebar + main panel layout breaks on screens narrower than ~800px
  - No mobile-specific ride booking flow (Uber's core UX is mobile-first)

- [ ] **Error boundaries**
  - The React app crashes completely on unhandled component errors
  - Add `<ErrorBoundary>` wrappers around each view

- [x] **Backend tests**
  - Pytest coverage includes schema/model checks, health probes, protected routes,
    and WebSocket token handling
  - Continue expanding coverage for ride status transitions and VRP solver output

- [x] **Production deployment foundation**
  - Dockerfile, Docker Compose, Alembic, separate API/worker processes, and ECS
    Fargate task-definition templates are included
  - Use `backend/.env` only for local development; ECS production secrets belong
    in AWS Secrets Manager

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
- `WS /tracking/ws` with the `bearer` subprotocol — live vehicle tracking stream
- `WS /notifications/ws` with the `bearer` subprotocol — per-user notification stream
- `GET /analytics/overview` — fleet-wide statistics
- `GET /predict/heatmap` — demand prediction over a bounding box

---

## Security and Production Notes

- All protected REST and WebSocket endpoints require a verified Clerk session token.
- Tracking data is scoped server-side: passengers see only their assigned ride vehicle, drivers see only their assigned vehicle, and admins see the fleet.
- Admins assign a driver to a vehicle with `PATCH /vehicle/{vehicle_id}`:

  ```json
  { "driver_user_id": 123 }
  ```

- Keep database credentials, Clerk secrets, and Supabase service-role keys out of the frontend and all `VITE_*` variables.
- Set explicit production `ALLOWED_ORIGINS` values and serve the frontend/backend over HTTPS/WSS.
- Run database migrations before deployment and rotate any credentials that have been exposed during development.

### Running behind Nginx Proxy Manager

`docker-compose.yml` includes an `nginx-proxy-manager` service (image `jc21/nginx-proxy-manager`) on the same default network as `api`, so no extra network setup is needed.

1. `docker compose up -d` (starts db, api, worker, and NPM together).
2. Open the NPM admin UI at `http://<server-ip>:81`. First login is `admin@example.com` / `changeme` -- **change both immediately**.
3. Add a Proxy Host: domain = your public domain, forward hostname/IP = `api`, forward port = `8000`, scheme = `http`.
4. Turn on **Websockets Support** on that proxy host -- `/tracking/ws` and `/notifications/ws` will fail silently without it.
5. On the SSL tab, request a Let's Encrypt certificate and force SSL.
6. In NPM's Advanced tab for this proxy host, consider raising `proxy_read_timeout`/`proxy_send_timeout`; the default nginx timeout can drop long-lived WebSocket connections.
7. Point your domain's DNS A record at the server before requesting the certificate, and make sure ports 80/443 are open on the host firewall (needed for Let's Encrypt's HTTP-01 challenge).
8. Set `ALLOWED_ORIGINS` and `CLERK_AUTHORIZED_PARTIES` in `backend/.env` to your real `https://` domain, not `localhost`.

Uvicorn is already started with `--proxy-headers --forwarded-allow-ips=*` (see `Dockerfile` / `docker-compose.yml`) so it trusts `X-Forwarded-For`/`X-Forwarded-Proto` from NPM -- this is required for the HSTS header logic in `backend/main.py` to detect HTTPS correctly and for real client IPs to show up in logs.

---

## Troubleshooting

### Backend Issues

**Backend won't start with "Cannot import name 'X' from module"**
- Ensure you've installed all dependencies: `pip install -r requirements.txt`
- Try clearing pip cache: `pip cache purge` then reinstall

**Database connection error: `database "smartrouteai" does not exist`**
- Create the database: `createdb smartrouteai`
- Or update `DATABASE_URL` in `.env` to point to an existing database
- Ensure PostgreSQL is running: `psql -U postgres` should work

**Alembic migration fails with "Can't locate revision identified by..."**
- Delete any incomplete migration files in `alembic/versions/`
- Re-create from current models: `alembic revision --autogenerate -m "restart migrations"`

**WebSocket connection fails in tracking/notifications**
- Ensure `uvicorn main:app` is running (not a production server without WebSocket support)
- Check `ALLOWED_ORIGINS` in `.env` matches your frontend URL
- Verify Clerk token is valid and not expired

**Worker.py runs but doesn't trigger clustering/rebalance jobs**
- Set `ENABLE_BACKGROUND_JOBS_IN_API=false` in `.env` (only one process should handle jobs)
- Check logs: `python worker.py` should print job execution details
- Ensure database connectivity with `python -c "import backend.database; print('OK')"`

### Frontend Issues

**Vite dev server shows "Cannot find module 'maplibre-gl-worker.mjs'"**
- This is a Vite dependency resolution issue; fix with:
  ```bash
  rm -rf node_modules package-lock.json
  npm install
  npm run dev -- --force
  ```

**Map doesn't load or shows blank canvas**
- Verify `VITE_API_BASE_URL` in `.env` is correct
- Verify `STADIA_API_KEY` is set in backend `.env`
- Check browser console for errors; map requires STADIA_API_KEY to function
- Ensure backend's `/maps/style` endpoint returns valid Stadia style JSON

**"Cannot read property 'auth' of undefined" in browser console**
- Clerk app is not initialized; check that `VITE_CLERK_PUBLISHABLE_KEY` is set correctly in `.env`
- Verify Clerk Domain matches your Clerk app settings

**TypeScript/ESLint warnings about React 19**
- React 19 changes the `jsx` syntax; this is expected and not an error
- Run `npm run lint` to see actual lint issues vs. warnings

### Database & Migrations

**"Relation 'user' does not exist" after running backend**
- Migrations haven't been applied; run:
  ```bash
  alembic -c alembic.ini upgrade head
  ```

**Want to reset database to clean state**
- Downgrade migrations to zero:
  ```bash
  alembic downgrade base
  alembic upgrade head
  python seed.py  # repopulate with demo data
  ```

### Docker & Deployment

**Docker build fails with "Package X not found"**
- Ensure `requirements.txt` is in the root directory and is up-to-date
- The Dockerfile assumes a specific structure; verify all paths are correct

**ECS task keeps crashing**
- Check CloudWatch logs: `aws logs tail /ecs/smartroute-api`
- Verify Secrets Manager secrets are named exactly as task definition expects
- Ensure IAM task execution role has permission to read Secrets Manager

---

## Contributing

### Development Workflow

1. **Create a feature branch**: `git checkout -b feature/my-feature`
2. **Make changes** — follow existing code style and patterns
3. **Test your changes**:
   - Backend: `pytest tests/` (if adding new endpoints)
   - Frontend: `npm run lint` and manual testing in dev server
4. **Commit with clear messages**: `git commit -m "Add feature: description"`
5. **Push and create a PR**

### Code Style

**Backend (Python)**:
- Use type hints in function signatures
- Format with `black` (configured in project)
- Organize imports: standard library → third-party → local
- Docstrings for public functions/classes

**Frontend (JavaScript/React)**:
- Use functional components with hooks
- Keep components small and focused
- Prop-drill or use React Context for state management
- Use destructuring for imports and props

### Adding New Features

1. **Database schema changes?** Create an Alembic migration:
   ```bash
   alembic revision --autogenerate -m "add_new_column"
   ```
   Review the migration file before applying it

2. **New backend endpoint?** Add to `backend/routers/` and include:
   - Request/response schemas in `backend/schemas/`
   - Type-safe SQLAlchemy queries
   - Proper error handling and HTTP status codes
   - WebSocket broadcast for real-time updates if applicable

3. **New UI view?** Add to `frontend/src/views/` with:
   - Component structure in `frontend/src/components/`
   - Styling that matches existing UI
   - Error boundaries for graceful failure

### Testing

**Backend**:
```bash
cd backend
pytest tests/ -v  # verbose output
pytest tests/test_health_and_ws_auth.py::test_health_live  # single test
```

**Frontend**:
```bash
cd frontend
npm run lint  # check for style issues
npm run build  # verify production build works
```

### Project Structure Quick Reference

```
backend/
├── main.py              # FastAPI app initialization
├── models/              # SQLAlchemy ORM models
├── routers/             # API endpoint groups (auth, rides, vehicles, etc.)
├── schemas/             # Pydantic request/response validators
├── services/            # Business logic (clustering, routing, ML, etc.)
├── utils/               # Helper functions (auth, geo, etc.)
├── config.py            # Settings and environment variables
├── database.py          # SQLAlchemy engine and session
└── seed.py              # Demo data insertion

frontend/
├── src/
│   ├── App.jsx          # Main router
│   ├── SwiftApp.jsx     # App shell with sidebar
│   ├── views/           # Full-page views (PassengerView, DriverView, etc.)
│   ├── components/      # Reusable UI components
│   ├── hooks/           # Custom React hooks (useWebSocket, etc.)
│   ├── services/        # API clients (api.js)
│   └── config/          # Frontend constants

architecture/            # Detailed technical documentation
├── system-design.md
├── api-reference.md
├── db-schema.md
├── algorithms.md
├── websockets.md
└── supabase.md
```

### Getting Help

- Check [architecture/README.md](architecture/README.md) for design docs
- Review [architecture/api-reference.md](architecture/api-reference.md) for endpoint specs
- Read inline comments in service modules (clustering, routing, etc.)
- Run backend API at `/docs` for interactive Swagger UI
- Check test files for usage examples
