"""Razorpay payment endpoints: create order, verify checkout, receive webhooks.

Security model:
  - All checkout endpoints require an authenticated user (Clerk/local JWT).
  - Amounts are computed server-side; nothing amount-related is accepted
    from the client.
  - The internal order is always validated to belong to the caller.
  - Only backend verification of the Razorpay signature marks a payment PAID.
  - The webhook endpoint verifies X-Razorpay-Signature against the raw body.
  - Everything is idempotent: duplicate verifications/webhooks are no-ops.
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from config import RAZORPAY_KEY_ID
from database import get_db
from models.payment import Payment
from models.ride_request import RideRequest
from models.user import User
from schemas.payment import (
    PaymentCheckoutResponse,
    PaymentCreate,
    PaymentResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
    WebhookResponse,
)
from services.razorpay_service import (
    VALID_FARE_IDS,
    RazorpayClient,
    RazorpayError,
    compute_fare_amount_paise,
    is_configured,
    verify_payment_signature,
    verify_webhook_signature,
)
from utils.auth_utils import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Injected in tests. Production default reads config lazily at call time.
_client: Optional[RazorpayClient] = None


def _get_client() -> RazorpayClient:
    global _client
    if _client is None:
        _client = RazorpayClient()
    return _client


def _require_razorpay_configured() -> RazorpayClient:
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payments are not configured on the server",
        )
    return _get_client()


def _get_owned_payment(db: Session, payment_id: int, current_user: User) -> Payment:
    """Fetch a payment enforcing ownership (owner or admin only)."""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment #{payment_id} not found",
        )
    if payment.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this payment",
        )
    return payment


def _route_distance_km(ride: RideRequest) -> float:
    """Server-side distance for fare computation.

    Uses the backend's own routing service (same source the UI shows);
    falls back to a haversine estimate if the routing provider is down.
    """
    from utils.geo import haversine_meters

    try:
        from services.stadia_client import extract_route_details, route as stadia_route

        data = stadia_route(ride.pickup_lat, ride.pickup_lng, ride.dest_lat, ride.dest_lng)
        details = extract_route_details(data)
        distance_km = float(details.get("distanceMeters") or 0) / 1000.0
        if distance_km > 0:
            return distance_km
    except Exception as exc:  # noqa: BLE001 — provider outage must not block booking
        logger.warning("Route distance unavailable (%s); using haversine fallback", exc.__class__.__name__)
    meters = haversine_meters(ride.pickup_lat, ride.pickup_lng, ride.dest_lat, ride.dest_lng)
    return meters / 1000.0


def _resolve_ride_amount(
    db: Session, current_user: User, ride_request_id: Optional[int], ride_option_id: str
) -> tuple[Optional[int], int]:
    """Validate the ride and return (ride_id, amount_paise) using server-side data only."""
    if ride_option_id not in VALID_FARE_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ride option",
        )

    ride_id = None
    distance_km = 0.0
    if ride_request_id is not None:
        ride = db.query(RideRequest).filter(RideRequest.id == ride_request_id).first()
        if not ride or ride.user_id != current_user.id:
            # 404 (not 403) so other users' ride IDs are never enumerated.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ride request #{ride_request_id} not found",
            )
        ride_id = ride.id
        distance_km = _route_distance_km(ride)

    try:
        amount = compute_fare_amount_paise(ride_option_id, distance_km)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ride option",
        ) from exc
    return ride_id, amount


def _fire_payment_notification(db: Session, payment: Payment, outcome: str) -> None:
    """Notify the rider via the existing notification service + WS push.

    Best-effort by design: the payment state is already committed, so a
    notification failure must never surface as a failed payment request.
    """
    from services.notifications import create_notification

    try:
        if outcome == "paid":
            create_notification(
                db,
                user_id=payment.user_id,
                notification_type="payment_received",
                title="Payment successful",
                message=f"Your payment of ₹{payment.amount / 100:.2f} was received. Thank you!",
                related_entity_type="payment",
                related_entity_id=payment.id,
            )
        else:
            create_notification(
                db,
                user_id=payment.user_id,
                notification_type="payment_failed",
                title="Payment failed",
                message="Your payment could not be completed. No amount has been charged.",
                related_entity_type="payment",
                related_entity_id=payment.id,
            )
        db.commit()
    except Exception as exc:  # noqa: BLE001 — never fail the payment over a notification
        db.rollback()
        logger.warning(
            "Payment notification failed (payment_id=%d): %s", payment.id, exc.__class__.__name__
        )


@router.post("/create-order", response_model=PaymentCheckoutResponse, status_code=status.HTTP_201_CREATED)
def create_payment_order(
    payment_in: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an internal Payment row + Razorpay Order for the authenticated user.

    Returns only public checkout data (Key ID, order ID, amount, customer
    info). The Key Secret never leaves the server.
    """
    client = _require_razorpay_configured()

    ride_id, amount = _resolve_ride_amount(
        db, current_user, payment_in.ride_request_id, payment_in.ride_option_id
    )

    # If the ride already has a paid payment, block duplicate charging.
    payment: Optional[Payment] = None
    if ride_id is not None:
        existing_paid = (
            db.query(Payment)
            .filter(Payment.ride_request_id == ride_id, Payment.status == "paid")
            .first()
        )
        if existing_paid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This ride has already been paid",
            )

        # Resume the user's most recent unpaid payment for this ride instead of
        # creating a second Razorpay order. Prevents double-charging when a
        # previous attempt failed after checkout (e.g. transient network error
        # during verification) but the customer may already have been charged.
        resumable = (
            db.query(Payment)
            .filter(
                Payment.ride_request_id == ride_id,
                Payment.user_id == current_user.id,
                Payment.status.in_(("created", "pending")),
            )
            .order_by(Payment.id.desc())
            .first()
        )
        if resumable is not None and (resumable.amount != amount or resumable.currency != "INR"):
            # Fare changed since the old attempt — retire it and start fresh.
            resumable.status = "failed"
            resumable.failure_reason = "superseded_by_new_order"
            db.commit()
            resumable = None
        payment = resumable

    if payment is None:
        payment = Payment(
            user_id=current_user.id,
            ride_request_id=ride_id,
            purpose="ride_fare",
            amount=amount,
            currency="INR",
            status="created",
            verified=0,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

    if payment.razorpay_order_id:
        # Resumed payment that already has a Razorpay order — reopen checkout
        # for the SAME order. Razorpay allows only one successful payment per
        # order, so this can never double-charge.
        logger.info(
            "Resuming existing payment: payment_id=%d order_id=%s",
            payment.id,
            payment.razorpay_order_id,
        )
        return PaymentCheckoutResponse(
            payment_id=payment.id,
            internal_order_id=payment.id,
            razorpay_key_id=RAZORPAY_KEY_ID,
            razorpay_order_id=payment.razorpay_order_id,
            amount=payment.amount,
            currency=payment.currency,
            customer_name=current_user.name,
            customer_email=current_user.email,
            customer_phone=current_user.phone or None,
            ride_request_id=payment.ride_request_id,
            ride_option_name=payment_in.ride_option_id,
        )

    try:
        order = client.create_order(
            amount=amount,
            currency="INR",
            receipt=f"payment-{payment.id}",
            notes={
                "payment_id": str(payment.id),
                "ride_request_id": str(ride_id) if ride_id else "",
                "user_id": str(current_user.id),
            },
        )
    except RazorpayError as exc:
        # Record the failure for diagnostics; the payment stays non-paid.
        payment.status = "failed"
        payment.failure_reason = "razorpay_order_creation_failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider is unavailable, please try again",
        ) from exc

    payment.razorpay_order_id = order.get("id")
    payment.status = "pending"
    db.commit()
    db.refresh(payment)

    logger.info(
        "Razorpay order created: payment_id=%d order_id=%s amount=%d",
        payment.id,
        payment.razorpay_order_id,
        amount,
    )

    return PaymentCheckoutResponse(
        payment_id=payment.id,
        internal_order_id=payment.id,
        razorpay_key_id=RAZORPAY_KEY_ID,
        razorpay_order_id=order.get("id"),
        amount=payment.amount,
        currency=payment.currency,
        customer_name=current_user.name,
        customer_email=current_user.email,
        customer_phone=current_user.phone or None,
        ride_request_id=payment.ride_request_id,
        ride_option_name=payment_in.ride_option_id,
    )


@router.post("/verify", response_model=PaymentVerifyResponse)
def verify_payment(
    verify_in: PaymentVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify the Checkout signature server-side and mark the payment PAID.

    Idempotent: re-verification of an already-verified payment returns the
    same success state without side effects.
    """
    _require_razorpay_configured()

    # Look up by Razorpay order ID, enforcing ownership.
    payment = (
        db.query(Payment)
        .filter(Payment.razorpay_order_id == verify_in.razorpay_order_id)
        .first()
    )
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found for this order",
        )
    if payment.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this payment",
        )

    # Idempotency: already verified → return current state unchanged.
    if payment.status == "paid" and payment.verified == 1:
        return PaymentVerifyResponse(
            payment_id=payment.id,
            status=payment.status,
            verified=True,
            ride_request_id=payment.ride_request_id,
            message="Payment already verified",
        )

    if payment.status not in ("created", "pending"):
        # failed/refunded are terminal unless a webhook changes them.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Payment is in status '{payment.status}' and cannot be verified",
        )

    # 1. Signature must verify before anything else.
    if not verify_payment_signature(
        verify_in.razorpay_order_id,
        verify_in.razorpay_payment_id,
        verify_in.razorpay_signature,
    ):
        payment.status = "failed"
        payment.failure_reason = "signature_verification_failed"
        db.commit()
        logger.warning(
            "Payment signature verification failed: payment_id=%d user_id=%d",
            payment.id,
            payment.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed",
        )

    # 2. Defence in depth: confirm via the Razorpay API that the payment
    #    belongs to the stored order and matches amount/currency/state.
    try:
        rzp_payment = _require_razorpay_configured().fetch_payment(verify_in.razorpay_payment_id)
    except RazorpayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider is unavailable, please try again",
        ) from exc

    if rzp_payment.get("order_id") != verify_in.razorpay_order_id:
        payment.status = "failed"
        payment.failure_reason = "order_mismatch"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment does not belong to this order",
        )
    if int(rzp_payment.get("amount", -1)) != payment.amount or rzp_payment.get("currency") != payment.currency:
        payment.status = "failed"
        payment.failure_reason = "amount_mismatch"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount does not match the order",
        )
    if rzp_payment.get("status") not in ("captured", "authorized"):
        payment.status = "failed"
        payment.failure_reason = "payment_not_captured"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment was not successful",
        )

    # 3. All checks passed → mark PAID exactly once.
    payment.status = "paid"
    payment.verified = 1
    payment.razorpay_payment_id = verify_in.razorpay_payment_id
    payment.razorpay_metadata = {
        "verify": {
            "razorpay_payment_id": verify_in.razorpay_payment_id,
            "razorpay_order_id": verify_in.razorpay_order_id,
        }
    }
    db.commit()
    db.refresh(payment)

    logger.info("Payment verified: payment_id=%d amount=%d", payment.id, payment.amount)

    if payment.ride_request_id:
        _fire_payment_notification(db, payment, "paid")

    return PaymentVerifyResponse(
        payment_id=payment.id,
        status=payment.status,
        verified=True,
        ride_request_id=payment.ride_request_id,
        message="Payment verified",
    )


@router.post("/webhook", response_model=WebhookResponse)
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Razorpay webhook receiver.

    Verifies X-Razorpay-Signature against the RAW request body using the
    webhook secret, then updates payment state idempotently. There is no
    user authentication by design — the signature IS the authentication.
    """
    signature = request.headers.get("X-Razorpay-Signature", "")
    body = await request.body()

    if not verify_webhook_signature(body, signature):
        logger.warning("Razorpay webhook rejected: invalid signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        ) from exc

    event = payload.get("event", "")
    entity_payload = payload.get("payload") or {}
    payment_entity = (entity_payload.get("payment") or {}).get("entity") or {}
    razorpay_order_id = payment_entity.get("order_id")
    razorpay_payment_id = payment_entity.get("id")

    logger.info(
        "Razorpay webhook received: event=%s order_id=%s",
        event,
        razorpay_order_id or "<none>",
    )

    if not razorpay_order_id:
        # Events without an order entity (e.g. payout events) — acknowledge.
        return WebhookResponse(received=True)

    payment = (
        db.query(Payment)
        .filter(Payment.razorpay_order_id == razorpay_order_id)
        .first()
    )
    if not payment:
        logger.info("Webhook for unknown order %s — acknowledged", razorpay_order_id)
        return WebhookResponse(received=True)

    # Idempotency: never downgrade or duplicate a paid payment.
    if payment.status == "paid" and event != "refund.processed":
        return WebhookResponse(received=True)

    if event in ("payment.captured", "payment.authorized"):
        payment.status = "paid"
        payment.verified = 1
        payment.razorpay_payment_id = razorpay_payment_id or payment.razorpay_payment_id
        payment.razorpay_metadata = {"webhook": {"event": event}}
        db.commit()
        if payment.ride_request_id:
            _fire_payment_notification(db, payment, "paid")
    elif event == "payment.failed":
        if payment.status != "paid":
            payment.status = "failed"
            payment.failure_reason = "razorpay_payment_failed"
            payment.razorpay_metadata = {"webhook": {"event": event}}
            db.commit()
            if payment.ride_request_id:
                _fire_payment_notification(db, payment, "failed")
    elif event == "refund.processed":
        if payment.status == "paid":
            payment.status = "refunded"
            payment.razorpay_metadata = {"webhook": {"event": event}}
            db.commit()
    else:
        # Unknown event types are acknowledged but not acted upon.
        logger.info("Unhandled webhook event: %s", event)

    return WebhookResponse(received=True)


@router.get("/mine", response_model=List[PaymentResponse])
def list_my_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the authenticated user's payments (no secrets in payloads)."""
    return (
        db.query(Payment)
        .filter(Payment.user_id == current_user.id)
        .order_by(Payment.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch one payment. Owner or admin only."""
    return _get_owned_payment(db, payment_id, current_user)
