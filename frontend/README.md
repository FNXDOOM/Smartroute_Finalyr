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
VITE_ROUTER_URL=http://localhost:8002
VITE_ROUTER_ENGINE=valhalla
```

For local demos, `VITE_STADIA_API_KEY` may be omitted. The app then uses the
Photon geocoder and a CARTO raster fallback through MapLibre. MapTiler is an
alternative: set `VITE_MAPTILER_KEY` and use
`VITE_GEOCODER_PROVIDER=maptiler`.

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
