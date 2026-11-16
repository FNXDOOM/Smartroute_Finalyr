"""Real Postgres sessions/indexes; provider calls remain deterministic mocks."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest

from database import SessionLocal, engine
from models.payment import Payment
from models.ride_request import RideRequest
from models.user import User
from routers import payments
from schemas.payment import PaymentCreate


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Requires the explicitly configured isolated PostgreSQL/PostGIS test database",
)


@pytest.mark.parametrize("iteration", range(5))
def test_parallel_postgres_checkouts_return_one_payment_and_order(monkeypatch, iteration):
    with SessionLocal() as db:
        user = User(
            name="Postgres QA", email=f"pg-checkout-{uuid4().hex}@example.test",
            password_hash="test_only", role="passenger",
        )
        db.add(user)
        db.flush()
        ride = RideRequest(
            user_id=user.id, pickup_lat=13, pickup_lng=77.6,
            dest_lat=13.1, dest_lng=77.7, status="pending", ride_option_id="swift-x",
        )
        db.add(ride)
        db.commit()
        user_id, ride_id = user.id, ride.id

    barrier = Barrier(2, timeout=15)

    def distance(ride):
        barrier.wait()
        return 1.0

    client = SimpleNamespace(create_order=lambda **kwargs: {
        "id": f"order_test_{uuid4().hex}", "amount": kwargs["amount"], "currency": "INR",
    })
    monkeypatch.setattr(payments, "_route_distance_km", distance)
    monkeypatch.setattr(payments, "_require_razorpay_configured", lambda: client)
    monkeypatch.setattr(payments, "RAZORPAY_KEY_ID", "rzp_test_not_live")

    def checkout(_):
        with SessionLocal() as db:
            return payments.create_payment_order(
                PaymentCreate(ride_request_id=ride_id, ride_option_id="swift-x"),
                db, db.get(User, user_id),
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(checkout, range(2)))
        assert results[0].payment_id == results[1].payment_id
        assert results[0].razorpay_order_id == results[1].razorpay_order_id
        with SessionLocal() as db:
            rows = db.query(Payment).filter(Payment.ride_request_id == ride_id).all()
            assert len(rows) == 1
            assert rows[0].status == "pending"
            assert rows[0].razorpay_order_id == results[0].razorpay_order_id
    finally:
        with SessionLocal() as db:
            db.query(Payment).filter(Payment.ride_request_id == ride_id).delete(synchronize_session=False)
            db.query(RideRequest).filter(RideRequest.id == ride_id).delete(synchronize_session=False)
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()
