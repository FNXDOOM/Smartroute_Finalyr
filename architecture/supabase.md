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

The current frontend is not fully production-wired to the backend:

- `frontend/src/services/api.js` falls back to fake rides, vehicles, analytics,
  and history when requests fail.
- `AuthContext.jsx` currently creates mock users and mock JWTs when login fails;
  this must be removed when Clerk is enabled.
- Notifications and trip history pages render hard-coded mock data.
- `updateProfile()` only updates React state; it does not call `/auth/me`.
- `useVehicleTracking.js` connects without the backend-required `token` query
  parameter, so the WebSocket is rejected with code `4401`.
- `RideBooking.jsx` creates a payload shape that must be converted to the
  backend's required `pickup_lat`, `pickup_lng`, `dest_lat`, and `dest_lng`
  fields before calling `/rides/request`.

Before production, remove silent fake-success fallbacks. Show an error state
when FastAPI or Supabase is unavailable so failed bookings cannot look
successful.

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
the existing server-side simulation and event format. Construct its URL with the
Supabase access token:

```js
const wsBase = import.meta.env.VITE_API_BASE_URL.replace(/^http/, 'ws');
const ws = new WebSocket(`${wsBase}/tracking/ws`, ['bearer', accessToken]);
```

Supabase Realtime can be introduced later for database change notifications, but
it does not automatically replace the route/dispatch logic in FastAPI.

## 9. Production checklist

- [ ] Create staging and production Supabase projects.
- [ ] Enable PostGIS in both projects.
- [ ] Use Alembic migrations; do not depend on automatic table creation.
- [ ] Decide UUID migration versus integer-to-UUID mapping.
- [ ] Migrate login/signup to Clerk.
- [ ] Verify Supabase JWTs in FastAPI and load roles from server-side profiles.
- [ ] Add RLS policies or keep tables inaccessible to direct browser queries.
- [ ] Remove frontend mock-success fallbacks.
- [ ] Add the WebSocket JWT query token and reconnect handling.
- [ ] Set production CORS origins and HTTPS/WSS URLs.
- [ ] Store secrets in the deployment provider, not Git.
- [ ] Run backup/restore and migration tests before switching production traffic.

## Official references

- [Supabase database connection options](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase database extensions](https://supabase.com/docs/guides/database/extensions)
- [Clerk + Supabase integration](https://clerk.com/docs/guides/development/integrations/databases/supabase)
- [Clerk session tokens](https://clerk.com/docs/guides/sessions/session-tokens)
- [Supabase database security and RLS](https://supabase.com/docs/guides/database/overview)
