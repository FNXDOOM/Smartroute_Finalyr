# SmartRoute AI

[![CI](https://github.com/FNXDOOM/Smartroute/actions/workflows/ci-cd.yml/badge.svg?branch=main)](https://github.com/FNXDOOM/Smartroute/actions/workflows/ci-cd.yml)
[![License](https://img.shields.io/github/license/FNXDOOM/Smartroute)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

SmartRoute AI is a shared-ride dispatch platform for Bengaluru. It clusters nearby
ride requests, pools riders travelling on the same corridor, and solves one
combined pickup-and-delivery route per vehicle before a driver accepts the run.

## Highlights

- **Shared-ride matching** — HDBSCAN on H3 cells plus a corridor pass, with a
  150 m pickup-walk limit.
- **Route optimisation** — OR-Tools pickup-and-delivery and Hungarian vehicle
  assignment, solved before dispatch.
- **Live operations** — driver carpool workflow, JWT-authenticated WebSockets,
  notifications, analytics and job monitoring.
- **Platform** — Clerk for web, local JWT for mobile, Razorpay payments, and an
  isolated presentation-demo mode.

## Architecture

```mermaid
flowchart LR
  client[Web / mobile client] --> npm[Nginx Proxy Manager]
  npm --> api[FastAPI API]
  api --> db[(PostgreSQL + PostGIS)]
  worker[Worker] --> db
  api --> maps[Stadia Maps / OSMnx]
  api --> solver[HDBSCAN / OR-Tools]
  api -. WebSocket .-> client
```

The API serves HTTP and WebSockets; the worker runs scheduled clustering,
dispatch, demand-refresh and rebalance jobs. Both use the same PostgreSQL
database. Keep jobs in one process with `ENABLE_BACKGROUND_JOBS_IN_API=false`.

Stack: Python 3.10, FastAPI, SQLAlchemy, Alembic, PostgreSQL 16 + PostGIS 3.4,
React 19, Vite, MapLibre GL, Clerk, Stadia Maps, Prometheus and Grafana.

Deep design notes live in [`architecture/`](architecture).

## Quick start

**Prerequisites:** Python 3.10+, Node.js 20.19+ (or 22.12+), PostgreSQL 16 with
PostGIS 3.4 (or Docker), a Clerk application, and a Stadia Maps API key.

### 1. Configure

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Set the required backend values and `VITE_CLERK_PUBLISHABLE_KEY` in the
frontend file. See [Configuration](#configuration).

With the compose database, use
`DATABASE_URL=postgresql://smartroute:smartroute@localhost:5432/smartroute`;
otherwise point it at your own PostGIS instance.

### 2. Backend

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

docker compose up -d db            # optional if you already run PostGIS

cd backend
alembic -c ../alembic.ini upgrade head
uvicorn main:app --reload --port 8000
```

Run the worker in a second terminal:

```bash
cd backend
python worker.py
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

### Docker stack

To run the full stack in Docker instead of the local processes above:

```bash
cp backend/.env.example backend/.env   # fill the required values
export VITE_API_BASE_URL=http://api.localhost
export VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
export ALLOWED_ORIGINS=http://app.localhost
export CLERK_AUTHORIZED_PARTIES=http://app.localhost
docker compose up --build
docker compose exec api alembic upgrade head
```

Open `http://localhost:81` (loopback only) and create two NPM proxy hosts:
`app.localhost` → `frontend:80`, `api.localhost` → `api:8000`; enable WebSockets
on both. Then open `http://app.localhost` (or the hostnames you configured).
Use the same app origin in your Clerk instance.

Add `--profile monitoring` to the `up` command to include Prometheus and
Grafana locally; production includes them in the same production compose file.

Optional demo data: `cd backend && python seed.py` (or `--reset`). Staging and
production seeding requires `SEED_ADMIN_PASSWORD` and `SEED_DEMO_PASSWORD`.

## Configuration

Settings live in `backend/.env`; the full list is in
[`backend/.env.example`](backend/.env.example).

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL + PostGIS connection string |
| `LOCAL_JWT_SECRET` | Yes | Mobile JWT key; startup fails if empty |
| `CLERK_JWKS_URL`, `CLERK_ISSUER` | For Clerk sign-in | Clerk JWT verification |
| `CLERK_SECRET_KEY` | No | Clerk metadata sync |
| `STADIA_API_KEY` | For maps | Maps, geocoding and routing |
| `ALLOWED_ORIGINS`, `CLERK_AUTHORIZED_PARTIES` | Production | Public HTTPS origins |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | No | Payments return 503 without them |
| `APP_ENV` | No | `development` (default) or `production` |
| `SEED_ADMIN_PASSWORD`, `SEED_DEMO_PASSWORD` | Seed only | Required outside development |

Never put backend secrets in `VITE_*` variables; Vite publishes those in the
browser bundle.

## API and authentication

- Swagger: `http://localhost:8000/docs`
- Full reference: [`architecture/api-reference.md`](architecture/api-reference.md)
- Health: `/health/live`, `/health/ready`; `/metrics` is internal-only

The database is the only source of truth for `role` and `driver_status`; JWT
claims never grant privileges. A first Clerk sign-in is not auto-linked to an
existing account by email. Bootstrap the first admin once in SQL:

```sql
UPDATE users SET role = 'admin' WHERE email = 'you@example.com';
```

## Testing

```bash
DATABASE_URL="sqlite:///./.testdb/ci_test.db" \
SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS=1 \
python -m pytest tests/ -q
```

The suite has 147 tests and refuses outbound sockets and hosted database URLs.
Override only when intentional: `TEST_ALLOW_NETWORK=1`, `TEST_DB_ALLOW_REMOTE=1`.
On Windows, use `py` instead of `python`.

Frontend verification:

```bash
cd frontend
npm run lint
npm run build
```

## Deployment

Pushing to `main` runs tests, builds immutable Docker images and deploys them to
a git-free EC2 host. Runtime secrets come from AWS Secrets Manager; migrations
are forward-only and containers roll back to the previous image on failure.

See [`deploy/README.md`](deploy/README.md) for the runbook. The NPM admin UI is
bound to `127.0.0.1:81`, and the public proxy denies `/metrics`.

Prometheus and Grafana are part of the production stack and start with the app.
Locally, start them with `docker compose --profile monitoring up -d`. Their
ports bind to `127.0.0.1`; on EC2 use
`ssh -L 9090:127.0.0.1:9090 -L 3000:127.0.0.1:3000 <host>`.

## Repository layout

`backend/` API and worker · `frontend/` React app · `alembic/` migrations ·
`architecture/` design docs · `deploy/` EC2 and Secrets Manager runbook ·
`monitoring/` Prometheus and Grafana config.

## Security

- Report vulnerabilities privately via
  [GitHub Security Advisories](https://github.com/FNXDOOM/Smartroute/security/advisories/new).
- Never commit `.env` files or provider secrets; keep server secrets server-side.
- Production CORS accepts only configured HTTPS origins, and roles are read from
  the database.

## License

Licensed under the Apache License, Version 2.0. See [`LICENSE`](LICENSE) and
[`NOTICE`](NOTICE).

## Contributing

Create a branch, run the backend tests and frontend lint/build, then open a pull
request describing the change and any migration or configuration impact.
