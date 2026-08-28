# SmartRouteAI frontend

The frontend is a React/Vite application using MapLibre GL for passenger,
driver, and admin maps. FastAPI remains the owner of ride operations, route
optimization, authentication, and live tracking WebSockets.

## Run locally

```bash
npm install
npm run dev
```

If Vite reports a missing `maplibre-gl-worker.mjs` file, force dependency
re-optimization:

```bash
npm run dev -- --force
```

## Environment

Copy `.env.example` to `.env`:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_API_BASE_URL=http://127.0.0.1:8000
```

The frontend sends geocoding, road snapping, route, matrix, map, and
map-matching requests to FastAPI. Put the Stadia key only in `backend/.env` as
`STADIA_API_KEY`; it must never be placed in a `VITE_*` variable because Vite
publishes those values in the browser bundle.

The map is Stadia-only and requires `STADIA_API_KEY` in `backend/.env`; it does
not fall back to another tile provider. Do not put database passwords, Clerk
secret keys, or Supabase service-role keys in this file; all `VITE_*` values
are exposed to the browser.

## Build and verify

```bash
npm run build
npm run lint
```

The production build should pass. Existing lint findings in legacy view code
may still require separate cleanup.
