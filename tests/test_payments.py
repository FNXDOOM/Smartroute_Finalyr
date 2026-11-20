"""Razorpay payment tests: orders, signatures, webhooks and failure handling, with the HTTP API fully mocked.
Rides and payments come from a plain MetaData because SQLite has no SpatiaLite, matching tests/test_mobile_auth.py."""

import asyncio
import hashlib
import hmac
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx
from fastapi import HTTPException
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Float, String, DateTime, JSON
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from models.payment import Payment  # noqa: E402
from models.ride_request import RideRequest  # noqa: E402
from models.user import User  # noqa: E402

TEST_KEY_ID = "rzp_test_dummykeyid"
TEST_KEY_SECRET = "testsecret_dummy_never_real"
TEST_WEBHOOK_SECRET = "testwebhooksecret_dummy"


def _utcnow():
    return datetime.now(timezone.utc)


def _build_lite_schema():
    """Plain tables matching the ORM columns, minus geometry (PostGIS-only)."""
    metadata = MetaData()
    Table(
        "users", metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String, nullable=False),
        Column("email", String, nullable=False),
        Column("phone", String),
        Column("password_hash", String, nullable=False),
        Column("clerk_user_id", String),
        Column("role", String, nullable=False, server_default="passenger"),
        Column("driver_status", String, nullable=False, server_default="active"),
        Column("driver_last_seen_at", DateTime),
        Column("created_at", DateTime, default=_utcnow),
    )
    Table(
        "ride_requests", metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, nullable=False),
        Column("pickup_lat", Float, nullable=False),
        Column("pickup_lng", Float, nullable=False),
        Column("dest_lat", Float, nullable=False),
        Column("dest_lng", Float, nullable=False),
        Column("status", String, server_default="pending"),
        Column("ride_mode", String, server_default="live"),
        Column("is_shared", Integer, server_default="1"),
        Column("carpool_status", String),
        Column("demo_run_id", String),
        Column("h3_index", String),
        Column("cluster_id", Integer),
        Column("virtual_stop_id", Integer),
        Column("pickup_location", String),
        Column("destination_location", String),
        Column("request_time", DateTime, default=_utcnow),
        Column("pickup_label", String),
        Column("destination_label", String),
        Column("ride_option_id", String),
        Column("ride_option_name", String),
        Column("ride_option_price", String),
    )
    Table(
        "payments", metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, nullable=False),
        Column("ride_request_id", Integer),
        Column("purpose", String, server_default="ride_fare"),
        Column("amount", Integer, nullable=False),
        Column("currency", String, server_default="INR"),
        Column("status", String, server_default="created"),
        Column("razorpay_order_id", String),
        Column("razorpay_payment_id", String),
        Column("verified", Integer, server_default="0"),
        Column("failure_reason", String),
        Column("metadata", JSON),
        Column("created_at", DateTime, default=_utcnow),
        Column("updated_at", DateTime, default=_utcnow),
    )
    Table(
        "notifications", metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, nullable=False),
        Column("notification_type", String, nullable=False),
        Column("title", String, nullable=False),
        Column("message", String, nullable=False),
        Column("related_entity_type", String),
        Column("related_entity_id", Integer),
        Column("metadata", JSON),
        Column("is_read", Integer, server_default="0"),
        Column("read_at", DateTime),
        Column("created_at", DateTime, default=_utcnow),
    )
    return metadata


test_engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
_build_lite_schema().create_all(bind=test_engine)

from schemas.payment import PaymentCreate, PaymentVerifyRequest  # noqa: E402
from services import razorpay_service  # noqa: E402
from services.razorpay_service import (  # noqa: E402
    RazorpayClient,
    RazorpayError,
    compute_fare_amount_paise,
    verify_payment_signature,
    verify_webhook_signature,
)
from routers import payments as payments_router  # noqa: E402


# --- Fixtures ---

@pytest.fixture()
def db():
    session = TestingSessionLocal()
    # The in-memory engine is shared across tests, so clear every row: fixed order IDs (order_payment-1) would collide.
    session.query(Payment).delete()
    session.query(RideRequest).delete()
    session.query(User).delete()
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db):
    u = User(name="Pay User", email=f"pay.user.{id(db)}@example.com", password_hash="x", role="passenger")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def other_user(db):
    u = User(name="Other User", email=f"other.user.{id(db)}@example.com", password_hash="x", role="passenger")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def ride(db, user):
    r = RideRequest(
        user_id=user.id,
        pickup_lat=12.9716, pickup_lng=77.5946,
        dest_lat=12.9352, dest_lng=77.6245,
        status="completed",
        ride_option_id="swift-x",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@pytest.fixture()
def fake_client(monkeypatch):
    """Replace the Razorpay HTTP client with an in-memory fake."""
    client = SimpleNamespace(
        create_order=lambda **kwargs: {
            "id": f"order_{kwargs['receipt']}",
            "amount": kwargs["amount"],
            "currency": kwargs["currency"],
        },
        fetch_payment=lambda payment_id: {
            "id": payment_id,
            "order_id": "order_payment-1",
            "amount": 1500,
            "currency": "INR",
            "status": "captured",
        },
    )
    monkeypatch.setattr(payments_router, "_client", client)
    monkeypatch.setattr(payments_router, "_require_razorpay_configured", lambda: client)
    return client


@pytest.fixture()
def set_secrets(monkeypatch):
    """Point the signature helpers at deterministic test-only secrets."""
    monkeypatch.setattr(razorpay_service, "RAZORPAY_KEY_SECRET", TEST_KEY_SECRET)
    monkeypatch.setattr(razorpay_service, "RAZORPAY_KEY_ID", TEST_KEY_ID)
    monkeypatch.setattr(razorpay_service, "is_configured", lambda: True)
    # The router binds RAZORPAY_KEY_ID at import time; patch its copy too.
    monkeypatch.setattr(payments_router, "RAZORPAY_KEY_ID", TEST_KEY_ID)
    return monkeypatch


@pytest.fixture()
def set_webhook_secret(monkeypatch):
    monkeypatch.setattr(razorpay_service, "RAZORPAY_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET)
    return monkeypatch


# --- Helpers ---

def _make_payment(db, user, ride, order_id="order_payment-1", status="pending", amount=1500):
    p = Payment(
        user_id=user.id,
        ride_request_id=ride.id if ride else None,
        purpose="ride_fare",
        amount=amount,
        currency="INR",
        status=status,
        razorpay_order_id=order_id,
        verified=0,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _valid_signature(order_id, payment_id, secret=TEST_KEY_SECRET):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


class _StubRequest:
    """Minimal async Request stand-in exposing the raw body."""

    def __init__(self, signature: str, body: bytes):
        self.headers = {"X-Razorpay-Signature": signature}
        self._body = body

    async def body(self):
        return self._body


def _make_request(signature: str, body: bytes):
    return _StubRequest(signature, body)


def _run_webhook(db, signature: str, payload: dict):
    """Invoke the async webhook endpoint as an awaitable test helper."""
    body = json.dumps(payload).encode()
    return asyncio.run(payments_router.razorpay_webhook(_make_request(signature, body), db))


def _captured_payload(order_id="order_payment-1", payment_id="pay_w1", event="payment.captured"):
    return {
        "event": event,
        "payload": {
            "payment": {
                "entity": {"id": payment_id, "order_id": order_id, "status": "captured"}
            }
        },
    }


def _signed_body(payload: dict, secret=TEST_WEBHOOK_SECRET):
    body = json.dumps(payload).encode()
    return body, hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# --- Signature helpers (service layer) ---

def test_signature_valid_and_invalid(set_secrets):
    sig = _valid_signature("order_1", "pay_1")
    assert verify_payment_signature("order_1", "pay_1", sig) is True
    assert verify_payment_signature("order_1", "pay_1", "deadbeef") is False
    assert verify_payment_signature("order_1", "pay_2", sig) is False
    assert verify_payment_signature("order_2", "pay_1", sig) is False


def test_webhook_signature_valid_and_invalid(set_webhook_secret):
    body = b'{"event":"payment.captured"}'
    sig = hmac.new(TEST_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, sig) is True
    assert verify_webhook_signature(body, "00" * 32) is False
    assert verify_webhook_signature(b"tampered", sig) is False


# --- Fare computation (server-side amount) ---

def test_fare_computation_server_side():
    # swift-x: base 12 + 6/km, clamped to the advertised [12, 15] rupee band
    assert compute_fare_amount_paise("swift-x", 0.0) == 1200
    assert compute_fare_amount_paise("swift-x", 1.0) == 1500
    assert compute_fare_amount_paise("swift-x", 50.0) == 1500
    # Moto: base 6 + 4/km, clamp [6, 9]
    assert compute_fare_amount_paise("swift-moto", 0.0) == 600
    assert compute_fare_amount_paise("swift-moto", 0.5) == 800
    assert compute_fare_amount_paise("swift-moto", 50.0) == 900


class _FlakyHTTP:
    """httpx.request stand-in raising transient errors for the first N calls."""

    def __init__(self, failures=2):
        self.failures = failures
        self.calls = 0

    def __call__(self, method, url, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise httpx.ConnectError("connection refused (simulated)")
        return SimpleNamespace(status_code=201, json=lambda: {"id": "order_retry", "amount": 1500, "currency": "INR"})


def test_http_retry_succeeds_after_transient_connect_errors(monkeypatch):
    """The transient-failure retry path recovers without surfacing an error."""
    flaky = _FlakyHTTP(failures=2)
    monkeypatch.setattr(razorpay_service.httpx, "request", flaky)
    client = RazorpayClient(key_id="k", key_secret="s")
    order = client.create_order(amount=1500, currency="INR", receipt="p-1")
    assert order["id"] == "order_retry"
    assert flaky.calls == 3


def test_http_retry_gives_up_after_max_attempts(monkeypatch):
    calls = {"n": 0}

    def always_down(method, url, **kwargs):
        calls["n"] += 1
        raise httpx.ConnectError("still down (simulated)")

    monkeypatch.setattr(razorpay_service.httpx, "request", always_down)
    monkeypatch.setattr(razorpay_service.time, "sleep", lambda _s: None)
    client = RazorpayClient(key_id="k", key_secret="s")
    # The client wraps the exhausted retries in RazorpayError (router → 502).
    with pytest.raises(RazorpayError):
        client.create_order(amount=1500, currency="INR", receipt="p-1")
    assert calls["n"] == razorpay_service.RAZORPAY_HTTP_ATTEMPTS


def test_http_no_retry_on_definitive_http_error(monkeypatch):
    """Real HTTP error responses must fail fast — no retry, no delay."""
    calls = {"n": 0}

    def http_error(method, url, **kwargs):
        calls["n"] += 1
        return SimpleNamespace(status_code=401, json=lambda: {"error": {}})

    monkeypatch.setattr(razorpay_service.httpx, "request", http_error)
    client = RazorpayClient(key_id="k", key_secret="s")
    with pytest.raises(RazorpayError):
        client.create_order(amount=1500, currency="INR", receipt="p-1")
    assert calls["n"] == 1


def test_fare_rejects_unknown_option():
    with pytest.raises(ValueError):
        compute_fare_amount_paise("nonexistent", 5.0)


# --- Order creation ---

def test_create_order_happy_path(db, user, ride, fake_client, set_secrets, monkeypatch):
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)
    resp = payments_router.create_payment_order(
        PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
    )

    assert resp.amount == 1500
    assert resp.razorpay_order_id == f"order_payment-{resp.payment_id}"
    assert resp.razorpay_key_id == TEST_KEY_ID
    assert resp.currency == "INR"
    assert resp.ride_request_id == ride.id
    # The Key Secret must never appear in any response field.
    assert TEST_KEY_SECRET not in str(resp.model_dump())

    db_p = db.query(Payment).filter(Payment.id == resp.payment_id).first()
    assert db_p.status == "pending"
    assert db_p.amount == 1500
    assert db_p.verified == 0
    assert db_p.user_id == user.id


def test_create_order_rejects_unknown_option(db, user, fake_client, set_secrets):
    with pytest.raises(HTTPException) as exc:
        payments_router.create_payment_order(
            PaymentCreate(ride_option_id="hacked-option"), db, user
        )
    assert exc.value.status_code == 400


def test_create_order_rejects_foreign_ride(db, user, other_user, ride, fake_client, set_secrets):
    """A user must not create a payment against someone else's ride."""
    with pytest.raises(HTTPException) as exc:
        payments_router.create_payment_order(
            PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"),
            db,
            other_user,
        )
    assert exc.value.status_code == 404


def test_create_order_razorpay_failure_marks_payment_failed(db, user, ride, set_secrets, monkeypatch):
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)

    def boom(**kwargs):
        raise RazorpayError("Razorpay order request failed")

    monkeypatch.setattr(
        payments_router,
        "_require_razorpay_configured",
        lambda: SimpleNamespace(create_order=boom),
    )
    with pytest.raises(HTTPException) as exc:
        payments_router.create_payment_order(
            PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
        )
    assert exc.value.status_code == 502
    failed = db.query(Payment).filter(Payment.user_id == user.id).first()
    assert failed.status == "failed"
    assert failed.failure_reason == "razorpay_order_creation_failed"


def test_create_order_blocked_when_ride_already_paid(db, user, ride, fake_client, set_secrets, monkeypatch):
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)
    _make_payment(db, user, ride, order_id="order_already", status="paid", amount=1500)
    with pytest.raises(HTTPException) as exc:
        payments_router.create_payment_order(
            PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
        )
    assert exc.value.status_code == 409


def test_create_order_resumes_unpaid_order_no_double_charge(db, user, ride, fake_client, set_secrets, monkeypatch):
    """Regression: a transient verification failure used to open a second order and double-charge."""
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)
    stuck = _make_payment(db, user, ride, order_id="order_stuck", status="pending", amount=1500)

    resp = payments_router.create_payment_order(
        PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
    )

    assert resp.payment_id == stuck.id
    assert resp.razorpay_order_id == "order_stuck"
    assert db.query(Payment).filter(Payment.user_id == user.id).count() == 1


def test_create_order_does_not_replace_unreconciled_order_when_fare_changed(db, user, ride, fake_client, set_secrets, monkeypatch):
    """A changed quote is not evidence that an existing order cannot charge."""
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)
    stuck = _make_payment(db, user, ride, order_id="order_stale", status="pending", amount=999)

    with pytest.raises(HTTPException) as refused:
        payments_router.create_payment_order(
            PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
        )
    assert refused.value.status_code == 409
    db.refresh(stuck)
    assert stuck.status == "pending"
    assert stuck.razorpay_order_id == "order_stale"
    assert db.query(Payment).count() == 1


def test_checkout_rejects_tier_downgrade(db, user, ride, fake_client, set_secrets, monkeypatch):
    ride.ride_option_id = "swift-lux"
    db.commit()
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)
    with pytest.raises(HTTPException) as refused:
        payments_router.create_payment_order(
            PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-moto"), db, user
        )
    assert refused.value.status_code == 409
    assert db.query(Payment).count() == 0


def test_checkout_requires_persisted_tier_for_linked_ride(db, user, ride, fake_client, set_secrets):
    ride.ride_option_id = None
    db.commit()
    with pytest.raises(HTTPException) as refused:
        payments_router.create_payment_order(
            PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-moto"), db, user
        )
    assert refused.value.status_code == 409
    assert db.query(Payment).count() == 0


@pytest.mark.parametrize("ride_status", ["pending", "clustered", "assigned", "arriving", "ready_for_pickup", "in_progress"])
def test_checkout_rejects_unfinished_ride(db, user, ride, fake_client, set_secrets, ride_status):
    from routers.payments import _resolve_ride_amount
    ride.status = ride_status
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _resolve_ride_amount(db, user, ride.id, ride.ride_option_id)
    assert exc.value.status_code == 409


def test_checkout_rejects_cancelled_ride(db, user, ride, fake_client, set_secrets):
    ride.status = "cancelled"
    db.commit()
    with pytest.raises(HTTPException) as refused:
        payments_router.create_payment_order(
            PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
        )
    assert refused.value.status_code == 409
    assert db.query(Payment).count() == 0


def test_bad_signature_keeps_original_checkout_resumable(db, user, ride, fake_client, set_secrets, monkeypatch):
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)
    original = _make_payment(db, user, ride, order_id="order_maybe_charged")
    with pytest.raises(HTTPException) as refused:
        payments_router.verify_payment(
            PaymentVerifyRequest(
                razorpay_order_id="order_maybe_charged", razorpay_payment_id="pay_callback",
                razorpay_signature="00" * 32,
            ), db, user,
        )
    assert refused.value.status_code == 400
    checkout = payments_router.create_payment_order(
        PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
    )
    assert checkout.payment_id == original.id
    assert checkout.razorpay_order_id == "order_maybe_charged"
    assert db.query(Payment).count() == 1


def test_bad_signature_can_be_followed_by_valid_verification(db, user, ride, fake_client, set_secrets):
    payment = _make_payment(db, user, ride)
    payload = dict(razorpay_order_id="order_payment-1", razorpay_payment_id="pay_retry")
    with pytest.raises(HTTPException):
        payments_router.verify_payment(
            PaymentVerifyRequest(**payload, razorpay_signature="00" * 32), db, user
        )
    result = payments_router.verify_payment(
        PaymentVerifyRequest(**payload, razorpay_signature=_valid_signature("order_payment-1", "pay_retry")),
        db, user,
    )
    db.refresh(payment)
    assert result.verified and payment.status == "paid"


def test_failed_attempt_webhook_does_not_open_another_order(db, user, ride, fake_client, set_secrets, set_webhook_secret, monkeypatch):
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)
    payment = _make_payment(db, user, ride)
    payload = _captured_payload(event="payment.failed")
    _, signature = _signed_body(payload)
    _run_webhook(db, signature, payload)
    checkout = payments_router.create_payment_order(
        PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
    )
    assert checkout.payment_id == payment.id
    assert checkout.razorpay_order_id == "order_payment-1"
    assert db.query(Payment).count() == 1
    # A subsequent successful attempt on the same order still reconciles.
    payload = _captured_payload()
    _, signature = _signed_body(payload)
    _run_webhook(db, signature, payload)
    db.refresh(payment)
    assert payment.status == "paid"


@pytest.mark.parametrize("provider_result", [
    {"order_id": "order_other"},
    {"amount": 999},
    {"status": "failed"},
])
def test_rejected_verification_does_not_retire_provider_order(db, user, ride, fake_client, set_secrets, provider_result):
    payment = _make_payment(db, user, ride)
    original_fetch = fake_client.fetch_payment
    fake_client.fetch_payment = lambda payment_id: {**original_fetch(payment_id), **provider_result}
    with pytest.raises(HTTPException) as refused:
        payments_router.verify_payment(
            PaymentVerifyRequest(
                razorpay_order_id="order_payment-1", razorpay_payment_id="pay_rejected",
                razorpay_signature=_valid_signature("order_payment-1", "pay_rejected"),
            ), db, user,
        )
    assert refused.value.status_code == 400
    db.refresh(payment)
    assert payment.status == "pending"
    assert payment.verified == 0


def test_create_order_does_not_resume_other_users_payment(db, user, other_user, ride, fake_client, set_secrets, monkeypatch):
    """Resume must be scoped to the caller's own payments."""
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)
    _make_payment(db, other_user, ride, order_id="order_someone_else", status="pending", amount=1500)

    resp = payments_router.create_payment_order(
        PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
    )

    assert resp.razorpay_order_id != "order_someone_else"
    assert resp.payment_id != db.query(Payment).filter(Payment.razorpay_order_id == "order_someone_else").first().id


# --- Verification ---

def test_verify_success_marks_paid(db, user, ride, fake_client, set_secrets):
    payment = _make_payment(db, user, ride)
    resp = payments_router.verify_payment(
        PaymentVerifyRequest(
            razorpay_order_id="order_payment-1",
            razorpay_payment_id="pay_ok1",
            razorpay_signature=_valid_signature("order_payment-1", "pay_ok1"),
        ),
        db,
        user,
    )
    assert resp.verified is True
    assert resp.status == "paid"
    db.refresh(payment)
    assert payment.status == "paid"
    assert payment.verified == 1
    assert payment.razorpay_payment_id == "pay_ok1"


def test_verify_rejects_invalid_signature(db, user, ride, fake_client, set_secrets):
    _make_payment(db, user, ride)
    with pytest.raises(HTTPException) as exc:
        payments_router.verify_payment(
            PaymentVerifyRequest(
                razorpay_order_id="order_payment-1",
                razorpay_payment_id="pay_bad1",
                razorpay_signature="00" * 32,
            ),
            db,
            user,
        )
    assert exc.value.status_code == 400
    p = db.query(Payment).filter(Payment.razorpay_order_id == "order_payment-1").first()
    assert p.status == "pending"  # untrusted callback cannot retire a possibly charged order


def test_verify_network_error_is_retryable_not_terminal(db, user, ride, fake_client, set_secrets, monkeypatch):
    """A transient outage during the fetch must stay 502/retryable, never terminal: the customer may already have paid."""
    payment = _make_payment(db, user, ride)

    def unreachable(payment_id):
        raise RazorpayError("Razorpay payment fetch failed")

    flaky = SimpleNamespace(
        create_order=lambda **kwargs: {"id": "order_x", "amount": kwargs["amount"], "currency": "INR"},
        fetch_payment=unreachable,
    )
    monkeypatch.setattr(payments_router, "_client", flaky)
    monkeypatch.setattr(payments_router, "_require_razorpay_configured", lambda: flaky)

    with pytest.raises(HTTPException) as exc:
        payments_router.verify_payment(
            PaymentVerifyRequest(
                razorpay_order_id="order_payment-1",
                razorpay_payment_id="pay_ok1",
                razorpay_signature=_valid_signature("order_payment-1", "pay_ok1"),
            ),
            db,
            user,
        )
    assert exc.value.status_code == 502
    db.refresh(payment)
    assert payment.status == "pending"   # recoverable — retry verification
    assert payment.verified == 0
    assert payment.razorpay_payment_id is None


def test_verify_rejects_wrong_order_id(db, user, ride, fake_client, set_secrets):
    """A signature computed for a different order must never mark payment paid."""
    _make_payment(db, user, ride, order_id="order_real")
    sig = _valid_signature("order_other", "pay_x")
    with pytest.raises(HTTPException) as exc:
        payments_router.verify_payment(
            PaymentVerifyRequest(
                razorpay_order_id="order_real",
                razorpay_payment_id="pay_x",
                razorpay_signature=sig,
            ),
            db,
            user,
        )
    assert exc.value.status_code == 400
    p = db.query(Payment).filter(Payment.razorpay_order_id == "order_real").first()
    assert p.status == "pending"


def test_verify_rejects_unauthorized_user(db, user, other_user, ride, fake_client, set_secrets):
    """Another user cannot verify someone else's order."""
    _make_payment(db, user, ride)
    sig = _valid_signature("order_payment-1", "pay_ok2")
    with pytest.raises(HTTPException) as exc:
        payments_router.verify_payment(
            PaymentVerifyRequest(
                razorpay_order_id="order_payment-1",
                razorpay_payment_id="pay_ok2",
                razorpay_signature=sig,
            ),
            db,
            other_user,
        )
    assert exc.value.status_code == 403
    p = db.query(Payment).filter(Payment.razorpay_order_id == "order_payment-1").first()
    assert p.status == "pending"  # untouched


def test_verify_idempotent_on_duplicate(db, user, ride, fake_client, set_secrets):
    payment = _make_payment(db, user, ride, status="paid")
    payment.verified = 1
    db.commit()

    resp = payments_router.verify_payment(
        PaymentVerifyRequest(
            razorpay_order_id="order_payment-1",
            razorpay_payment_id="pay_ok3",
            razorpay_signature=_valid_signature("order_payment-1", "pay_ok3"),
        ),
        db,
        user,
    )
    assert resp.verified is True
    assert resp.message == "Payment already verified"
    # razorpay_payment_id unchanged — no duplicate side effects.
    db.refresh(payment)
    assert payment.razorpay_payment_id is None


def test_verify_rejects_terminal_failed_payment(db, user, ride, fake_client, set_secrets):
    _make_payment(db, user, ride, status="failed")
    with pytest.raises(HTTPException) as exc:
        payments_router.verify_payment(
            PaymentVerifyRequest(
                razorpay_order_id="order_payment-1",
                razorpay_payment_id="pay_ok4",
                razorpay_signature=_valid_signature("order_payment-1", "pay_ok4"),
            ),
            db,
            user,
        )
    assert exc.value.status_code == 409


def test_verify_rejects_amount_mismatch(db, user, ride, fake_client, set_secrets):
    payment = _make_payment(db, user, ride, amount=9999)
    with pytest.raises(HTTPException) as exc:
        payments_router.verify_payment(
            PaymentVerifyRequest(
                razorpay_order_id="order_payment-1",
                razorpay_payment_id="pay_ok5",
                razorpay_signature=_valid_signature("order_payment-1", "pay_ok5"),
            ),
            db,
            user,
        )
    assert exc.value.status_code == 400
    db.refresh(payment)
    assert payment.status == "pending"
    assert payment.failure_reason == "amount_mismatch"


# --- Webhooks ---

def test_webhook_marks_payment_paid(db, user, ride, set_webhook_secret):
    payment = _make_payment(db, user, ride)
    body, sig = _signed_body(_captured_payload())
    resp = _run_webhook(db, sig, json.loads(body))
    assert resp.received is True
    db.refresh(payment)
    assert payment.status == "paid"
    assert payment.verified == 1
    assert payment.razorpay_payment_id == "pay_w1"


def test_webhook_rejects_invalid_signature(db, user, ride, set_webhook_secret):
    payment = _make_payment(db, user, ride)
    body, _sig = _signed_body(_captured_payload())
    with pytest.raises(HTTPException) as exc:
        _run_webhook(db, "00" * 32, json.loads(body))
    assert exc.value.status_code == 400
    db.refresh(payment)
    assert payment.status == "pending"  # untouched


def test_webhook_duplicate_delivery_is_idempotent(db, user, ride, set_webhook_secret):
    payment = _make_payment(db, user, ride)
    body, sig = _signed_body(_captured_payload())
    payload = json.loads(body)

    # First delivery → paid.
    _run_webhook(db, sig, payload)
    db.refresh(payment)
    assert payment.status == "paid"

    # Duplicate delivery → no state change, no duplicate side effects.
    _run_webhook(db, sig, payload)
    db.refresh(payment)
    assert payment.status == "paid"
    assert payment.razorpay_payment_id == "pay_w1"


def test_webhook_payment_failed(db, user, ride, set_webhook_secret):
    payment = _make_payment(db, user, ride)
    body, sig = _signed_body(_captured_payload(event="payment.failed"))
    _run_webhook(db, sig, json.loads(body))
    db.refresh(payment)
    assert payment.status == "pending"
    assert payment.failure_reason == "razorpay_payment_failed"


def test_webhook_unknown_event_acknowledged(db, user, ride, set_webhook_secret):
    payment = _make_payment(db, user, ride)
    body, sig = _signed_body(_captured_payload(event="payout.processed"))
    resp = _run_webhook(db, sig, json.loads(body))
    assert resp.received is True
    db.refresh(payment)
    assert payment.status == "pending"


def test_webhook_unknown_order_acknowledged(db, user, set_webhook_secret):
    body, sig = _signed_body(_captured_payload(order_id="order_does_not_exist"))
    resp = _run_webhook(db, sig, json.loads(body))
    assert resp.received is True


def test_webhook_never_downgrades_paid_payment(db, user, ride, set_webhook_secret):
    """A late 'payment.failed' webhook must not un-pay a verified payment."""
    payment = _make_payment(db, user, ride, status="paid")
    payment.verified = 1
    db.commit()
    body, sig = _signed_body(_captured_payload(event="payment.failed"))
    _run_webhook(db, sig, json.loads(body))
    db.refresh(payment)
    assert payment.status == "paid"


# --- Razorpay client (HTTP layer, mocked) ---

def test_client_create_order_requires_config():
    client = RazorpayClient(key_id="", key_secret="")
    with pytest.raises(RazorpayError):
        client.create_order(amount=100, receipt="r1")


def test_client_create_order_http_error(monkeypatch):
    import httpx

    def raise_http_error(*args, **kwargs):
        raise httpx.ConnectError("connection failed")

    # The client calls httpx.request, not httpx.post: the wrong name leaves a real HTTPS call that an offline box "passes" by raising ConnectError.
    monkeypatch.setattr(razorpay_service.httpx, "request", raise_http_error)
    client = RazorpayClient(key_id="k", key_secret="s")
    with pytest.raises(RazorpayError):
        client.create_order(amount=100, receipt="r1")


def test_client_surface_never_exposes_secret():
    client = RazorpayClient(key_id="k", key_secret="super-secret-value")
    assert "super-secret-value" not in repr(client)


# --- One active payment per ride (create-order race) ---

def test_one_active_payment_per_ride_is_enforced_by_the_schema():
    """Two concurrent create-orders used to open two Razorpay orders for one ride; the partial unique index is the DB-level backstop."""
    from sqlalchemy.exc import IntegrityError

    engine = create_engine("sqlite:///:memory:")
    Payment.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    try:
        session.add(Payment(user_id=1, ride_request_id=7, amount=1500, currency="INR", status="created"))
        session.commit()
        session.add(Payment(user_id=1, ride_request_id=7, amount=1500, currency="INR", status="pending"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        # A failed attempt frees the slot; other rides and wallet rows never conflict.
        session.add(Payment(user_id=1, ride_request_id=7, amount=1500, currency="INR", status="failed"))
        session.commit()
        session.add(Payment(user_id=1, ride_request_id=8, amount=1500, currency="INR", status="created"))
        session.commit()
        session.add(Payment(user_id=1, ride_request_id=None, amount=1500, currency="INR", status="created"))
        session.commit()
        session.add(Payment(user_id=1, ride_request_id=None, amount=1500, currency="INR", status="created"))
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_create_order_resumes_the_winner_of_a_concurrent_insert(db, user, ride, fake_client, set_secrets, monkeypatch):
    """When the unique index rejects our insert, resume the payment that won the race instead of failing."""
    from sqlalchemy.exc import IntegrityError

    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)

    class _RaceLost:
        """Delegates to the real session, but the first commit loses to a concurrent insert."""

        def __init__(self, real):
            self._real = real
            self._fired = False

        def __getattr__(self, name):
            return getattr(self._real, name)

        def commit(self):
            if not self._fired:
                self._fired = True
                self._real.rollback()
                winner = Payment(
                    user_id=user.id, ride_request_id=ride.id, purpose="ride_fare",
                    amount=1500, currency="INR", status="pending",
                    razorpay_order_id="order_winner", verified=0,
                )
                self._real.add(winner)
                self._real.commit()
                raise IntegrityError("INSERT INTO payments", {}, Exception("uq_payments_one_active_per_ride"))
            return self._real.commit()

    resp = payments_router.create_payment_order(
        PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), _RaceLost(db), user
    )
    assert resp.razorpay_order_id == "order_winner"
    assert db.query(Payment).filter(Payment.ride_request_id == ride.id).count() == 1


def test_create_order_returns_the_first_attached_order_when_two_race(db, user, ride, set_secrets, monkeypatch):
    """Both requests can mint a Razorpay order for the same payment; only the first attach wins and the loser must return it."""
    monkeypatch.setattr(payments_router, "_route_distance_km", lambda ride: 1.0)

    def create_order(**kwargs):
        # The other request attaches its order while ours is in flight.
        payment_id = int(kwargs["receipt"].split("-")[1])
        other = db.query(Payment).filter(Payment.id == payment_id).first()
        other.razorpay_order_id = "order_other_request"
        other.status = "pending"
        db.commit()
        return {"id": "order_ours", "amount": kwargs["amount"], "currency": kwargs["currency"]}

    client = SimpleNamespace(create_order=create_order)
    monkeypatch.setattr(payments_router, "_client", client)
    monkeypatch.setattr(payments_router, "_require_razorpay_configured", lambda: client)

    resp = payments_router.create_payment_order(
        PaymentCreate(ride_request_id=ride.id, ride_option_id="swift-x"), db, user
    )
    assert resp.razorpay_order_id == "order_other_request"
    stored = db.query(Payment).filter(Payment.id == resp.payment_id).first()
    assert stored.razorpay_order_id == "order_other_request"


@pytest.mark.parametrize("iteration", range(3))
def test_parallel_checkouts_return_one_active_payment_and_order(tmp_path, set_secrets, monkeypatch, iteration):
    """Real separate sessions/threads and the actual partial unique index."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4

    engine = create_engine(f"sqlite:///{tmp_path / 'checkout-race.db'}", connect_args={"timeout": 15})
    _build_lite_schema().create_all(engine)
    next(index for index in Payment.__table__.indexes if index.name == "uq_payments_one_active_per_ride").create(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions() as setup:
        owner = User(name="Concurrent checkout", email="checkout-race@example.test", password_hash="x", role="passenger")
        setup.add(owner)
        setup.flush()
        booking = RideRequest(
            user_id=owner.id, pickup_lat=13, pickup_lng=77.6,
            dest_lat=13.1, dest_lng=77.7, status="completed", ride_option_id="swift-x",
        )
        setup.add(booking)
        setup.commit()
        owner_id, ride_id = owner.id, booking.id

    barrier = Barrier(2, timeout=15)

    def distance(ride):
        barrier.wait()
        return 1.0

    client = SimpleNamespace(create_order=lambda **kwargs: {
        "id": f"order_{uuid4().hex}", "amount": kwargs["amount"], "currency": "INR",
    })
    monkeypatch.setattr(payments_router, "_route_distance_km", distance)
    monkeypatch.setattr(payments_router, "_require_razorpay_configured", lambda: client)

    def checkout(_):
        with sessions() as session:
            return payments_router.create_payment_order(
                PaymentCreate(ride_request_id=ride_id, ride_option_id="swift-x"),
                session, session.get(User, owner_id),
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(checkout, range(2)))
        assert results[0].payment_id == results[1].payment_id
        assert results[0].razorpay_order_id == results[1].razorpay_order_id
        with sessions() as session:
            rows = session.query(Payment).all()
            assert len(rows) == 1
            assert rows[0].razorpay_order_id == results[0].razorpay_order_id
    finally:
        engine.dispose()
