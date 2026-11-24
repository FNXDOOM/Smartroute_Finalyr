# SmartRoute defensive static security audit

Scope: workspace source and checked-in configuration only. No live service was tested and no exploit or payload was produced. The findings below are confirmed in source, not observations about the running deployment. Line numbers refer to the pre-remediation source.

Remediation status: all four findings were addressed in the workspace after the audit. The snippets below document the original recommendations; the implementation also lets checkout recheck pending capture without opening another checkout. Verification: 357 backend tests passed with SQLite, five PostgreSQL-only tests were skipped, and the frontend production build passed. No existing payment records were changed.

## Surface and trust boundaries

- **Stack:** Python/FastAPI and Uvicorn, SQLAlchemy and Alembic, PostgreSQL/PostGIS in production; React/Vite and MapLibre in the browser. Docker Compose and Nginx Proxy Manager provide the checked-in production path; the repository also includes ECS definitions and GitHub Actions build/deploy configuration.
- **Public inputs:** local registration and login, Razorpay's independently signed webhook, root and health endpoints, default FastAPI docs/OpenAPI, and the in-app metrics endpoint. The supplied Nginx API configuration denies public `/metrics`; its installation was not verified.
- **Authenticated inputs:** the 14 mounted router groups (`backend/main.py:97–110`) cover accounts, rides/demo rides, clustering, route planning and carpool transitions, routing/geocoding/map proxying, vehicles and telemetry, prediction, notifications, analytics, jobs, and payments. Tracking and notifications have separate authenticated WebSocket handshakes. The synthetic fleet socket belongs to a separate app, not the production router list.
- **Other inputs:** the worker consumes database-backed optimization jobs and runs scheduled dispatch, clustering, forecasting, and rebalancing. The seed CLI and migrations take operator-controlled inputs. Deployment configuration and environment variables supply signing material, service credentials, origins, and database settings.
- **High-value boundaries:** Clerk identity and locally signed JWTs resolve to DB-controlled passenger, driver, and admin roles; driver approval is a separate authorization condition. Ride and job ownership, vehicle assignment, and live versus demo scope determine access to location data. Razorpay is authoritative for payment state; Stadia receives location queries and uses a server-side quota credential.

## Confirmed findings

| ID | Title | Severity | Class | Primary location |
| --- | --- | --- | --- | --- |
| SR-01 | Job history bypasses optimization-job ownership | Medium | Broken object-level authorization | `backend/routers/jobs.py:87–96` |
| SR-02 | Tracking socket retains stale privileges | Medium | Authorization revocation failure | `backend/routers/tracking.py:54–58,81–108,432–458` |
| SR-03 | Driver route history omits approval enforcement | Medium | Broken function-level authorization | `backend/routers/route.py:292–367` |
| SR-04 | An authorized but uncaptured payment is recorded as paid | Medium | Payment state integrity | `backend/routers/payments.py:431–454,524–536` |

### SR-01 — Job history bypasses optimization-job ownership

**Flow.** `backend/routers/route.py:233–251` stores the request and its initiating user in `JobRun`; the worker consumes these rows (`backend/services/background_jobs.py:1005–1021`). The job-specific API enforces owner-or-admin access at `route.py:254–279`. The general history path checks driver/admin membership but fetches all recent rows (`jobs.py:87–96`). `JobRunResponse` serializes `summary` (`backend/schemas/jobs.py:7–13`); neither authentication nor serialization adds a row-level filter.

**Impact.** An approved driver can receive other users' optimization job summaries, including submitted vehicle and stop references. This is a cross-account disclosure, not a claim of arbitrary ride or payment access.

**Patch.** Replace the unfiltered query in `list_job_runs` below `_require_admin_or_driver(current_user)`. Keep existing shared operational history for non-optimization jobs:

```python
from sqlalchemy import or_  # module imports

# In list_job_runs:
query = db.query(JobRun)
if current_user.role != "admin":
    query = query.filter(
        or_(
            JobRun.job_name != "optimize_route",
            JobRun.triggered_by_user_id == current_user.id,
        )
    )
runs = query.order_by(JobRun.started_at.desc()).limit(limit).all()
return [JobRunResponse.model_validate(run) for run in runs]
```

### SR-02 — Tracking socket retains stale privileges

**Flow.** The handler verifies a token and origin at `tracking.py:432–454`, then stores the user's role in `TrackingConnection` (`:36–58`). Snapshot and push senders trust that cached role (`:81–108`), including the admin fast path that bypasses object scoping. The account role is mutable (`backend/routers/auth.py:257–280`), but the receive loop performs no authorization refresh. The socket also does not apply the active-driver check used by HTTP tracking (`tracking.py:282–311`; `backend/utils/auth_utils.py:233–264`).

**Impact.** An open admin socket can continue receiving fleet-wide locations and tracking events after the user is demoted. An inactive driver can also receive assigned-vehicle telemetry while the vehicle remains assigned. The admin case requires an already-established privileged connection; it is not an unauthenticated admin bypass.

**Patch.** In `tracking.py`, add this method to `ConnectionManager`. In **both** `_send_snapshot` and `_send_vehicle_update`, insert the guard below before computing visibility. This uses the DB role on every send and closes sockets with a changed role, rather than reusing privileges from the handshake.

```python
async def _still_authorized(self, entry: TrackingConnection, db: Session) -> bool:
    row = db.query(User.role, User.driver_status).filter(User.id == entry.user_id).first()
    if row is not None and row.role == entry.role and (
        row.role != "driver" or row.driver_status == "active"
    ):
        return True
    self.disconnect(entry.websocket)
    await entry.websocket.close(code=4403, reason="Tracking access revoked")
    return False
```

```python
# First lines of both send methods:
if not await self._still_authorized(entry, db):
    return
```

Also add the following immediately after the handshake's `finally: db.close()` and before `manager.connect(...)`:

```python
if user.role == "driver" and user.driver_status != "active":
    await websocket.close(code=4403, reason="Driver is not active")
    return
```

### SR-03 — Driver route history omits approval enforcement

**Flow.** Both history handlers accept any authenticated user with DB role `driver` or `admin` (`backend/routers/route.py:292–313,340–362`). The vehicle filter enforces ownership but never checks active approval. The driver verification path updates driver status (`backend/routers/auth.py:223–254`); the shared dependency used by other driver APIs explicitly denies inactive drivers (`backend/utils/auth_utils.py:233–264`). The history handlers still serialize route plans, and the list handler can also commit reconciliation changes (`route.py:320–336`).

**Impact.** An inactive driver retains access to detailed plans tied to vehicles that remain assigned to that account. The list endpoint can still trigger repair of those plans. This does not grant access to unrelated vehicles.

**Patch.** Add `get_current_driver_user` to the `utils.auth_utils` import in `route.py`. In **both** `list_routes` and `get_route_history`, replace the `current_user` parameter with the following, remove the now-redundant inline role-only block, and leave the vehicle ownership checks intact:

```python
current_user: User = Depends(get_current_driver_user),
```

### SR-04 — An authorized but uncaptured payment is recorded as paid

**Flow.** The authenticated verification path checks payment ownership, checkout signature, provider order, and amount/currency (`backend/routers/payments.py:367–430`). It then accepts both `captured` and `authorized` and persists `paid` and `verified` (`:431–454`). The webhook verifies a raw-body signature (`:474–488`), but likewise sets `paid` on `payment.authorized` (`:524–536`). A subsequent failure event for an already-paid row is skipped by the early return at `:525`. The signature proves authenticity; it does not make authorization equivalent to capture.

**Impact.** If capture is delayed or fails, local receipts and paid notifications can overstate collected revenue. No claim is made that a person can forge a provider signature, or that the UI grants a service solely from this state.

**Patch.** In the verification handler between the amount/currency check and the existing status rejection, add the distinct pending response below and replace the old two-state condition with `if provider_status != "captured":`. Keep the existing failure block and the conditional paid update. In the webhook, replace `if event in ("payment.captured", "payment.authorized"):` with `if event == "payment.captured":`; authorization events then fall through to the existing acknowledgement without any paid write.

```python
provider_status = rzp_payment.get("status")
if provider_status == "authorized":
    return PaymentVerifyResponse(
        payment_id=payment.id,
        status=payment.status,
        verified=False,
        ride_request_id=payment.ride_request_id,
        message="Payment is awaiting capture",
    )
if provider_status != "captured":
    payment.failure_reason = "payment_not_captured"
    db.commit()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Payment was not successful",
    )
```

Ensure the checkout UI does not show a paid receipt from HTTP success alone; use `verified` or persisted payment status. Reconcile existing paid rows against provider records before making any corrections.

## Triage notes and remaining coverage

- JWT decoding pins HS256 for local tokens and RS256 for Clerk; the latter checks issuer and configured audience/authorized party. HTTP uses `OAuth2PasswordBearer`, not a cookie session. Both production sockets explicitly check a supplied browser `Origin`; the confirmed issue above is authorization after connection, not a demonstrated cross-site handshake bypass.
- The reviewed Stadia calls use configured upstream hosts; route coordinates and search strings enter query/body fields or a quoted resource path. No arbitrary-host SSRF was established. The sampled interpolated SQL uses migration/seed table names rather than request values. No request-controlled pickle source, upload handler, or GraphQL/RPC mount was identified in the scanned paths.
- The payment webhook authenticates the raw body before parsing, and the payment read routes scope rows to the user/admin. Checkout uses a conditional final update and the webhook locks its payment row. These are real protections, not evidence that all webhook permutations are correct.
- Live proxy configuration, log retention and redaction (including the supported WebSocket token query parameter), deployed credential entropy, dependency advisories, and multi-process concurrency were not verified. The production Compose file contains fallback database and Grafana passwords; their deployment reachability and whether defaults are in use were not established. Require explicit secrets in production configuration.
- This is a source inventory and targeted end-to-end review, not a completed handler-by-handler proof of absence. Remaining depth includes a per-endpoint authorization matrix for all ride/demo/dispatch actions, full provider event-order reconciliation, and frontend HTML-sink and client-storage coverage. The audit itself was static-only; the later remediation was checked locally as described above.
