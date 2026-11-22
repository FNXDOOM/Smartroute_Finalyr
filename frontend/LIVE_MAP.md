# Fleet map demo

## Production passenger tracking

Set `VITE_PASSENGER_ROUTE_ANIMATION=true` in `frontend/.env.local` for a local
test, or in the repository's GitHub Actions variables before a production
build. This is a build-time flag: disable it and rebuild to restore the
original tracking renderer. It defaults to off. Open an active ride and
select **Live ride tracking** to test the authenticated feed and route trail.
Stored pooled routes support snapping and trail progress; rides without a
stored route glide between fixes without snapping to the booking preview.
The standalone demo and synthetic WebSocket are local only.

## Standalone demo

Install the existing frontend dependencies from `frontend` with `npm ci`; no additional
NPM packages are needed. Run `npm run dev -- --port 5173 --strictPort` and open
`http://localhost:5173/live-map.html`. No Clerk key is needed for this page.
Simulation mode needs an internet connection for OpenFreeMap and OSRM.

For Live mode, in a second terminal at the repository root, install
`fastapi` and `uvicorn[standard]` in your Python environment, then run
`python -m uvicorn backend.vehicle_demo:app --host 127.0.0.1 --port 8000`.
On Windows, use `py -3.10` in place of `python` if needed. Toggle **Live mode**.
The demo feed uses synthetic waypoints, not production telemetry, and needs no
database. It sends an array of fixes every two seconds and includes route
geometry on first connection and whenever the trip revision changes.

The public OSRM demo is not for production fleet traffic. Requests are paced;
the 50-vehicle simulation loads trips progressively. Swap the routing provider in
`src/map/routeUtils.js` before using this at scale. Show only the selected trail
by default to limit MapLibre worker traffic; enable **Show all trails** to compare.

## Tuning

1. `SPEEDS` sets cruise speed in metres per second by vehicle type.
2. `setSpeed(mps)` overrides cruise speed for one animator.
3. `RAMP_METRES` controls the acceleration and braking distance per leg.
4. `TURN_RATE` controls heading smoothing; a higher value turns faster.
5. `STOP_SECONDS` is the simulation dwell at pickup and drop-off.
6. `GLIDE_SECONDS` controls how long an accepted GPS fix takes to reach.
7. `MAX_JUMP` limits GPS movement between accepted fixes, in metres.
8. `SNAP_METRES` limits how far off-route a fix can be before rejection.
9. `INTERVAL` and `STOP` control demo WebSocket cadence and server-side dwell.
10. The `250` ms sidebar interval controls React updates independently of map animation.
