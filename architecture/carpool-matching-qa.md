# Carpool matching regression checks

## Scope

These are deterministic synthetic-road and scratch-SQLite tests, not claims about
live Stadia access, real Bengaluru road times, or PostgreSQL concurrency.
Existing booking-race tests remain in the suite; PostgreSQL-only tests are skipped
when no local PostgreSQL test database is supplied.

## Reproduced and fixed

- Four/seven compatible riders were greedily split into `3 + 1` / `3 + 3 + 1`.
  The remaining singleton now borrows from a triple only if both pairs pass policy.
- The local-pickup pass used a different, asymmetric straight-line predicate from
  the corridor pass. Both now use directed road distances and every rider's budget.
- Production rides 35/36 exposed a remaining destination-radius gate: their
  destinations are 7,814 m apart, so the 7,000 m gate skipped all road checks.
  Removed that gate from new-pool matching and pre-acceptance insertion. Long
  nested corridors now use the same per-rider detour limits as shorter trips.
  Exact-coordinate regressions use synthetic roads; actual provider compatibility
  is still evaluated at runtime, not assumed from pickup labels.
- Requiring all pickups before all drop-offs rejected overlapping chains of trips.
  Feasible orders now allow interleaving, with pickup-before-drop-off and genuine
  shared travel (not just boarding at somebody else's exact drop-off coordinate).
- Late insertion still used the old 150 m straight-line corridor rejection. It now
  uses road detours, rejects private requests, and cannot eject existing passengers.
- Matrix denial had a route fallback in matching but not in the dispatch solver.
  Small solves (at most eight unique points) can now use the same road fallback.
- Seat occupancy alone let dispatch exceed the three-rider-per-run policy.
  Dispatch now enforces 2–3 total riders per used carpool vehicle, plus physical
  capacity. Four riders/two vehicles dispatch as pairs; excess demand may wait.
- The final solver did not enforce individual detour limits. It now uses the same
  45% / 5 km limits as matching.
- Each worker tick slept a full minute after finishing. The default is now a
  configurable five-second start-to-start cadence; ticks never overlap.
- Dedicated pickup creation unnecessarily fetched OSM road graphs. These stops
  retain the requested coordinates; driving routes still require road verification.
- Standard-route fallbacks were sequential and repeated across checks. They now
  use four concurrent requests, deduplicate directed edges within the tick, and
  stop retrying failed matrix calls during that tick. Provider caches still apply.
- Routing failures now appear in job summaries and mark incomplete jobs `partial`,
  while independently valid pools remain committed. Summaries include clustering
  duration, matrix attempts, route attempts, and routing failures.
- A production vehicle was reserved by accepted route `route-1-97f5f08b`, with
  status `needs_reoptimization` and rider 10 incorrectly demoted to `clustered`.
  Cancellations now preserve accepted co-passenger progress. The worker and driver
  history reconcile the legacy demotion only while the vehicle still owns that
  reservation; they never rewind onboard riders or free an unfinished ride.
- Driver history and map navigation now include both live route states. A plan
  requiring reoptimization no longer disappears while still reserving a vehicle.
- Clustered riders bound to a live plan are excluded from fresh dispatch. An
  `idle` label cannot override an existing reservation. The frontend refreshes
  backend availability after cancellation instead of marking a shared car idle.
- Private-ride completion also closes its plan and releases the reservation on
  the backend, so safe reservation checks do not strand completed private trips.

## Scenario coverage

`tests/test_carpool_scenarios.py`:

- 2, 3, 4, 5, and 7 compatible riders through both matching entry points.
- Nested destinations in either booking order.
- Production 35/36 coordinates with synthetic nested-road distances, in both
  arrival orders and matching entry points; distant destinations with excessive
  road detours still fail; later riders can continue farther along the corridor.
- Nearby pickups requiring excessive road detours.
- Private-ride exclusion; opposite-direction/disjoint/short-trip incompatibility.
- Overlapping chains that require an early drop-off.
- Matrix denial, bounded fallback concurrency, cache reuse and routing failures.
- Dispatch fallback without OSM, pickup/drop-off precedence, solver detour bounds.
- Four riders with two vehicles versus one; one-seat vehicle exclusion.
- Scheduler delay subtracts work time.

`tests/test_booking_concurrency.py` additionally covers full/accepted runs, private
requests, excessive-detour insertion, curved-road insertion and last-seat races.
`tests/test_cluster_resilience.py` verifies partial failures preserve good pools
and dedicated pickups never trigger graph downloads.

`tests/test_reoptimization_recovery.py` verifies accepted/pre-acceptance
cancellation visibility, legacy repair and idempotency, worker reconciliation,
no double dispatch or onboard rewind, historical-assignment protection, and
completion/release with a single surviving rider or a private trip.

`tests/test_carpool_dispatch_consistency.py` adds 44 deterministic scenarios:
pool backlogs of up to 12, multiple fleet sizes and capacities, stale and
reoptimizing routes, hidden unassigned requests, failed and undersized pools,
greedy pair repair, real shared travel, matrix denial recovery, and singleton
requeue with and without a new partner.
Automatic dispatch now plans each verified pool independently with a bounded
stop-order search instead of solving across unrelated pools. Map geometry is
loaded on demand. The driver and passenger views use the vehicle's current
reservation to distinguish a real offer from pending matching.
If cancellation or expiry leaves a single clustered rider without a live
reservation, the rider returns to searching and can match a new partner.

Job summaries report `clustering_duration_ms` separately from
`route_planning_duration_ms` (when planning ran), plus eligible `idle_vehicles`
and `unassigned_clustered_rides` after planning. Matrix HTTP 403 responses
trigger a one-minute per-process cooldown; valid standard road routes are
still used and the provider is probed again after the cooldown.

## Operational notes

`AUTO_DISPATCH_INTERVAL_SECONDS=5` is the default; minimum is two seconds.
It is a polling interval, **not** a five-second booking/assignment guarantee.
Routing latency, solver work, lack of compatible riders and driver availability
still affect end-to-end wait time. Only one dispatch worker is supported.

No production booking data or provider credentials are needed for this suite.
Verify deployed job summaries and real-road end-to-end timing after deployment
before claiming a measured production latency improvement.

The reservation recovery does **not** cancel or complete rider 10. Once deployed,
the driver must finish the recovered ride or the passenger/admin must explicitly
cancel it before that vehicle can take another run.
