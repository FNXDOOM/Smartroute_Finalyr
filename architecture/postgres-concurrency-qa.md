# PostgreSQL concurrency validation

## Result

**67 PostgreSQL/PostGIS tests passed, zero failures** in 13.55 seconds.
The PostgreSQL availability blocker is resolved for this tested scope.

Full SQLite regression: **213 passed, 5 skipped** in 36.08 seconds. The five
skips are explicitly PostgreSQL-only parallel checkout tests, which passed in
the PostgreSQL run. These numbers describe separate runs, not additive coverage.

## Isolation and environment

- Docker engine: 29.1.3.
- Dedicated container: `smartroute-qa-postgis-20261116`.
- Image: `postgis/postgis:16-3.4`.
- Verified server: PostgreSQL **16.4**, PostGIS **3.4.3**.
- Verified transaction isolation: **READ COMMITTED**.
- Dedicated database/user: `carpool_qa`; published only on
  `127.0.0.1:64825` for this run.
- Data directory was tmpfs; container was created with `--rm`.
- Trust authentication was confined to this disposable local test container;
  no production credentials were requested or used.
- No application database, existing container or named volume was modified.
- Outbound network remained blocked by pytest. Routing and Razorpay calls were
  deterministic mocks; PostgreSQL transactions, locks and constraints were real.
- Container is stopped/automatically removed after testing; its database is
  intentionally ephemeral. Logs and JUnit results persist outside the container.

## Tests executed on PostgreSQL

Files:

- `tests/test_booking_concurrency.py` — 13 tests: real compatible pre-acceptance
  allocation, five distinct-request races, five duplicate-booking-ID races,
  sequential retry and rollback.
- `tests/test_postgres_payment_concurrency.py` — 5 new PostgreSQL-only tests.
  Each uses two threads with independent sessions and the actual payment
  partial unique index; the mock provider creates distinct IDs. Both responses
  must converge on one persisted payment and attached order.
- `tests/test_carpool_lifecycle.py`
- `tests/test_ride_status_transitions.py`
- `tests/test_shared_ride_routing.py`
- `tests/test_schema_backfill.py`

Booking race assertions check exactly one winner, exactly one solved replacement
plan, three roster members, one allocated candidate and correct pickup counts.
Rollback now injects an actual NOT NULL violation during replacement-plan
persistence, after the source-plan claim. Caller rollback must restore the
original solved route and pending/unbound candidate.

The full heterogeneous pytest suite was not labeled a PostgreSQL run:
several older test modules intentionally own SQLite-only lightweight databases.
The files listed above are the PostgreSQL-native validation scope.

## Additional defect found and fixed

**PG-001 — PostgreSQL schema initializer waits on its own DDL locks (High).**

The first PostgreSQL run timed out before test execution. Inspection of
`pg_stat_activity` and `pg_blocking_pids` identified:

- PID 201 held uncommitted DDL locks and waited for the client.
- PID 202 ran column reflection and was blocked by PID 201.

Root cause: `create_db_tables` opened a DDL transaction while its SQLAlchemy
Inspector was bound to the Engine. Reflection therefore checked out a different
connection, which could not read schema metadata locked by our transaction.

Fix: bind the Inspector to the same active DDL connection.
Source: `backend/database.py:create_db_tables`.
No schema redesign or destructive migration was introduced.

Regression-first test:
`test_postgres_backfill_reflects_on_its_ddl_connection` failed before the fix and
passed afterward. The subsequent real PostgreSQL initialization and all 67
selected tests completed successfully. Statement and lock timeouts were set to
20 and 10 seconds respectively during the final PostgreSQL test run.

## Evidence

Files in `C:/Users/gudiy/AppData/Local/Temp/opencode/`:

- `postgres-booking-concurrency.xml` / `.log` — initial successful 13-test run.
- `postgres-concurrency-final.xml` / `.log` — final 67-test PostgreSQL run.
- `postgres-followup-sqlite.xml` / `.log` — full SQLite regression.

The timed-out initial test process was explicitly stopped before rerunning.
Only the test process/container created for this task was stopped.

## Reproduction

Create a new dedicated PostgreSQL/PostGIS test container; never substitute the
application's configured database. Set its loopback URL and execute:

```powershell
$env:DATABASE_URL='postgresql://carpool_qa@127.0.0.1:<test-port>/carpool_qa'
$env:PGOPTIONS='-c statement_timeout=20000 -c lock_timeout=10000'
$env:SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS='1'
py -m pytest tests/test_booking_concurrency.py tests/test_postgres_payment_concurrency.py tests/test_carpool_lifecycle.py tests/test_ride_status_transitions.py tests/test_shared_ride_routing.py tests/test_schema_backfill.py -q
```

## Remaining limits

This validates the existing pre-acceptance booking race and checkout race at
READ COMMITTED. It does not establish production readiness, load capacity,
all isolation levels, distributed dispatch, driver-accept/rebuild races, payment/
webhook races, live provider integration or authenticated browser behavior.
No dynamic mid-journey insertion or real financial transaction was performed.
PostgreSQL is no longer unavailable, but these broader scenarios remain future
work rather than implicitly passed tests.
