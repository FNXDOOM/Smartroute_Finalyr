# Razorpay Payments — Setup & Operations Guide

SmartRoute AI uses **Razorpay Checkout** (Standard) for ride-fare payments.
The backend is the single source of truth for payment state; the frontend
never sees any Razorpay secret and never decides whether a payment succeeded.

---

## Table of Contents

- [Architecture / payment flow](#architecture--payment-flow)
- [Razorpay account setup](#razorpay-account-setup)
- [Environment variables](#environment-variables)
- [Webhook configuration](#webhook-configuration)
- [Local development](#local-development)
- [Test-mode payment flow](#test-mode-payment-flow)
- [Production configuration](#production-configuration)
- [Test vs live credentials](#test-vs-live-credentials)
- [API endpoints](#api-endpoints)
- [Payment states](#payment-states)
- [Security model](#security-model)
- [Troubleshooting](#troubleshooting)

---

## Architecture / payment flow

```
User taps "Pay …" (PassengerView active-ride card → RazorpayPayment)
  → POST /payments/create-order          (Clerk/local JWT auth)
      backend: validates ride ownership → computes fare SERVER-SIDE
               (fare table × backend route distance, paise, clamped)
               → INSERT payments row (status=created)
               → POST https://api.razorpay.com/v1/orders (Key ID + secret)
               → stores razorpay_order_id, status=pending
  ← { razorpay_key_id, razorpay_order_id, amount, currency, customer_* }
  → Razorpay Checkout opens (checkout.js, order_id flow)
  → user completes / cancels / fails payment
  → checkout handler returns { razorpay_order_id, razorpay_payment_id,
                               razorpay_signature }   ← NOT trusted as success
  → POST /payments/verify                (same user; ownership enforced)
      backend: verify_payment_signature = HMAC-SHA256(order|payment, secret)
               → fetch payment from Razorpay API: order_id / amount /
                 currency / captured status must match the DB row
               → only then: status=paid, verified=1 (exactly once)
  ← { status: "paid", verified: true }  → frontend NOW shows success

In parallel, Razorpay webhooks → POST /payments/webhook
      backend: HMAC-SHA256(raw body, RAZORPAY_WEBHOOK_SECRET) vs
               X-Razorpay-Signature → payment.captured | payment.failed |
               refund.processed handled idempotently (paid never downgraded)
```

The database `payments` row is authoritative. The frontend success screen is
driven only by the `/payments/verify` response.

---

## Razorpay account setup

1. Sign up at <https://dashboard.razorpay.com> and complete KYC
   (KYC is required before live-mode payments; test mode works without it).
2. **Generate API keys**: Dashboard → *Settings → API Keys → Generate Test Key*.
   You get a Key ID (`rzp_test_...`) and Key Secret (shown once — store it
   in `backend/.env` immediately; it is never displayed again).
3. Optionally create a separate Razorpay account (or use the same account's
   live keys later) for staging vs production.

---

## Environment variables

All Razorpay configuration lives in `backend/.env` (see
`backend/.env.example`):

| Variable | Who holds it | Purpose |
|---|---|---|
| `RAZORPAY_KEY_ID` | Backend; also returned to frontend by `/payments/create-order` | Public checkout key (`rzp_test_…` / `rzp_live_…`) |
| `RAZORPAY_KEY_SECRET` | **Backend only** | Signs orders; verifies checkout signatures. Never returned by any endpoint, never in `VITE_*`, never in Docker build args |
| `RAZORPAY_WEBHOOK_SECRET` | **Backend only** | Verifies `X-Razorpay-Signature` on `/payments/webhook` |

If `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` are unset, the backend logs a
warning at startup and `/payments/create-order` + `/payments/verify` return
`503 Payments are not configured on the server` — the rest of the app is
unaffected. Webhooks with `RAZORPAY_WEBHOOK_SECRET` unset are always
rejected (fail closed).

Never commit real values; `.env` files are already git-ignored.

---

## Webhook configuration

Dashboard → *Settings → Webhooks → Add New Webhook*:

1. **URL**: `https://<your-api-domain>/payments/webhook`
   (production: the NPM-proxied API domain; local dev cannot receive public
   webhooks — use ngrok/cloudflared if you must test them locally).
2. **Secret**: generate a strong secret; put the *same* value in
   `RAZORPAY_WEBHOOK_SECRET` in `backend/.env` / the production Secrets
   Manager JSON. The signature header is `HMAC-SHA256(raw_body, secret)`.
3. **Active events** (everything else can stay off):
   - `payment.captured`
   - `payment.failed`
   - `refund.processed`
4. Save, then use *Send test webhook* and confirm the backend logs
   `Razorpay webhook received: event=…`.

The endpoint verifies the signature against the **raw request body** before
parsing, rejects invalid signatures with `400`, acknowledges unknown events,
and is idempotent for duplicate deliveries (Razorpay retries on non-2xx).

---

## Local development

```bash
# backend/.env
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=<test key secret>
RAZORPAY_WEBHOOK_SECRET=<any strong local secret>

alembic -c ../alembic.ini upgrade head   # creates the payments table
uvicorn main:app --reload --port 8000
```

Then in the Passenger portal: pick pickup + destination → request a ride →
in the active-booking card press **Pay**. Checkout opens in test mode and
accepts Razorpay's test cards (below).

---

## Test-mode payment flow

Use Razorpay's standard test instruments — no real money moves:

| Instrument | Value |
|---|---|
| Success card | `4111 1111 1111 1111`, any future expiry, any CVV, any name |
| Failure card | `4000 0000 0000 0002` (declined) |
| UPI | any valid-looking VPA, e.g. `success@razorpay` |
| Netbanking | pick any bank, choose *Success* on the mock page |

Expected behaviour:

- **Success** → verify returns `{ "status": "paid", "verified": true }`,
  payments row `paid`, toast "Payment successful".
- **Cancel / dismiss checkout** → button resets to *Payment cancelled — tap
  to retry*; no charge, no state change.
- **Failed card** → failure state; `/payments/verify` returns `400` and the
  payment is recorded `failed` (never `paid`).
- **Duplicate click / re-verify** → idempotent: the same success response,
  no duplicate charge (`409` if the ride is already paid).
- **Webhooks** → duplicate `payment.captured` deliveries are no-ops; a late
  `payment.failed` can never downgrade a `paid` payment.

---

## Production configuration

1. Complete KYC, then *Settings → API Keys → Generate Live Key*
   (`rzp_live_…`).
2. Put the live keys + webhook secret into the **AWS Secrets Manager** JSON
   (`smartroute/production/backend` — see `deploy/README.md`):

   ```json
   "RAZORPAY_KEY_ID": "rzp_live_...",
   "RAZORPAY_KEY_SECRET": "...",
   "RAZORPAY_WEBHOOK_SECRET": "..."
   ```

   `deploy/deploy.sh` validates these three keys and aborts the deploy if
   missing. They reach the `api`/`worker` containers only via
   `deploy/.env.prod` → compose `env_file` — never via build args.
3. Register the production webhook (URL from your real API domain) with the
   same secret.
4. Re-verify one test charge with a real instrument after go-live.

---

## Test vs live credentials

- Mode is determined **only** by which key pair is configured — there is no
  automatic switching, no `LIVE` flag to flip in code.
- Keep test and live secrets in separate stores (local `.env` vs Secrets
  Manager) so a local run can never charge real money.
- Key prefixes are a quick sanity check: `rzp_test_` = test, `rzp_live_` =
  live. Rotating keys: generate new keys in the dashboard, update the env /
  secret, restart the backend.

---

## API endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /payments/create-order` | Bearer JWT | Validate ride + compute fare server-side, create DB row + Razorpay Order, return public checkout payload |
| `POST /payments/verify` | Bearer JWT (owner/admin) | Verify checkout signature + Razorpay API cross-check; mark `paid` exactly once; idempotent |
| `POST /payments/webhook` | Signature only | Verified webhook receiver: `payment.captured` / `payment.failed` / `refund.processed`, idempotent |

Rate limits (application-level, per-IP + per-user; see `utils/rate_limit.py`):
`create-order` ≤10/10min per IP and ≤15/10min per user; `verify` ≤20/10min per IP
and ≤30/10min per user. The webhook is deliberately exempt from IP throttling —
its `X-Razorpay-Signature` verification is the access control, and throttling it
could delay legitimate Razorpay deliveries.
| `GET /payments/mine` | Bearer JWT | Current user's payments (no secrets) |
| `GET /payments/{payment_id}` | Bearer JWT (owner/admin) | Single payment |

Error mapping follows the project convention (`{ "detail": "…" }`):
`400` invalid option / verification failed / amount mismatch,
`403` not your payment, `404` unknown payment or ride (also returned for
other users' rides to prevent enumeration), `409` already paid / terminal
state, `502` Razorpay unavailable, `503` payments not configured.

---

## Payment states

`created → pending → paid`, with `failed` from either the checkout path or
webhooks, and `refunded` via `refund.processed`:

| Status | Meaning |
|---|---|
| `created` | DB row written, Razorpay Order not yet created |
| `pending` | Razorpay Order created, awaiting payment |
| `paid` | Signature verified (and/or verified webhook) + API cross-check passed |
| `failed` | Signature failure, Razorpay failure, amount mismatch, or provider error |
| `refunded` | Verified `refund.processed` webhook on a paid payment |

`verified` is a separate column: only server-side signature verification
sets `verified = 1`.

---

## Security model

- The **Key Secret never leaves the backend** — it exists only inside
  `backend/services/razorpay_service.py` and `backend/config.py`; no
  response schema contains it (see `backend/schemas/payment.py`).
- Amounts are computed from a **server-side fare table × backend-computed
  route distance**; the client can only name a ride option ID.
- `POST /payments/verify` enforces **ownership** before touching state, and
  cross-checks the payment against the Razorpay API (order ID, amount,
  currency, captured status).
- Verification and webhooks are **idempotent**; a paid payment is never
  downgraded by a later failed webhook.
- Logs contain order/payment IDs and event names only — never secrets,
  never card data, never raw Razorpay error bodies.
- All responses use safe, generic error messages (`400 Payment verification
  failed`), so nothing about Razorpay internals leaks to clients.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `503 Payments are not configured` | `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` missing in `backend/.env`; restart after editing |
| Checkout opens then errors immediately | Key ID doesn't match the secret's account, or the order was created with a live key while checkout got a test key (or vice versa) |
| `400 Payment verification failed` | Checkout signature mismatch — usually key mismatch or a tampered payload; check backend logs for `signature verification failed` |
| `502 Payment provider is unavailable` on verify (row stays `pending`) | Backend couldn't reach `api.razorpay.com` while cross-checking the payment (VPN/proxy toggles, firewall, DNS blips). The service now retries transient connection errors 3× with backoff, and the payment stays recoverable: tap Pay again and the SAME order is reopened — never a new charge. Check backend logs for `Razorpay API ... transient failure` |
| `409 This ride has already been paid` | Expected duplicate-charge guard — a `paid` payment exists for that ride |
| Webhook `400 Invalid webhook signature` | `RAZORPAY_WEBHOOK_SECRET` in env differs from the dashboard webhook secret |
| Webhook acknowledged but no state change | Event wasn't `payment.captured`/`payment.failed`/`refund.processed`, or the order ID has no matching payments row (check `Webhook for unknown order` logs) |
| `502 Payment provider is unavailable` | Razorpay API outage / network block; the payment row is marked `failed` with `razorpay_order_creation_failed` — retry creates a new one |
