# Payment and booking concurrency follow-up

**Update:** the Docker blocker has been resolved. See
[`postgres-concurrency-qa.md`](postgres-concurrency-qa.md): **67 PostgreSQL/
PostGIS tests passed**, including real parallel booking/checkout and constraint-
failure rollback. Full SQLite regression is now **213 passed, 5 PostgreSQL-only
skips**. The environment blocker described below is historical.

## Outcome

**212 backend tests passed, no failures or expected failures** (34.18 seconds).
This includes 48 payment tests and 13 pre-acceptance booking tests.
Dynamic mid-run insertion was not implemented.

All provider payment calls were deterministic mocks. No real payment orders,
charges or refunds were made. SQLite databases were dedicated test files;
existing configured application data was not used.

Evidence:

- `C:/Users/gudiy/AppData/Local/Temp/opencode/payment-concurrency-final.xml`
- `C:/Users/gudiy/AppData/Local/Temp/opencode/payment-concurrency-final.log`
- Scratch DB:
  `C:/Users/gudiy/AppData/Local/Temp/opencode/payment-concurrency-audit.db`
- Parallel checkout tests additionally use fresh per-test SQLite files with
  the actual `uq_payments_one_active_per_ride` partial unique index.

## Reproduced payment defects and fixes

| ID | Severity | Reproduction / observed before fix | Fix |
|---|---|---|---|
| PAY-001 | High | Book Lux, request Moto checkout: cheaper order accepted | Linked checkout must match the persisted valid ride tier; missing/invalid stored tier or mismatch returns 409 before payment creation |
| PAY-002 | High | Invalid signature callback retired a possibly charged order; retry created another payment | Invalid signature rejects only the request; active order stays resumable |
| PAY-003 | High | Recalculated quote retired the pending order and created a replacement | Return 409 for quote/currency changes until existing payment is reconciled; never automatically retire that order |
| PAY-004 | Medium | Checkout against a cancelled ride was accepted | Cancelled ride checkout returns 409 |
| PAY-005 | High | Failed-attempt webhook or rejected provider verification retired the order, allowing a replacement | Preserve active order; record diagnostic reason for the unsuccessful attempt without declaring the order financially terminal |

Regression-first evidence: five initial payment tests failed before the first
fixes; four additional failed-attempt/verification probes failed before the
related order-state corrections. All now pass. Tests also verify successful
verification after an invalid signature, and delayed capture after a failed
attempt without allocating a second payment/order.

`payment.failed` describes an attempt, not proof that the order cannot receive
another successful payment. Failed-attempt notifications no longer guarantee
that no money was charged. Invalid signatures still never mark payments paid.
Existing authorization/signature checks remain in place.

Production change: `backend/routers/payments.py`.
Regression tests: `tests/test_payments.py`.

### Real parallel checkout tests

Three repeated runs execute two actual threads with independent database
sessions. A barrier synchronizes quote computation before concurrent checkout;
the provider mock generates distinct order IDs. Both responses must return
the same payment ID and attached order ID, with exactly one persisted payment.
All three passed. The existing conditional order attachment and unique index
already handle this tested race; no additional checkout locking was introduced.

## Reproduced booking defects and fixes

Scope: existing pre-acceptance joining of a two-rider run with vehicle capacity
three. This is not the missing ongoing-ride insertion workflow.

### BOOK-001 — compatible candidate missing from solver input (High)

Normal compatible third-rider attachment returned false even with deterministic
available routing. Root cause: sessions disable autoflush; assigning only
`virtual_stop_id` did not update `stop.ride_requests`, which is the builder's
input. The candidate never reached the route solver.

Fix: append the candidate to the ORM pickup-stop collection before solving, and
remove that association on rejection. A real builder/solver regression using
an explicit synthetic road matrix now assigns the compatible rider.

### BOOK-002 — both last-seat requests reported success (Critical)

Before the fix, **five of five** synchronized two-thread runs returned
`[True, True]`: both workers read the same open source plan, then each persisted
a replacement route. Re-reading driver acceptance was not an atomic claim.

Fix: conditionally UPDATE the source plan from solved to superseded, requiring
driver acceptance still not true. Only the worker that updates one row may
persist its replacement. A loser removes speculative membership, restores the
candidate's prior state and refreshes pickup count rather than overwriting the
winner's count.

Tests now cover:

- Five parallel distinct-request runs.
- Five parallel duplicate-booking-ID runs.
- Exactly one success, one active replacement plan, three roster entries,
  one assigned candidate, correct pickup passenger counts.
- Sequential retry does not create another reservation or plan.
- Injected persistence failure after the atomic claim, followed by caller
  rollback: original plan remains solved and candidate remains pending/unbound.

All pass. The routing step is deterministically mocked in race tests to force
the relevant overlap; actual ORM sessions, SQL updates, commits and persisted
state are used. The separate compatible-rider test executes the actual solver
with an explicit synthetic matrix.

Production change: `backend/services/carpool_matching.py`.
Regressions: `tests/test_booking_concurrency.py`.

## Compatibility and remaining work

- Existing linked rides without a valid stored fare tier now require explicit
  correction/reconciliation; checkout no longer trusts a submitted replacement
  tier. No silent backfill or fabricated legacy fare was performed.
- Existing active orders whose quote changed return 409 rather than open a new
  potentially duplicate charge. A product/support reconciliation workflow and
  cancellation/refund policy still need definition. No refunds were implemented.
- Historical failed payment rows from before this change were not migrated or
  reconciled; these fixes do not prove those old provider orders are settled.
- Docker is installed but its Linux engine pipe is unavailable; no `psql`,
  `postgres` or `pg_ctl` executable was found on PATH. Therefore **PostgreSQL/
  PostGIS concurrency validation remains BLOCKED**, not passed by SQLite.
- Tests do not establish all production isolation levels, driver-accept versus
  route-rebuild races, distributed worker dispatch, payment/webhook concurrency,
  or end-to-end browser/payment-provider behavior.
- Geographic route verification, stale GPS handling, signed-webhook financial
  field/reconciliation hardening, and the broader security concerns remain
  separate follow-up work.

## Re-run

```powershell
$env:DATABASE_URL='sqlite:///C:/Users/gudiy/AppData/Local/Temp/opencode/payment-concurrency-audit.db'
$env:SHARED_RIDE_SOLVER_TIME_LIMIT_SECONDS='1'
py -m pytest tests/ -q
```
