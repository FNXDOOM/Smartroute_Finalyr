# Carpool: implementation and verification notes

This is the consolidated carpool document. It replaces the earlier QA plan,
QA report, and matching regression notes with one current record. It describes
the system as implemented and separates fixed defects from workflows that the
product deliberately does not support.

## 1. Scope and product boundary

The product performs **pre-dispatch pooled ride allocation**, not dynamic
mid-journey insertion. `carpool_matching.attach_to_existing_run` and
`carpool_lifecycle.run_is_open_to_riders` close membership at driver
acceptance; `architecture/algorithms.md` documents that policy. "Join a ride
already in progress" is therefore a missing product workflow, not a bug in an
existing insertion evaluator.

## 2. Architecture under test

- React 19 / Vite 8 frontend: passenger, driver, and admin views; Axios client;
  MapLibre map; WebSocket hook; Razorpay checkout.
- FastAPI HTTP/WebSocket backend, SQLAlchemy ORM, Alembic, and worker dispatch jobs.
- Production PostgreSQL/PostGIS. All SQLite results below are from dedicated
  scratch databases, never configured customer data.
- Clerk web authentication and local JWT/mobile authentication; database roles
  and active-driver status gate access.
- Stadia geocoding, routing, matrix, and map matching; OSMnx road graph fallback;
  NetworkX distances; H3 partitioning; HDBSCAN/DBSCAN clustering; OR-Tools PDP
  and Hungarian vehicle assignment.
- `RideRequest` is an individual booking; `RoutePlan` is a vehicle itinerary;
  waypoints hold booking IDs; `VirtualStop` groups pickups. There is no
  independent multi-seat reservation model.
- Notifications are persisted and exposed over authenticated WebSockets;
  tracking broadcasts use per-user visibility filtering.

## 3. Implemented behavior and constraints

- Shared runs require two to three riders and cap occupancy at three. A lone
  shared rider is not dispatched as a shared run.
- PDP supports ordered intermediate pickups/drop-offs, separate rider states,
  and signed capacity across route segments. It does not model individual
  maximum delay, pickup windows, or road-travel-time insertion budgets.
- Matching uses geometric corridor/destination filters before PDP and checks
  directed road distances when a matrix is available. The 7,000 m destination
  gate that skipped road checks for distant corridors (production rides 35/36)
  was removed from new-pool matching and pre-acceptance insertion.
- Feasible orders allow interleaved pickup/drop-off chains with genuine shared
  travel. Requiring all pickups before all drop-offs was corrected.
- Road matrices fail closed for outages, disconnected pairs, and invalid
  provider distances. PDP/CVRP return `routing_unavailable` with no routes;
  private route construction also checks a road matrix before assignment.
  A working OSM matrix is an allowed fallback to Stadia.
- Fare computation is server-side in `services/razorpay_service.py`. This is
  not segment-level shared-fare settlement or automatic cancellation refunds.

## 4. Fixes already delivered

### Lifecycle and routing

- **QA-001 — survivor's live route disappears (fixed).** Passenger route lookup
  required `solved` while cancellation sets `needs_reoptimization`. Both route
  lookups now use `LIVE_ROUTE_STATUSES`. This exposes the existing plan; it does
  not calculate a new road itinerary.
- **QA-002 — onboard rider detaches via status PATCH (fixed).** Generic forward
  ordering allowed `in_progress` to `cancelled`. That transition is now rejected
  before mutation, matching the DELETE guard.
- **QA-003 — unverified routing during outage (fixed).** Road matrices now fail
  closed for outages/disconnected pairs/invalid distances; no unverified
  assignment is produced. If road services are unavailable, no assigned route
  is created, including presentation runs. No hidden simulation bypass exists.
- **QA-004 — generic PATCH bypasses boarding (fixed).** Shared-ride generic PATCH
  can no longer advance arrival/readiness/boarding/completion, for drivers or
  admins. Dedicated lifecycle endpoints enforce stage prerequisites; private
  manual controls remain separate.

### Matching and dispatch regressions

- Greedy splitting no longer strands a singleton: the remaining rider borrows
  from a triple only if both pairs pass policy.
- Local-pickup and corridor checks now use the same directed road distances and
  every rider's budget.
- Late insertion uses road detours rather than the old 150 m straight-line
  rejection; it rejects private requests and cannot eject existing passengers.
- Matrix denial has a bounded road fallback in both matching and the solver.
- Dispatch enforces 2–3 riders per used carpool vehicle plus physical capacity.
- The final solver applies the same 45% / 5 km detour limits as matching.
- Worker cadence defaults to a configurable five-second start-to-start interval
  (minimum two seconds); ticks never overlap. It is a polling interval, not a
  booking guarantee.
- Routing failures appear in job summaries and mark incomplete jobs `partial`;
  independently valid pools remain committed.
- Cancellations preserve accepted co-passenger progress. Worker and driver
  history reconcile legacy demotion only while the vehicle still owns the
  reservation; they never rewind onboard riders or free an unfinished ride.
- Driver history and navigation include both `solved` and
  `needs_reoptimization` live routes.
- Clustered riders bound to a live plan are excluded from fresh dispatch; an
  `idle` label cannot override an existing reservation. Cancel/expiry with a
  single clustered rider and no reservation returns the rider to searching.
- Private-ride completion closes its plan and releases the reservation.
- Automatic dispatch plans each verified pool independently with a bounded
  stop-order search. Map geometry loads on demand.
- Job summaries report `clustering_duration_ms` separately from
  `route_planning_duration_ms`, plus eligible `idle_vehicles` and
  `unassigned_clustered_rides` after planning. Matrix HTTP 403 triggers a
  one-minute per-process cooldown.
- Payment/concurrency follow-up: payment concerns and a pre-acceptance
  last-seat race were reproduced and fixed. See
  [`payment-concurrency-qa.md`](payment-concurrency-qa.md) and
  [`postgres-concurrency-qa.md`](postgres-concurrency-qa.md).

## 5. Scenario classification

The original TC01–TC35 matrix classified scenarios as PASS only for a named
implemented component contract, never as a full authenticated browser or
real-provider workflow. After the follow-up fixes, the classification was:
**6 PASS, 0 FAIL, 2 BLOCKED, 24 NOT IMPLEMENTED, 3 NOT RUN**; executed-contract
pass rate 6/6, **not full E2E coverage**.

NOT IMPLEMENTED takes precedence where a necessary workflow is absent. Dynamic
mid-run insertion, multi-seat requests, per-passenger delay budgets, no-show
timers, deviation recovery, refunds, and stale-GPS rejection remain absent or
incomplete. Exact Avalahalli place identity and road compatibility require real
provider verification; synthetic corridor coordinates are not geographic
evidence.

### Contract tests

- `tests/test_carpool_scenarios.py`: 2, 3, 4, 5, and 7 riders through both
  matching entry points; nested destinations; production 35/36 coordinates with
  synthetic roads; excessive detours; private-ride exclusion; overlapping
  chains; matrix denial and bounded fallback concurrency; solver detour bounds;
  fleet/capacity mixes; scheduler cadence.
- `tests/test_booking_concurrency.py`: full/accepted runs, private requests,
  excessive-detour insertion, curved-road insertion, and last-seat races.
- `tests/test_cluster_resilience.py`: partial failures preserve good pools;
  dedicated pickups never trigger graph downloads.
- `tests/test_reoptimization_recovery.py`: cancellation visibility, legacy
  repair, no double dispatch or onboard rewind, historical-assignment
  protection, and completion/release.
- `tests/test_carpool_dispatch_consistency.py`: 44 deterministic scenarios for
  pool backlogs, fleet sizes, stale/reoptimizing routes, hidden unassigned
  requests, failed pools, greedy pair repair, matrix denial recovery, and
  singleton requeue.
- `tests/test_carpool_qa_contracts.py` and `tests/test_carpool_lifecycle.py`:
  invalid coordinates, closed-run contract, segment capacity and reuse,
  oversized pickup rejection, and lifecycle regressions.

## 6. Verification evidence

- PostgreSQL validation for the selected concurrency/lifecycle scope:
  **67 passed**, recorded in [`postgres-concurrency-qa.md`](postgres-concurrency-qa.md).
- SQLite QA snapshots: 158 baseline; 168 passed with two expected failures at
  the time of the initial audit; 187 passed after the routing/PATCH fixes;
  212–213 passed during payment/concurrency work. Latest local full regression:
  **357 passed, 5 PostgreSQL-only skipped**, on a scratch SQLite database.
- Frontend lint and build passed at the time of the initial audit; the latest
  production build also passed. Bundle-size warning remains.
- Evidence files and scratch databases were kept in the approved temporary
  directory, not in the repository. No browser screenshots were captured;
  authenticated driver/passenger browser flows were not run.
- No live Stadia/geocoding request was executed for the named locations.
  Build/lint are not frontend synchronization evidence.

Reproduce the SQLite suite with a scratch database:

```powershell
$env:DATABASE_URL='sqlite:///C:/Users/gudiy/AppData/Local/Temp/opencode/carpool-audit.db'
$env:SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS='1'
py -m pytest tests/ -q -rx
```

Never point the test suite at `backend/.env` database data.

## 7. Remaining risks and next steps

- Verify deployed job summaries, real road routes for rides 35/36, and the
  recovered accepted route for rider 10. Confirm `clustering_duration_ms`,
  `route_planning_duration_ms`, eligible vehicle counts, and remaining counts.
- Run PostgreSQL concurrency QA for dispatch versus manual operations and an
  authenticated two-passenger/one-driver end-to-end flow.
- Decide the live-insertion policy before treating ongoing-join scenarios as
  bugs. Add isolated PostGIS concurrency/fault tests and resolve exact places
  through Stadia.
- Dynamic matching, time windows, per-passenger delay, multi-seat reservations,
  no-show, early drop-off, refunds, and GPS freshness/plausibility are still
  missing. Route `needs_reoptimization` may still carry old geometry.
- The `AUTO_DISPATCH_INTERVAL_SECONDS=5` default requires a single dispatch
  worker. No browser reconnection/synchronization or load/performance audit was
  performed.
- Overall assessment: suitable for continued development testing, not a
  completed dynamic carpooling product.
