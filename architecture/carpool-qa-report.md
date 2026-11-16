# Dynamic carpool QA report

PostgreSQL validation is now complete for the selected concurrency/lifecycle
scope: **67 passed**. See
[`postgres-concurrency-qa.md`](postgres-concurrency-qa.md), including a newly
fixed PostgreSQL initialization lock issue. Full SQLite regression: **213 passed,
5 PostgreSQL-only skips**. Earlier Docker-blocked statements below are historical.

Latest payment/concurrency work is recorded in
[`payment-concurrency-qa.md`](payment-concurrency-qa.md): payment concerns
reproduced and fixed, pre-acceptance last-seat race reproduced and fixed,
**212 backend tests passed**. PostgreSQL concurrency remains blocked; SQLite
race/rollback tests are not claimed as production-database validation.

## Follow-up fix verification — latest result

QA-003 and QA-004 are now **fixed**, not expected failures:

- Road matrices fail closed for outages, disconnected OSM pairs and invalid
  provider distances. PDP/CVRP return `routing_unavailable` with no routes.
  Private route construction also checks a road matrix before assignment.
  A working OSM road matrix remains an allowed fallback to Stadia.
- Shared-ride generic PATCH cannot advance arrival/readiness/boarding/completion,
  for either drivers or admins. Dedicated lifecycle endpoints enforce the
  passenger stage prerequisites. Private controls are unchanged; the current
  frontend already separates private manual controls from the shared-run UI.
- Former xfails are ordinary passing regressions. Added driver/admin transition
  cases, road direction/disconnection/invalid-distance tests and shared/private
  route-outage tests. Pipeline integration confirms outage leaves bookings
  clustered, zero assigned routes, and the vehicle unassigned. Explicit
  synthetic matrix fixtures replace tests' reliance on production fallback.
- Full regression: **187 passed, 0 failed, 0 xfailed**, 29.74 seconds.
  Scratch DB: `C:/Users/gudiy/AppData/Local/Temp/opencode/carpool-fixes-20261116.db`.
  Evidence: `carpool-fixed.xml` and `carpool-fixed.log` in the same directory.
- TC22/TC28 are now PASS for their documented component contracts. Updated
  35-case classification: **6 PASS, 0 FAIL, 2 BLOCKED, 24 NOT IMPLEMENTED,
  3 NOT RUN**; executed-contract pass rate 6/6 = 100%, **not full E2E coverage**.
- Compatibility change: unavailable road services no longer yield assigned
  routes, including presentation runs; configure Stadia/OSM for real routing.
  No hidden simulation bypass was introduced. An incomplete OSM matrix is
  conservatively refused, which may reject otherwise feasible directed routes.
- Still outstanding: dynamic mid-run insertion, real-provider geography,
  PostgreSQL concurrency/fault testing, full authenticated browser workflows,
  and separately identified payment/security review concerns.

The sections below preserve the **initial audit snapshot** and its pre-fix
observations for traceability; their open-defect statuses and expected-failure
counts are superseded by this follow-up verification.

## A. Project overview

Audit baseline: `f61092e`, clean `main` at start. Scope: supplied TC01–TC35
requirements and existing implementation, with two minimal lifecycle/API fixes.

### Architecture inspected

- React 19 / Vite 8 frontend, passenger/driver/admin views, Axios client,
  MapLibre map, WebSocket hook and Razorpay checkout component.
- FastAPI HTTP/WebSocket backend, SQLAlchemy ORM, Alembic, worker dispatch jobs.
- Production PostgreSQL/PostGIS; this execution used **SQLite only**.
- Clerk web authentication and local JWT/mobile authentication; database roles
  and active-driver status gate access.
- Stadia geocoding/routing/matrix/map matching, OSMnx road graph fallback,
  NetworkX distances, H3 partitioning, HDBSCAN/DBSCAN clustering, OR-Tools PDP
  and Hungarian vehicle assignment.
- `RideRequest` is the individual booking/journey; `RoutePlan` is the vehicle
  itinerary; waypoints hold booking IDs; `VirtualStop` groups pickups.
  Vehicles, users, tracking events, notifications and payments are separate
  models. No independent multi-seat reservation model was found.
- Notifications are persisted and exposed over authenticated WebSockets;
  tracking broadcasts use per-user visibility filtering.
- Existing tests use pytest, FastAPI TestClient in some modules, direct router/
  service invocation with real SQLAlchemy sessions in lifecycle tests, and
  deterministic payment/routing mocks. No installed frontend E2E test script.

### What exists versus the target

The existing product is **pre-dispatch pooled ride allocation**, not dynamic
mid-journey insertion. `carpool_matching.attach_to_existing_run` and
`carpool_lifecycle.run_is_open_to_riders` explicitly close membership at driver
acceptance. `architecture/algorithms.md:168–170` documents that policy.
Shared runs require at least two riders and cap occupancy at three, irrespective
of a four-seat example. A lone shared rider is not dispatched as a shared run.

PDP supports ordered intermediate pickups/drop-offs, separate rider states and
signed capacity across route segments. This does not establish atomic live seat
reservation, multi-seat requests, current-position insertion, passenger-specific
delay budgets, no-show timers, deviation recovery, refunds or stale-GPS rejection.
Those workflows are absent or incomplete. They were not silently implemented.

Matching uses geometric corridor/destination filters before PDP. Road matrices
are attempted, but failure falls back to haversine. PDP minimizes distance and
enforces pickup/delivery and load; it does not model individual maximum delay,
pickup windows or a road-travel-time insertion budget. Route enrichment is
best-effort and fallback duration assumes about 30 km/h.

Fare computation is server-side in `services/razorpay_service.py`; baseline fare,
option validation, signature checks, failure handling and repeated verification/
webhook behavior have existing tests. This is not segment-level shared-fare
settlement or an automatic cancellation-refund system.

## B. Test execution summary

**Interpretation:** PASS below is explicitly limited to the named implemented
component contract. No row asserts a full authenticated browser/real-provider
workflow. NOT IMPLEMENTED takes precedence where a necessary workflow is absent;
partial working components are described rather than represented as full passes.

| ID | Scenario / expected | Actual observation | Status | Severity |
|---|---|---|---|---|
| TC01 | Join ongoing Tin Factory–Hoskote ride | Membership closes on acceptance; exact Avalahalli identity and road relationship unverified | NOT IMPLEMENTED | High gap |
| TC02 | Shared pickup, independent destinations/fares | Generic pooled solver/lifecycle tests pass; exact named-road route and full fare/UI workflow not executed | BLOCKED | — |
| TC03 | Join ongoing run, same destination | Separate ride IDs exist; ongoing insertion prohibited | NOT IMPLEMENTED | High gap |
| TC04 | Reject unacceptable reverse-direction insertion | No live-insertion direction/delay evaluator; do not count blanket closure as correct matching | NOT IMPLEMENTED | High gap |
| TC05 | Reject pickup already passed | No current-position live-insertion evaluator | NOT IMPLEMENTED | High gap |
| TC06 | Three riders, intermediate handover | Pre-dispatch PDP exists; live insertion workflow absent | NOT IMPLEMENTED | High gap |
| TC07 | Two-seat plus one-seat reservation fills vehicle | Solver oversized-pickup rejection passes; request schema has no requested-seat count | NOT IMPLEMENTED | High gap |
| TC08 | Cancel before pickup during vehicle run | Cancellation and survivor completion tested; route remains needs_reoptimization, no verified automatic new itinerary; passenger map defect fixed | NOT IMPLEMENTED | High gap |
| TC09 | Cancel, release exactly once, update route/refund/UI | Status replay protected on PATCH; full refund/recalculation workflow absent | NOT IMPLEMENTED | High gap |
| TC10 | Accept small road detour within delay budgets | No road-based insertion/delay budget evaluator | NOT IMPLEMENTED | High gap |
| TC11 | Reject Electronic City detour | No implemented live detour decision; actual provider route not verified | NOT IMPLEMENTED | High gap |
| TC12 | Exactly one winner for last seat under concurrency | No real parallel last-seat reservation run; SQLite cannot establish production locking behavior | BLOCKED | Critical risk |
| TC13 | Enforce wait/no-show policy | No no-show timer/status workflow identified | NOT IMPLEMENTED | Medium gap |
| TC14 | Detect deviation/recalculate/preserve bookings | GPS/map matching exists; deviation-triggered recovery absent | NOT IMPLEMENTED | High gap |
| TC15 | Book future freed capacity mid-run | Synthetic solver frees/reuses seats correctly; live future booking absent | NOT IMPLEMENTED | High gap |
| TC16 | Duplicate request idempotency | No booking request idempotency field/workflow in request schema/router | NOT IMPLEMENTED | High gap |
| TC17 | Reject invalid coordinates | Six deterministic out-of-range/nonfinite schema cases reject; existing batch geofence regression passes | PASS | — |
| TC18 | Identical pickup/drop-off policy | No defined zero-length policy established; no end-to-end execution | NOT RUN | Policy ambiguity |
| TC19 | Reject multi-seat excess request | Requested-seat count not supported | NOT IMPLEMENTED | High gap |
| TC20 | Offline driver, stale location safety | No location freshness/expiry contract found | NOT IMPLEMENTED | High gap |
| TC21 | Reject delayed/out-of-order GPS | Telemetry schema/router has no sample-time ordering guard | NOT IMPLEMENTED | High gap |
| TC22 | Routing outage must not validate unverified route | Simulated Stadia and OSM absence still returns solved using haversine; QA-003 | FAIL | High |
| TC23 | Driver cancels whole run with notifications/refunds | Required coordinated whole-run financial cancellation workflow not established | NOT IMPLEMENTED | High gap |
| TC24 | Join completed run rejected | Closed-run predicates tested; specific join-existing-vehicle booking API/workflow absent | NOT IMPLEMENTED | High gap |
| TC25 | Full segment request rejected unless future capacity | Solver capacity tests pass; live segment reservation workflow absent | NOT IMPLEMENTED | High gap |
| TC26 | Co-located pickups grouped without duplicate navigation | Virtual-stop grouping exists; universal duplicate-stop normalization not implemented/validated | NOT IMPLEMENTED | Medium gap |
| TC27 | Same destination, independent completion | Existing lifecycle independence tests pass; exact co-located multiple-dropoff full scenario not run | NOT RUN | — |
| TC28 | Reject drop-off before pickup | Dedicated lifecycle guarded, but active assigned driver PATCH completes unboarded passenger; QA-004 | FAIL | High |
| TC29 | Payment failure preserves consistent payment state | Mock provider-order failure, retryable verify network error, webhook failure tests pass; no actual charge | PASS | — |
| TC30 | DB failure atomically rolls booking back | No injected booking-confirmation transaction failure executed | NOT RUN | Critical risk |
| TC31 | Revalidate stale match against current ride | Pre-acceptance plan recheck exists; live current-position stale-match confirmation workflow absent | NOT IMPLEMENTED | High gap |
| TC32 | Segment occupancy within capacity | Synthetic A→B→C→D PDP fixture asserts every segment load 0..2 and pickup before drop-off; not API reservation proof | PASS | — |
| TC33 | Reject other passenger's modification | Existing owner/role/assigned-driver and foreign-payment/route permission regressions pass; direct-router scope, not complete security audit | PASS | — |
| TC34 | Idempotent cancellation/refund | PATCH replay no-op tested; DELETE repeats notifications and refund workflow absent | NOT IMPLEMENTED | Medium gap |
| TC35 | Reject impossible GPS movements | No validated speed/jump plausibility workflow identified | NOT IMPLEMENTED | High gap |

### Execution evidence and reproducibility

Dedicated database:
`C:/Users/gudiy/AppData/Local/Temp/opencode/carpool-audit-20261116.db`.
Tests did not target configured customer data. Existing hermetic fixture blocked
outbound sockets. Auth actors were test records; no payment or map calls were live.
Normal tests create and clean their own ride/route records; some pre-existing
suite user records intentionally remain inside the scratch database.

PowerShell environment for every pytest run:

```powershell
$env:DATABASE_URL='sqlite:///C:/Users/gudiy/AppData/Local/Temp/opencode/carpool-audit-20261116.db'
$env:SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS='1'
py -m pytest tests/ -q -rx
```

Evidence files in the approved temporary directory:

- `carpool-baseline.xml`: 158 passed before changes, 38.57 seconds.
- `carpool-final.xml` / `carpool-final.log`: final regression summary.
- `carpool-open-defects.log`: `--runxfail` probe execution, **9 passed,
  2 failed**, including actual assertion traces for QA-003/QA-004.
- Frontend `npm run lint`: exit 0.
- Frontend `npm run build`: exit 0, 2,321 modules; map chunk approximately
  977 kB minified / 255 kB gzip, bundle-size warning.
  An initial parallel command failed to spawn PowerShell; the retry built
  successfully. This was a harness launch issue, not an app build failure.

No browser screenshots were captured: authenticated driver/passenger browser
flows were **NOT RUN**. Build/lint are not frontend synchronization evidence.
No real Stadia/geocoding request was executed, so exact Avalahalli remains
**BLOCKED** as geographic validation, not implicitly resolved from a name.

### Repeatable new case definitions

Common preconditions: scratch DB environment above; pytest dependencies installed;
outbound networking blocked. Tests reside in `tests/test_carpool_qa_contracts.py`
and `tests/test_carpool_lifecycle.py`. Pytest assertion output is the relevant log.
No browser applies to these component tests.

- **REG-QA-001 / TC08 partial:** fixture has two persisted shared riders; driver
  accepts, boards/departs A, B cancels. Read A's route, then drop A and close run.
  Expected same live accepted route with needs_reoptimization. Initially `None`;
  after fix route returned and independent completion succeeds. High, fixed.
- **REG-QA-002 / TC08 after-pickup safety:** same fixture; board/depart A, passenger
  A PATCHes cancelled. Expected HTTP 400 and unchanged status/stop. Initially no
  exception and rider detached; now rejected. High, fixed.
- **QA-TC17:** parametrize pickup/destination coordinates with 91, 181, -91,
  -181, NaN and infinity. Construct schema. Expected ValidationError for each;
  actual all reject. PASS, no bug.
- **QA-CLOSED-RUN / TC01 limitation:** accepted plan metadata, query membership
  predicate. Expected current product rejects. Actual false. Component PASS
  confirms missing target workflow, not successful dynamic pooling.
- **QA-TC32 / TC15 solver partial:** synthetic depot A, grouped pickup of two at
  A; one goes to C, one to B; another boards at B and leaves at D. Capacity 2.
  Matrix is deterministic haversine **mock**, not real road evidence. Solve,
  walk events and check precedence, bounded occupancy and final zero. PASS.
- **QA-TC07 solver partial:** same synthetic pickup demand increased to 3 with
  capacity 2 and consistent drop-off demand. Expected no_solution; actual
  no_solution. PASS at solver layer, not multi-seat API coverage.
- **QA-TC22:** mock both real matrix and OSM graph unavailable; solve synthetic
  pool. Expected no verified solved plan, actual solved. FAIL, QA-003 open.
- **QA-TC28:** persisted two-rider route, active assigned driver; directly PATCH
  unboarded rider to completed. Expected conflict, actual succeeds. FAIL,
  QA-004 open. Role/driver-status fixture mutations restored in cleanup.

Other evidence is the existing named regression suite, including
`test_carpool_lifecycle_walks_every_stage_then_completes`,
`test_pool_solver_boards_before_dropping_and_leaves_the_route_open`,
`test_pool_solver_reuses_a_seat_after_a_drop_off_where_cvrp_cannot`,
`test_the_owner_can_still_cancel_and_replays_are_no_ops`,
`test_only_the_assigned_driver_can_patch_a_riders_status`,
and payment failure/signature/repeated-callback tests in `test_payments.py`.
These passing components do not upgrade unexecuted full scenarios.

## C. Bugs found

### QA-001 — survivor's live route disappears (High, fixed)

Related: TC08/TC09 frontend-backend synchronization.
Reproduce REG-QA-001 above. Expected survivor keeps route access; actual response
was null. Root cause: passenger endpoint's two queries required solved while
cancellation sets needs_reoptimization, already considered live by driver paths.
Source: `backend/routers/rides.py:get_ride_route`.
Fix: both route lookups use existing LIVE_ROUTE_STATUSES. Regression failed
before fix, passed after fix. This exposes the existing plan with its pending
reoptimization status; it does not calculate a new road itinerary.

### QA-002 — onboard rider can detach via status PATCH (High, fixed)

Related: TC08 after-pickup cancellation/safety.
Reproduce REG-QA-002. Expected same refusal as DELETE, actual PATCH accepted and
detached rider. Root cause: generic forward status ordering treated cancellation
as legal after in_progress; DELETE had a separate onboard guard.
Source: `backend/routers/rides.py:update_ride_request_status`.
Fix: reject in_progress→cancelled before mutation. Regression failed before fix,
passed after fix. Intentional compatibility change: callers using this bypass
now receive HTTP 400. Safe early drop-off remains a missing workflow.

### QA-003 — unverified routing accepted during outage (High, open)

Related: TC22/road compatibility. Reproduce QA-TC22. Expected refusal of a
route-dependent assignment without verified road reachability; actual solver
returns solved. Root cause: `vrp_solver.build_road_distance_matrix` returns a
haversine matrix if road graph unavailable; PDP accepts it without provenance/
verification gating, and builder enrichment is optional.
Recommendation: propagate matrix provenance/unreachable arcs and fail closed for
real assignments while explicitly permitting deterministic demo simulations.
This changes a documented fallback policy and needs coordinated caller behavior;
not bundled into the minimal lifecycle fix. Strict xfail regression remains;
`--runxfail` reproduces actual failure.

### QA-004 — generic PATCH bypasses boarding (High, open)

Related: TC28. Reproduce QA-TC28. Expected conflict before pickup, actual driver
sets unboarded rider completed. Root cause: monotonic coarse status comparison
does not enforce the fine-grained CarpoolRun stage ladder.
Source: `backend/routers/rides.py:update_ride_request_status` versus
`backend/services/carpool_lifecycle.py:CarpoolRun._hop`.
Recommendation: enforce lifecycle prerequisites on generic writes or require
dedicated lifecycle endpoints, checking existing driver UI compatibility first.
Strict xfail regression remains; `--runxfail` reproduces actual failure.

### Source-review concerns, not runtime-confirmed bugs

Payment checkout computes using caller-supplied option rather than binding it to
stored ride option; invalid verify signatures mark the provider order failed,
potentially enabling a new order before delayed reconciliation. These require
dedicated reproductions before production changes. Driver request-list scope
and WebSocket identity revalidation also merit security/product review. No
financial exploitation or token-expiry scenario was executed here.

## D. Code changes

- `backend/routers/rides.py`: `get_ride_route` live-status filters;
  `update_ride_request_status` onboard cancellation guard. No schema migration,
  new endpoint, fare rule or algorithm replacement.
- `tests/test_carpool_lifecycle.py`: strengthen survivor-route assertion; add
  onboard cancellation regression.
- `tests/test_carpool_qa_contracts.py`: six invalid-coordinate parameter cases,
  closed-run contract, capacity/reuse and oversized-pickup tests; two strict
  xfails documenting open defects.
- `architecture/carpool-qa-plan.md`, this report: scope, execution and limitations.

Compatibility: route endpoint now returns live pending-reoptimization plans
instead of null; clients must read route_status rather than infer recalculation.
Onboard cancellation PATCH now returns the existing DELETE-style refusal.
No existing business rule enabling mid-run joins was introduced.

## E. Coverage

35 requested scenario classifications:
**4 PASS, 2 FAIL, 2 BLOCKED, 24 NOT IMPLEMENTED, 3 NOT RUN, 0 NOT APPLICABLE.**

Executed scenario contracts = PASS + FAIL = 6.
Pass rate = 4 / 6 × 100 = **66.67%**, limited to the adapted component contracts
explicitly stated in the table. This is **not** an end-to-end product pass rate.
The other 29 scenarios are not counted as executed successes or failures.

Separately, automated regression suite: **168 passed, 2 expected failures**.
Expected failures represent known unresolved requirement failures, not passes.
Baseline: 158 passed. Eleven new collected cases plus one strengthened existing
case. No line/branch coverage percentage was measured. No production-database
concurrency or complete browser E2E coverage was measured.

## Standards

Two independent read-only reviewers assessed this session's uncommitted changes,
not a historical branch comparison. No documented coding-standard violation
established. Review caught fixture role/status restoration and overly broad
expected-error handling; corrected by restoring both actor fields, checking
HTTP 409 specifically and limiting xfail to assertion failures. Possible
cross-test helper coupling remains a maintainability heuristic, not a hard rule.

## Spec

Review confirmed the two production fixes match the intended lifecycle behavior
without architecture replacement. Isolated DB execution is explicitly supplied,
not inferred from the existing fixture. Full dynamic insertion and unavailable
external/browser workflows remain partial/missing and are not labeled passed.
No originating tracker was supplied; `/setup-matt-pocock-skills` can configure
one if a tracker-backed review is wanted. No user comparison ref was supplied,
so a formal `git diff <ref>...HEAD` review remains unperformed.

Review summary: Standards: 0 hard violations, 1 remaining coupling heuristic;
Spec: 0 identified defects in the two targeted fixes, incomplete target-product
coverage explicitly documented.

## F. Remaining risks

- High-severity QA-003/004 still open; source-review payment/security concerns
  need deterministic reproduction.
- Missing dynamic matching, time windows, per-passenger delay, multi-seat
  reservations, no-show, early drop-off, refunds and GPS freshness/plausibility.
- PostgreSQL/PostGIS tests, real concurrent booking races/retries and DB fault
  injection not executed. Mock payment race tests are not booking race evidence.
- Exact Tin Factory/KR Puram/Avalahalli/Hoskote road compatibility unverified;
  no arbitrary coordinates were substituted as evidence.
- Authenticated browser maps, reconnection, driver/passenger synchronization
  and real provider contracts need controlled staging credentials/fixtures.
- Route marked needs_reoptimization may still carry old geometry; retaining
  access does not establish correct navigation after cancellation.
- Bundle-size warning; no load/performance audit or measured production capacity.
- Existing suite uses shared scratch users and a one-second solver budget;
  results are not solver-quality or production-scale guarantees.

## G. Final assessment

Suitable for **continued development testing**, not production consideration
as the specified dynamic carpooling system. Existing pre-dispatch pooling and
many component contracts have useful passing coverage, but the primary ongoing
join workflow is deliberately absent and important safety failures remain.
Next: decide the live-insertion policy, resolve QA-003/004, add isolated PostGIS
concurrency/fault tests, resolve exact places through Stadia, then run full
authenticated driver/passenger browser workflows in controlled staging.
