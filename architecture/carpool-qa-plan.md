# Carpool validation execution plan

Baseline: `f61092e` (clean checkout at start). The supplied 35-scenario task is
the target specification, not a claim about existing functionality.

1. Inspect models, HTTP routers, lifecycle/matching/solver services, frontend
   views, architecture notes and existing tests.
2. Run existing pytest tests with outbound network blocked and a dedicated
   SQLite database in the approved temporary directory. Never use backend/.env
   database data for tests. Run frontend lint/build separately.
3. Add deterministic contract/probe tests for feasible pickup/drop-off ordering,
   segment capacity, invalid coordinates, closed-run membership, and failures.
   Reuse the installed pytest framework and existing fixture conventions.
4. Reproduce confirmed defects before editing production code; make minimal
   fixes and rerun the regression suite.
5. Record all TC01–TC35 statuses and evidence in `carpool-qa-report.md`.
   Distinguish component tests from full end-to-end tests and missing workflows
   from failed existing workflows.

Constraints: SQLite cannot establish PostgreSQL locking correctness. No live
Clerk, Stadia, Razorpay or authenticated browser workflow is implied by mocks.
Exact Avalahalli place identity and road compatibility require real provider
verification; synthetic corridor coordinates are not geographic evidence.
Dynamic mid-run insertion is explicitly excluded by existing implementation
and architecture/algorithms.md:168–170; do not silently reverse that policy.

Formal two-axis diff review requires a user-supplied comparison ref, which was
not supplied. Current-source assessment and review of this session's minimal
change can proceed, but are not a historical branch review.
