"""Payment records for Razorpay checkout — source of truth for payment state."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func

from database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    # Owning user; set from the authenticated principal, never from the client.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Optional ride linkage (ride fare payments).
    ride_request_id = Column(Integer, ForeignKey("ride_requests.id"), nullable=True, index=True)
    # ride_fare | wallet_topup (future wallet feature)
    purpose = Column(String, default="ride_fare", nullable=False)
    # Server-computed amount in paise. Never accepted from the client.
    amount = Column(Integer, nullable=False)
    currency = Column(String, default="INR", nullable=False)
    # created | pending | paid | failed | refunded (lowercase per project convention)
    status = Column(String, default="created", nullable=False, index=True)
    razorpay_order_id = Column(String, nullable=True, index=True)
    razorpay_payment_id = Column(String, nullable=True)
    # Server-side signature verification result: 0 = unverified, 1 = verified.
    verified = Column(Integer, default=0, nullable=False)
    failure_reason = Column(String, nullable=True)
    # Raw Razorpay event payloads (webhooks / callbacks) for diagnostics.
    # Named razorpay_metadata in Python; column is "metadata" (JSON),
    # mirroring the Notification model pattern.
    razorpay_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} user_id={self.user_id} amount={self.amount} "
            f"status={self.status} rzp_order={self.razorpay_order_id}>"
        )
