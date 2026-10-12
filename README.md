# SmartRoute AI

Ride dispatch for Bengaluru. HDBSCAN clusters pickups, a destination-corridor pass pools
compatible riders, and OR-Tools solves one combined pickup-and-delivery route per vehicle.
Routes are pre-computed before dispatch — a driver accepts an already-solved run.

Deep documentation lives in [`architecture/`](architecture), not here. This file is only
"what is it, how do I run it, what will bite me".

## Stack

| | |
|---|---|
| Backend | FastAPI, SQLAlchemy, PostgreSQL 16 + PostGIS, Alembic |
| Frontend | React 19 + Vite, MapLibre GL, shadcn/ui |
| Auth | Clerk (JWT RS256 via JWKS); roles resolved from the database only |
| Routing/ML | HDBSCAN, OR-Tools CP-SAT pickup-and-delivery, Hungarian assignment, H3 res 9, XGBoost demand model |
| Geo | Stadia Maps behind an authenticated backend proxy, OSMnx road graphs, all writes India-guarded |
| Real-time | WebSockets for vehicle tracking and per-user notifications |
| Payments | Razorpay — server-side fares, HMAC signature verification, idempotent webhooks |
| Isolation | `ride_mode` (`live` / `presentation_demo`) + `demo_run_id` on every scoped table |

Needs Python 3.10+, Node 18+, and a PostGIS-capable PostgreSQL — the schema uses
`geoalchemy2` geometry columns, so plain PostgreSQL will not work.

## Run it

```bash
cd backend
pip install -r ../requirements.txt
cp .env.example .env        # DATABASE_URL, Clerk settings, STADIA_API_KEY, LOCAL_JWT_SECRET, RAZORPAY_*
alembic -c ../alembic.ini upgrade head
uvicorn main:app --reload --port 8000
```

Second terminal, from `backend/`:

```bash
python worker.py            # scheduled clustering / dispatch / demand / rebalance
```

The API and the jobs are **separate processes**. Keep `ENABLE_BACKGROUND_JOBS_IN_API=false`
so exactly one of them schedules work.

```bash
cd frontend && npm install && cp .env.example .env   # VITE_CLERK_PUBLISHABLE_KEY, VITE_API_BASE_URL
npm run dev                 # http://localhost:5173
```

Never put `STADIA_API_KEY` in a `VITE_*` variable — Vite publishes those into the browser
bundle. The map already proxies through the API.

Optional demo data: `python seed.py` (or `--reset` to wipe and re-seed).

### Docker

```bash
docker compose up --build
docker compose exec api alembic upgrade head
```

Dev compose runs `db` (PostGIS 16, published on 127.0.0.1 only), `frontend`, `api`, `worker`
and `nginx-proxy-manager`. The `db` service supplies `DATABASE_URL`, overriding `backend/.env`.

### Migrations

Forward-only. `alembic downgrade` is never run against a shared database — down-migrations
are untested and can destroy data ([`deploy/README.md`](deploy/README.md) states the policy).
After changing a model, generate the revision and **read it** before applying:

```bash
alembic -c ../alembic.ini revision --autogenerate -m "describe the change"
alembic -c ../alembic.ini upgrade head
```

`run_startup_migrations()` also applies additive Postgres backfills at boot, so a skipped
`upgrade head` fails loudly rather than half-working.

## Auth and roles

Two isolated portals. The passenger `<SignIn />` offers Google OAuth; the driver form uses
Clerk's headless `useSignIn()` and renders no social buttons at all — credentials only.

**The database is the only source of truth for a role.** A Clerk JWT is identity only:
`role` / `driver_status` claims, including `publicMetadata` (which users can usually write
about themselves), never grant anything. `require_roles()` authenticates, then reads the
`users` row; `ensure_active_driver()` blocks any `role=driver` whose status is not `active`,
across both the write endpoints and the read-only surfaces. The backend *pushes* metadata to
Clerk so its dashboard and the client's optimistic UI agree — that sync is cosmetic. Without
`CLERK_SECRET_KEY` the push is skipped with one log line and the app keeps working.

Driver lifecycle: apply → `pending_verification` → gate screen → admin
`POST /auth/driver/{id}/verify` → `active` (dashboard) / `suspended` (blocked everywhere,
role retained for reinstatement) / `rejected` (returned to `passenger`, must re-apply).

Bootstrap the first admin in SQL, because `PATCH /auth/users/{id}/role` is itself admin-only:

```sql
UPDATE users SET role='admin' WHERE email='you@example.com';
```

Signing in with an existing email but a new Clerk identity links to the *passenger* row;
same-email `driver`/`admin` rows are never auto-linked and get a `409`.

## Dispatch and carpooling

```
pending → HDBSCAN + corridor search → VirtualStop/ClusterRun → OR-Tools PDP
        → RoutePlan(solved) → Hungarian vehicle assignment → driver accepts → per-stop workflow
```

Carpooling pools 2–3 riders. A corridor-matched group gets **one** `cluster_id` with one
pickup stop per rider, within a 150 m walk limit. Acceptance closes the run to new riders.
Each rider then walks a per-rider ladder that stays in lockstep with the coarse `status`, so
clients reading only `status` are unaffected:

```
pending → searching → clustered → assigned → driver_accepted → driver_arriving
→ pickup_ready → passenger_confirmed_pickup_stop → boarded → in_transit → dropped_off → completed
```

Only explicit completion ends a run; a co-passenger cancellation moves the plan to
`needs_reoptimization` and the driver keeps serving the rest. Presence beats every 30 s and
stay dispatchable for 90 s — an unaccepted route held by a driver who went offline is
released on the next cycle.

## Endpoints

Don't maintain a second list here: `architecture/api-reference.md` is the spec and
`http://localhost:8000/docs` serves live Swagger. Two things worth knowing up front:

- Every geo route (`/maps/stadia/*`, `/geocode/*`, `/routing/*`) is authenticated and
  India-guarded; the map style is `/maps/stadia/style.json`.
- Tracking is scoped server-side: admin sees the fleet, a driver their own vehicle, a
  passenger the vehicle on their ride.

## Monitoring

`/health/live`, `/health/ready` (real `SELECT 1`) and `/metrics` in Prometheus format.
`/metrics` is unauthenticated because a scraper holds no JWT, and that is safe only because
nothing publishes it — no host port and no proxy route.

Prometheus and Grafana are opt-in and never published:

```bash
docker compose --profile monitoring up -d
```

Without the profile the resolved compose file is unchanged, so a host that has not opted in
pays no memory for it. Neither service maps a host port; reach Grafana with
`ssh -L 3000:grafana:3000 <host>`. The admin panel does **not** embed Grafana — it calls
`GET /analytics/monitoring`, which queries Prometheus from a fixed server-side whitelist, so
caller-supplied PromQL never reaches it.

## Tests

```bash
DATABASE_URL=sqlite:///./.testdb/ci_test.db pytest tests/ -v
```

139 tests, ~26 s. The suite is hermetic, and both guards have an explicit opt-out because
both failure modes are silent:

- **Outbound sockets are refused.** `road_snapper.build_road_graph` asks Overpass for a road
  graph per 0.05° cell. This is invisible locally because `osmnx` is only in
  `requirements.txt`, so the import fails and returns `None`; on a networked runner it
  really fetches, which took this suite past ten minutes. Override: `TEST_ALLOW_NETWORK=1`.
- **A hosted `DATABASE_URL` is refused.** `create_db_tables()` issues real DDL
  (`ALTER TABLE … ADD COLUMN`, `CREATE INDEX`), so a bare `pytest` would migrate whatever
  `backend/.env` points at. Override: `TEST_DB_ALLOW_REMOTE=1`.

`SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS` lowers the pooled-route solver budget from its 15 s
production default; CI sets 1 because `GUIDED_LOCAL_SEARCH` has no early exit and pays the
whole budget per call (~80 s across the suite). Scratch databases belong in `.testdb/`
(gitignored) and the fixture keeps the three newest.

There is no frontend test runner — verification is `npm run lint` plus `npm run build`.

## Layout

```
backend/
  main.py         FastAPI app, middleware, /health + /metrics
  worker.py       scheduled jobs; no HTTP listener
  models/ routers/ schemas/ services/ utils/    13 tables
  config.py database.py seed.py Dockerfile
frontend/src/     SwiftApp.jsx views/ components/ services/api.js hooks/ config/
alembic/          forward-only migrations
monitoring/       Prometheus + Grafana config (profile-gated)
deploy/           deploy.sh + the EC2 / Secrets Manager runbook
architecture/     system-design, api-reference, db-schema, algorithms,
                  background-jobs, websockets
docs/payments.md  Razorpay setup, webhooks, test cards
```

`docker-compose.yml` builds locally; `docker-compose.prod.yml` pulls immutable `:<git-sha>`
images. Production is: push to `main` → CI lint/test/build → push images → SCP the bundle
(`docker-compose.prod.yml`, `deploy/deploy.sh`, `monitoring/`) to a git-free EC2 →
`deploy.sh` pulls, fetches secrets from AWS Secrets Manager, migrates, starts, health-checks,
and rolls containers back to the previous SHA on failure. Full setup and first-deploy steps:
[`deploy/README.md`](deploy/README.md). An ECS/Fargate alternative is in [`deploy/ecs/`](deploy/ecs).

## Gotchas

- **`uvicorn --reload` does not watch `.env`.** Restart after editing it.
- **WebSockets fail silently behind NPM** unless "Websockets Support" is on for that proxy
  host; raise `proxy_read_timeout` there too or long-lived connections drop.
- **WS auth accepts `?token=<jwt>` as a last resort.** Header and the `bearer, <jwt>`
  subprotocol are preferred; the query fallback exists because Flutter's
  `web_socket_channel` cannot negotiate subprotocols. Query tokens are read from the parsed
  dict and never logged.
- **A blank map is almost always a missing server-side `STADIA_API_KEY`** — the map is
  Stadia-only with no tile fallback.
- **Nothing dispatches** if both the API and the worker schedule jobs, or neither does.
- **Vehicle writes are `PATCH /vehicle/{id}`** — singular, like the other router prefixes.
- Rotate any credential that has ever been pasted into a terminal or chat log; `backend/.env`
  is gitignored, but that does not un-leak it.
