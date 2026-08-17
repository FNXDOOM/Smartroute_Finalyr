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
VITE_STADIA_API_KEY=your_stadia_key
VITE_GEOCODER_PROVIDER=stadia
VITE_ROUTER_URL=https://api.stadiamaps.com/route/v1
VITE_ROUTER_ENGINE=valhalla
```

Stadia hosts the Valhalla routing engine, so no Valhalla process or map tiles
are required on the VPS. The frontend sends route validation and ETA requests
to Stadia using `VITE_STADIA_API_KEY`. Restrict the Stadia key to your
production domains in the Stadia dashboard because `VITE_*` values are
visible in the browser.

For local demos, `VITE_STADIA_API_KEY` may be omitted. The app then uses a
CARTO raster fallback through MapLibre, but Stadia geocoding and Valhalla
routing will be unavailable.

`VITE_MAP_STYLE_URL` can override the default Stadia/MapTiler style URL. Do not
put database passwords, Clerk secret keys, or Supabase service-role keys in
this file; all `VITE_*` values are exposed to the browser.

## Build and verify

```bash
npm run build
npm run lint
```

The production build should pass. Existing lint findings in legacy view code
may still require separate cleanup.
