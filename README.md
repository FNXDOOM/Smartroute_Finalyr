# SmartRoute AI

An Uber-like AI-powered shared ride dispatch system built for Bengaluru. Uses HDBSCAN clustering, OR-Tools VRP optimization, and Hungarian assignment to pre-compute optimized multi-passenger routes before dispatch.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Tech Stack](#tech-stack)
- [Running the Project](#running-the-project)
- [Authentication & Role System](#authentication--role-system)
- [Architecture Overview](#architecture-overview)
- [API Reference](#api-reference)
- [Deployment (CI/CD)](#deployment-cicd)
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
# Edit .env with DATABASE_URL, CLERK_JWKS_URL, CLERK_ISSUER, CLERK_SECRET_KEY,
# LOCAL_JWT_SECRET, and STADIA_API_KEY (see backend/.env.example)

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
| Frontend | React 19 + Vite, MapLibre GL (Stadia-only via authenticated backend proxy), Clerk (auth) |
| Backend | FastAPI (Python), SQLAlchemy, PostgreSQL (Supabase) |
| Auth | Clerk (JWT RS256 via JWKS) + dual-role isolation (Passenger / Driver) |
| Role Sync | Clerk `publicMetadata` patched via Backend API on every role change (requires `CLERK_SECRET_KEY` in `backend/.env`; the backend only logs a line and skips the sync if it is missing) |
| Algorithms | HDBSCAN clustering, OR-Tools CVRP (Stadia ≤25×25 → OSM Dijkstra → haversine), Hungarian algorithm (scipy), H3 spatial indexing (res 9 ≈ 0.1 km²) |
| ML | XGBoost demand model (`ml/models/demand_model.pkl`, heuristic fallback if absent) |
| Maps | Stadia Maps via authenticated MapLibre proxy (`/maps/stadia/*`, `/geocode/*`, `/routing/*`), OSMnx road graph; all geo endpoints India-guarded (`is_india_location`) |
| Isolation | `ride_mode` (`live` \| `presentation_demo`) + `demo_run_id` on rides/stops/runs/plans/vehicles (Alembic `0002_demo_scope`); `PresentationDemoView` keeps demos off live fleet |
| Real-time | WebSockets (FastAPI) for live vehicle tracking + per-user notifications (bearer subprotocol only; `?token=` rejected with 4401) |

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

The dev compose file runs four services: `frontend` (nginx + Vite build),
`api` (FastAPI), `worker` (`python worker.py`), and `nginx-proxy-manager`
(reverse proxy/TLS termination). There is no local `db` service — the database
is Supabase PostgreSQL via `DATABASE_URL`. See
[Running behind Nginx Proxy Manager](#running-behind-nginx-proxy-manager) for
how to configure the proxy host. Provide the development database and Clerk
settings through `backend/.env`; do not bake them into the image.

### Deployment (CI/CD)

Production deploys run from `main` only:

```text
push to main → GitHub Actions (lint/test/build → docker build/push :<sha>)
  → Docker Hub (smartroute-api + smartroute-frontend)
  → EC2 (pull exact SHA → secrets from AWS Secrets Manager
  → alembic upgrade head → compose up → healthchecks)
```

Key files: `docker-compose.prod.yml` (pinned `image:`, no `build:`),
`deploy/deploy.sh` (migrate → up → `frontend /health`, `api /health/live`,
`api /health/ready` → rollback to previous SHA on failure),
`.github/workflows/ci-cd.yml` (PRs run lint/tests/build; `main` also pushes
and deploys; `concurrency: production`). Full setup — GitHub
Secrets/Variables, EC2 IAM + Security Groups, the Secrets Manager JSON layout,
first-deploy steps, and the forward-only migration / container-rollback policy —
is in [`deploy/README.md`](deploy/README.md).

For Amazon ECS/Fargate as an alternative to EC2, use the task-definition
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

The frontend map uses the authenticated FastAPI Stadia proxy, so no Stadia key
is required in `frontend/.env`. The map is Stadia-only and has no tile
fallback.

---

## Authentication & Role System

SmartRoute AI uses **Clerk** for authentication with two completely isolated login portals.

### Passenger Portal

Accessible via the ** Passenger Portal** tab on the login screen.
- Full Clerk `<SignIn />` / `<SignUp />` component with **Google OAuth + Email/Password**
- First-time sign-up auto-provisions a DB user with `role=passenger`
- Role is stored in the database and synced to Clerk `publicMetadata`

### Driver Portal

Accessible via the ** Driver Portal** tab on the login screen.
- Custom `DriverLoginForm` using Clerk's headless `useSignIn()` / `useSignUp()` SDK
- **No social login buttons** — strictly credentials-only (email + password)
- Sign-up uses Clerk email-code verification (6-digit input with resend) when the instance requires it
- Driver registration also captures vehicle license plate
- New drivers are assigned `role=driver, driver_status=pending_verification`
- Clerk `publicMetadata` reads `{ role: "pending", license_plate, driver_status: "pending_verification" }` until an admin approves, then flips to the confirmed driver state
- Signing in at the Driver portal with a still-`passenger` account routes to the in-app `DriverApplyView` to finish the application (the login screen unmounts on sign-in, so this step lives inside the app)
- Drivers see a verification gate screen until an admin approves them

### Driver Lifecycle

```
Driver registers via Driver Portal (email-code verified if required)
  └─ POST /auth/driver/apply { license_plate } → role="driver", driver_status="pending_verification"
  └─ Clerk publicMetadata → { role: "pending", license_plate, ... }
  └─ DriverVerificationGate shown instead of dashboard

Admin opens Overview → Pending Driver Verifications widget
  └─ POST /auth/driver/{id}/verify { status: "active" }  (also "suspended" / "rejected")
  └─ DB updated + Clerk publicMetadata synced to confirmed driver
  └─ Driver now sees full DriverView dashboard
```

### Environment Variables for Auth

| Variable | Where | Purpose |
|---|---|---|
| `VITE_CLERK_PUBLISHABLE_KEY` | `frontend/.env` | Initializes the Clerk frontend SDK |
| `CLERK_JWKS_URL` | `backend/.env` | URL to Clerk's JWKS endpoint for JWT verification |
| `CLERK_ISSUER` | `backend/.env` | Expected `iss` claim in Clerk JWTs |
| `CLERK_AUDIENCE` | `backend/.env` | (Optional) Expected `aud` claim |
| `CLERK_AUTHORIZED_PARTIES` | `backend/.env` | Must be the public `https://` domain in production (matches `ALLOWED_ORIGINS`) |
| `CLERK_ALLOW_NATIVE_CLIENTS` | `backend/.env` | Gate native-client tokens (`true` in dev example) |
| `CLERK_SECRET_KEY` | `backend/.env` | Backend API key to sync `publicMetadata` to Clerk in real time (present in `backend/.env.example` — set a real value; the backend only logs a line and skips the sync if it is missing) |

> **Note:** If `CLERK_SECRET_KEY` is omitted, role changes are saved to the database but Clerk `publicMetadata` is never updated (the sync is skipped silently). The app itself reads roles from the database, so it keeps working — only the Clerk dashboard view goes stale. After adding the key you must restart the backend (`uvicorn --reload` does not watch `.env`), then re-apply/approve once to backfill metadata.

### Role Reference

| Role | `driver_status` | Access |
|---|---|---|
| `passenger` | `active` | Passenger ride booking, tracking, history |
| `driver` | `pending_verification` | Verification gate only — no dashboard access |
| `driver` | `active` | Full driver dashboard, fleet map, ride management |
| `driver` | `suspended` | Verification gate — access blocked |
| `driver` | `rejected` | Verification gate — must be re-approved (re-apply to return to pending) |
| `admin` | `active` | All passenger + driver + admin panels |

> **First admin:** `PATCH /auth/users/{id}/role` is admin-only, so bootstrap the first admin with `UPDATE users SET role='admin' WHERE email='you@example.com';` or by setting `{ "role": "admin" }` in the user's Clerk public metadata (requires the session-token JWT template to expose it) and signing in again.
>
> **Re-registration:** signing in with the same email but a new Clerk identity links to the existing *passenger* row instead of crashing. Same-email `driver`/`admin` rows are never auto-linked — that login gets a `409` pointing at the original sign-in method.

### Seed the database (first run)

```bash
cd backend
python seed.py          # insert demo data
python seed.py --reset  # wipe and re-seed
```

---

## Architecture Overview

### Authentication Flow

```
Login Screen
├──  Passenger Portal (tab)
│   └── Clerk <SignIn /> — Google OAuth + Email/Password
│       └── JWT decoded → role defaults to "passenger"
│       └── DB user auto-provisioned
│
└── Driver Portal (tab)
    └── DriverLoginForm (useSignIn / useSignUp — credentials only)
        └── POST /auth/driver/apply
        └── role="driver", driver_status="pending_verification"
        └── DriverVerificationGate shown

Admin → Drivers Panel
└── POST /auth/driver/{id}/verify { status: "active" }
    └── DB updated + Clerk publicMetadata synced
    └── Driver sees full dashboard on next load
```

### Ride Dispatch Pipeline

```
Passenger books ride (India-guarded)
        ↓
POST /rides/request  ──→  RideRequest (status=pending, mode=live)
        ↓  [every 60s, or POST /jobs/run/auto-dispatch|clustering]
HDBSCAN clustering   ──→  VirtualStop + ClusterRun (status=clustered)
        ↓  [POST /route/optimize (drivers scoped to own vehicles) or auto-dispatch]
OR-Tools VRP (Stadia ≤25×25 → OSM Dijkstra → haversine, 10 s)  ──→  RoutePlan + RouteWaypoints (status=assigned)
        ↓  [Hungarian algorithm inside auto-dispatch / POST /vehicle/assign]
Vehicle assignment   ──→  Vehicle.assigned_route_id set, status=active
        ↓  [simulation job every 5s: assigned → arriving → in_progress → completed]
Status progression   ──→  arriving → in_progress → completed (pending/clustered never touched by sim)
        ↓  [WebSocket broadcast every 2s]
Passenger tracking   ──→  Live map updates in browser
```

Live and `presentation_demo` rows are isolated by `ride_mode` + `demo_run_id` (Alembic `0002_demo_scope`); demo flow uses `PresentationDemoView` + `DEMO-PRESENTATION-01`.

---

## API Reference

Full interactive docs available at `http://localhost:8000/docs` when backend is running.

### Authentication & Role Endpoints
- `GET /auth/me` — return current user profile
- `PATCH /auth/me` — update profile (name, phone)
- `POST /auth/driver/apply` — apply to become a driver (any authenticated user)
- `GET /auth/drivers/pending` — list pending driver applications (admin only)
- `POST /auth/driver/{user_id}/verify` — approve / reject / suspend a driver (admin only)
- `PATCH /auth/users/{user_id}/role?role=...` — override any user's role (admin only)

### Ride Endpoints
- `POST /rides/request` — book a ride (India-guarded, `mode=live`)
- `POST /rides/batch` — batch live booking
- `POST /rides/demo-batch` / `POST /rides/demo-shared-batch` / `DELETE /rides/demo-runs/{demo_run_id}` — isolated presentation demos
- `GET /rides/my-rides` — passenger trip history (live scope)
- `GET /rides/{ride_id}/vehicle` — assigned vehicle or null
- `POST /cluster/run` — run HDBSCAN clustering (admin/driver; `mode`/`demo_run_id` supported via jobs endpoints)
- `POST /route/optimize` — run VRP route optimization (admin/driver; drivers scoped to own `driver_user_id` vehicles)

### Maps / Geo (Stadia-backed, India-only, auth required)
- `GET /maps/stadia/style.json` + `GET /maps/stadia/resource/{path}` — authenticated tile proxy (no key in browser)
- `GET /geocode/suggest|search|reverse` — autocomplete / forward / reverse geocode
- `GET /routing/route` / `GET /routing/nearest-road` / `POST /routing/map-match` / `POST /routing/matrix` (matrix: admin/driver, 1–25 points per side)

### Jobs
- `POST /jobs/run/auto-dispatch` — full cluster → VRP → assign pipeline (`?mode=live|presentation_demo`)
- `POST /jobs/run/clustering` — same `mode`/`demo_run_id` query support

### Real-Time
- `WS /tracking/ws` with the `bearer` subprotocol — live vehicle tracking stream (`?token=` query rejected with 4401; scoped: admin=fleet, driver=own vehicle, passenger=own ride vehicle)
- `WS /notifications/ws` with the `bearer` subprotocol — per-user notification stream

### Analytics & ML
- `GET /analytics/overview` — fleet-wide statistics
- `GET /predict/heatmap` — demand prediction over a bounding box

---

## Security and Production Notes

- All protected REST and WebSocket endpoints require a verified Clerk session token. WebSocket `?token=` query params are rejected — use `['bearer', jwt]` (covered by `tests/test_health_and_ws_auth.py`).
- **India service area**: all ride/geocode/routing writes are guarded by `is_india_location` (6.5–35.7 / 68.1–97.4); out-of-area requests return `422`.
- **Driver Portal isolation**: The Driver Portal login form uses Clerk's headless `useSignIn()` — Google OAuth buttons are never rendered. Social logins are architecturally excluded, not just hidden.
- **Role enforcement is defence-in-depth**: Roles are checked at three layers — frontend route guard, FastAPI `require_roles()` dependency, and Clerk `publicMetadata` claims in the JWT.
- **`driver_status` guard**: Even if a user has `role=driver`, driver-only API endpoints reject requests if `driver_status` is not `active`.
- Tracking data is scoped server-side: passengers see only their assigned ride vehicle, drivers see only their assigned vehicle, and admins see the fleet.
- Admins assign a driver to a vehicle with `PATCH /vehicles/{vehicle_id}`:

  ```json
  { "driver_user_id": 123 }
  ```

- `CLERK_SECRET_KEY` in `backend/.env` enables real-time `publicMetadata` sync to Clerk. Without it, role updates are stored in the DB and synced on the user's next sign-in.
- Keep database credentials, Clerk secrets, and Supabase service-role keys out of the frontend and all `VITE_*` variables.
- Set explicit production `ALLOWED_ORIGINS` and `CLERK_AUTHORIZED_PARTIES` values and serve the frontend/backend over HTTPS/WSS.
- Run database migrations before deployment and rotate any credentials that have been exposed during development.

### Running behind Nginx Proxy Manager

`docker-compose.yml` includes an `nginx-proxy-manager` service (pinned to `2.12.3`
in `docker-compose.prod.yml`) on the same default network as `api`, so no extra
network setup is needed.

1. `docker compose up -d` (starts frontend, api, worker, and NPM together).
2. Open the NPM admin UI at `http://<server-ip>:81`. First login is `admin@example.com` / `changeme` -- **change both immediately**.
3. Add a Proxy Host: domain = your public domain, forward hostname/IP = `api`, forward port = `8000`, scheme = `http`.
4. Turn on **Websockets Support** on that proxy host -- `/tracking/ws` and `/notifications/ws` will fail silently without it.
5. On the SSL tab, request a Let's Encrypt certificate and force SSL.
6. In NPM's Advanced tab for this proxy host, consider raising `proxy_read_timeout`/`proxy_send_timeout`; the default nginx timeout can drop long-lived WebSocket connections.
7. Point your domain's DNS A record at the server before requesting the certificate, and make sure ports 80/443 are open on the host firewall (needed for Let's Encrypt's HTTP-01 challenge).
8. Set `ALLOWED_ORIGINS` and `CLERK_AUTHORIZED_PARTIES` in `backend/.env` to your real `https://` domain, not `localhost`.

Uvicorn is already started with `--proxy-headers` and `--forwarded-allow-ips` limited
to loopback + private ranges (see `backend/Dockerfile` / `docker-compose.yml`) so it trusts `X-Forwarded-For`/`X-Forwarded-Proto` from NPM -- this is required for the HSTS header logic in `backend/main.py` to detect HTTPS correctly and for real client IPs to show up in logs.

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
- The backend Dockerfile assumes a specific structure; verify all paths are correct

**Production deploy fails or new version is unhealthy**
- See [`deploy/README.md`](deploy/README.md): `deploy.sh` rolls containers back
  to the previous SHA automatically but leaves DB migrations forward (by design)
- Check EC2: `docker compose -f docker-compose.prod.yml ps` and
  `docker compose -f docker-compose.prod.yml logs --tail=50 api`
- Verify the Secrets Manager JSON has all required keys and the EC2 IAM role
  allows `secretsmanager:GetSecretValue`

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
# from project root (tests/ live at root, backend on sys.path)
pytest tests/ -v  # verbose output
pytest tests/test_health_and_ws_auth.py -v  # single file
python scripts/test_models_schemas.py  # schema/model sanity check
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
├── main.py              # FastAPI app initialization (+ lifespan broadcast loop)
├── worker.py            # Dedicated asyncio worker (scheduled jobs)
├── models/              # SQLAlchemy ORM models (12 tables)
├── routers/             # API endpoint groups (auth, rides, cluster, route, vehicle, tracking, notifications, analytics, predict, jobs, routing, geocode, maps)
├── schemas/             # Pydantic request/response validators
├── services/            # Business logic (clustering, routing/vrp_solver, assignment, prediction, stadia_client, clerk_service, background_jobs, etc.)
├── utils/               # Helper functions (auth_utils, geo [haversine + India guard], ride_scope [live/demo])
├── config.py            # Settings and environment variables
├── database.py          # SQLAlchemy engine and session (+ PortableGeometry)
├── Dockerfile           # Backend image (shared by api + worker)
└── seed.py              # Demo data insertion (see also scripts/seed_db.py)

frontend/
├── Dockerfile           # Vite build -> nginx (VITE_* baked as build-args in CI)
├── nginx.conf           # SPA fallback + /health probe
├── src/
│   ├── App.jsx          # Main router
│   ├── SwiftApp.jsx     # App shell with sidebar
│   ├── views/           # Full-page views (PassengerView, DriverView, AdminView, PresentationDemoView)
│   ├── components/      # Reusable UI components (AppMap, DriverLoginForm, DriverVerificationGate)
│   ├── hooks/           # Custom React hooks (useWebSocket, etc.)
│   ├── services/        # API clients (api.js — Clerk JWT interceptor, bearer WS factories)
│   └── config/          # Frontend constants (demoPresets, etc.)

ml/models/demand_model.pkl  # Trained XGBoost demand model (see scripts/train_demand_model_synthetic.py)

docker-compose.yml        # Dev: builds images locally (frontend/api/worker + NPM)
docker-compose.prod.yml   # Prod: pulls immutable Docker Hub :<sha> images (no build)
deploy/
├── deploy.sh            # EC2 deploy: pull SHA → Secrets Manager → migrate → up → healthcheck → rollback
└── README.md            # GitHub/EC2/Secrets Manager setup + first-deploy + rollback
.github/workflows/ci-cd.yml  # PR lint/test/build; main pushes images + deploys to EC2

architecture/            # Detailed technical documentation
├── system-design.md
├── api-reference.md
├── db-schema.md
├── algorithms.md
├── background-jobs.md
├── websockets.md
└── supabase.md
```

### Getting Help

- Check [architecture/README.md](architecture/README.md) for design docs
- Review [architecture/api-reference.md](architecture/api-reference.md) for endpoint specs
- Read inline comments in service modules (clustering, routing, etc.)
- Run backend API at `/docs` for interactive Swagger UI
- Check test files for usage examples
