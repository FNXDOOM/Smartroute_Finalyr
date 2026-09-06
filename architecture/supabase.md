# SmartRouteAI + Supabase Setup Guide

This project should use Supabase as the managed PostgreSQL/PostGIS database and
Clerk as the authentication provider. The FastAPI backend should remain the
owner of clustering, route optimization, background jobs, and WebSockets.

## Recommended architecture

```text
React/Vite frontend
        │
        │ Clerk session JWT + Authorization: Bearer <JWT>
        ▼
FastAPI backend
        │
        │ SQLAlchemy DATABASE_URL over SSL
        ▼
Supabase PostgreSQL + PostGIS
```

Use Clerk as the single identity provider. Do not keep the current custom
password/JWT flow active alongside Clerk in production. The backend should
verify Clerk session tokens and use the Clerk user ID in the JWT `sub` claim to
find the matching application profile.

The frontend should call FastAPI for business operations. Do not expose the
Supabase `service_role` key in React or browser code.

## 1. Create the Supabase project

1. Create a project at [supabase.com](https://supabase.com/).
2. Save the database password in a password manager.
3. In **Database → Extensions**, enable **PostGIS**. SmartRouteAI currently
   stores latitude/longitude columns and uses Python for H3/clustering, but
   PostGIS is needed for the production geometry columns and future spatial
   queries.
4. In Clerk, configure the sign-in methods, email verification, redirect URLs,
   and roles/metadata required by the application.
5. If the browser will query Supabase directly, activate the native Clerk
   integration under Supabase's authentication providers and configure Clerk as
   a third-party provider. This is optional when all database access goes through
   FastAPI.

## 2. Connect the FastAPI backend

For a long-running FastAPI server, use the Supabase direct connection when the
deployment supports IPv6, or the Supavisor session pooler on IPv4-only hosting.
Use the connection string shown by the Supabase **Connect** dialog; never commit
the password.

Backend `backend/.env`:

```env
DATABASE_URL=postgresql://postgres:<PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres
ALLOWED_ORIGINS=http://localhost:5173
AUTH_PROVIDER=clerk
CLERK_JWKS_URL=https://<your-clerk-domain>/.well-known/jwks.json
CLERK_ISSUER=https://<your-clerk-domain>
```

If using the session pooler, the host and username will look different and the
port is normally `5432`. Transaction pooler mode uses port `6543` and does not
support prepared statements, so it should not be the first choice for this
long-running SQLAlchemy backend unless the engine is configured accordingly.

Remove the old local PostgreSQL password and do not use SQLite in production.
Run the schema against Supabase explicitly and confirm the
connection before starting background workers.

## 3. Migrate the current schema

The SQLAlchemy models are the current source of truth for these tables:

`users`, `ride_requests`, `virtual_stops`, `cluster_runs`, `route_plans`,
`route_waypoints`, `vehicles`, `tracking_events`, `notifications`, `job_runs`,
`demand_snapshots`, and `vehicle_rebalance_suggestions`.

Recommended migration process:

1. Create a staging Supabase project.
2. Set its `DATABASE_URL` in a local `backend/.env`.
3. Run the existing table creation/seed process against staging and inspect all
   tables, foreign keys, indexes, JSON columns, and geometry columns.
4. Run the checked-in Alembic baseline with `alembic upgrade head`, then add
   a new revision for every schema change. Do not use
   `Base.metadata.create_all()` during application startup.
5. Back up the existing `smartrouteai.db` before importing any development data.
6. Import only sanitized seed/demo data into production.

At minimum, the first migration should create the tables and indexes currently
described in [db-schema.md](./db-schema.md), enable PostGIS, and add a unique
identity mapping from `clerk_user_id` to the application profile row.

## 4. Choose the user/profile model

Clerk owns login credentials and user profiles. Keep application-specific fields
in the database so backend authorization does not depend on browser-supplied
data. A practical target is:

```sql
create table public.profiles (
  id bigint generated always as identity primary key,
  clerk_user_id text not null unique,
  name text not null,
  phone text,
  role text not null default 'passenger'
    check (role in ('passenger', 'driver', 'admin')),
  created_at timestamptz not null default now()
);
```

The current SQLAlchemy `users.id` is an integer and the current foreign keys
point to it. The lowest-risk migration is:

- keep integer application IDs and add a unique `clerk_user_id text` column;
- create/update the application row from Clerk webhooks (`user.created`,
  `user.updated`, and `user.deleted`); and
- use the Clerk `sub` claim to resolve the application user on every request.

Do not use Clerk's user ID as an integer or silently trust a role from the
frontend.

## 5. Backend authentication with Clerk

The backend now expects Clerk session tokens for protected endpoints:

1. Add Clerk's React SDK and wrap the app in `ClerkProvider`.
2. Use Clerk's sign-in and sign-up components/hooks.
3. Send the Clerk session token to FastAPI as:

   ```http
   Authorization: Bearer <clerk-session-token>
   ```

4. `get_current_user` verifies Clerk's JWT signature using Clerk's
   published JWKS/public key and validate the issuer/audience expected by the
   Clerk instance. Read the `sub` claim.
5. Load the matching profile and enforce the role from the server-side profile,
   not from browser input.
6. Remove or disable public registration with a client-supplied `role`; new
   users must start as `passenger` and only an admin workflow may promote them.
7. Keep Clerk secret keys and Supabase database credentials only in the backend
   environment.

Do not accept a user ID, role, or admin flag from the frontend as proof of
identity. Clerk verifies identity; FastAPI still authorizes every operation.

## 6. Frontend changes required

The current frontend (`frontend/src/`) is Clerk-wired — no mock fallbacks remain in the API layer:

- `frontend/src/services/api.js` attaches the Clerk session JWT via `setAuthTokenGetter()` on every request (Axios interceptor → `Authorization: Bearer <jwt>`); `WS_BASE_URL` is derived from `VITE_API_BASE_URL`. There are no fake-ride/vehicle/analytics fallbacks.
- Auth uses `@clerk/clerk-react` (`ClerkProvider` in `main.jsx`/`App.jsx`): Passenger portal = `<SignIn/>`/`<SignUp/>` with Google OAuth + password; Driver portal = headless `DriverLoginForm.jsx` (credentials only, email-code verification when required) → `POST /auth/driver/apply` (plate, explicit per-request token); still-`passenger` sign-ins route to the in-app `DriverApplyView.jsx` to finish applying; pending drivers see `DriverVerificationGate.jsx`.
- Views are real: `PassengerView.jsx` (book/cancel/history + live map + VRP polyline), `DriverView.jsx` (fleet map, GPS push, Start/Arriving/Complete), `AdminView.jsx` (9 panels), `PresentationDemoView.jsx` (isolated `presentation_demo` runs via `POST /rides/demo-batch` + `POST /jobs/run/auto-dispatch?mode=presentation_demo`).
- Maps go through the authenticated Stadia proxy (`/maps/stadia/style.json`); geocoding/routing go through `/geocode/*` and `/routing/*` (India-guarded). The Stadia key lives only in `backend/.env` — never in `VITE_*`.
- WebSockets use the `bearer` subprotocol (`createTrackingWS` / `createNotificationsWS` in `services/api.js`, consumed via `hooks/useWebSocket.js`); `?token=` query params are rejected with `4401` (see `tests/test_health_and_ws_auth.py`).

Before production, keep this posture: surface API errors in the UI (no silent success), and keep all secrets out of `frontend/.env`.

Frontend environment variables should be public-only:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
```

The Supabase URL/key are only needed in the frontend if it directly queries
Supabase. Never put `DATABASE_URL`, Clerk secret keys, or a
Supabase service-role/secret key in `frontend/.env` or any `VITE_*` variable.

## 7. Row Level Security

If the browser accesses Supabase tables directly, configure Supabase's native
Clerk third-party integration and enable RLS on every exposed table. Policies
can compare the Clerk ID in the JWT with a text `clerk_user_id` column. For the
recommended architecture where the browser calls FastAPI and FastAPI uses
SQLAlchemy, keep application tables private to the Data API and enforce access
in FastAPI.

At a minimum:

- passengers can read and cancel only their own rides;
- passengers can read and mark only their own notifications;
- drivers can read/update only the fleet and rides assigned to them;
- admins can manage users, vehicles, routes, and jobs;
- anonymous users cannot read rides, vehicles, notifications, or tracking data.

RLS is still valuable as defense in depth, but it does not replace FastAPI role
checks. A backend connection using the database owner/service credentials can
bypass RLS, so application authorization must remain explicit.

## 8. Realtime and WebSockets

Keep the current FastAPI WebSocket for live vehicle tracking if the client needs
the existing server-side simulation and event format. Authenticate with the Clerk session JWT via the `bearer` subprotocol (never a query param):

```js
const wsBase = import.meta.env.VITE_API_BASE_URL.replace(/^http/, 'ws');
const ws = new WebSocket(`${wsBase}/tracking/ws`, ['bearer', clerkSessionJwt]);
```

Supabase Realtime can be introduced later for database change notifications, but
it does not automatically replace the route/dispatch logic in FastAPI.

## 9. Production checklist

- [ ] Create staging and production Supabase projects.
- [ ] Enable PostGIS in both projects.
- [ ] Use Alembic migrations (`0001_initial_schema`, `0002_demo_scope` for `ride_mode`/`demo_run_id`); do not depend on automatic table creation.
- [ ] Decide UUID migration versus integer-to-UUID mapping (current `users.id` is integer + unique `clerk_user_id` text).
- [ ] Migrate login/signup to Clerk (already wired: dual-portal + `publicMetadata` sync via `CLERK_SECRET_KEY`).
- [ ] Verify Clerk JWTs in FastAPI and load roles from server-side profiles.
- [ ] Add RLS policies or keep tables inaccessible to direct browser queries.
- [ ] Keep the no-mock-fallback posture: surface API errors instead of fake success.
- [ ] Keep WebSocket `bearer`-subprotocol auth and reconnect handling (`hooks/useWebSocket.js`).
- [ ] Set production CORS origins (`ALLOWED_ORIGINS`) + `CLERK_AUTHORIZED_PARTIES` to the public `https://` domain and HTTPS/WSS URLs.
- [ ] Store secrets in the deployment provider, not Git (`CLERK_SECRET_KEY` lives in `backend/.env` / `backend/.env.example` — set a real value wherever `publicMetadata` sync is needed; the backend must be restarted to pick it up).
- [ ] Run backup/restore and migration tests before switching production traffic.

## Official references

- [Supabase database connection options](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase database extensions](https://supabase.com/docs/guides/database/extensions)
- [Clerk + Supabase integration](https://clerk.com/docs/guides/development/integrations/databases/supabase)
- [Clerk session tokens](https://clerk.com/docs/guides/sessions/session-tokens)
- [Supabase database security and RLS](https://supabase.com/docs/guides/database/overview)
