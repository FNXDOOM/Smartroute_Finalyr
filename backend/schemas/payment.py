"""Pydantic schemas for payment endpoints."""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    """Request to start a Razorpay checkout.

    NOTE: no amount/price field exists here BY DESIGN — the backend computes
    the payable amount from server-side data (fare table + route distance).
    """

    ride_request_id: Optional[int] = Field(
        None, ge=1, description="Ride to pay for (optional for wallet top-ups)"
    )
    ride_option_id: str = Field(
        ...,
        min_length=2,
        max_length=40,
        description="Ride option ID; amount is resolved server-side",
    )


class PaymentCheckoutResponse(BaseModel):
    """Everything Checkout needs — contains only PUBLIC values.

    The Razorpay Key Secret is never included in any response schema.
    """

    payment_id: int
    internal_order_id: int
    razorpay_key_id: str
    razorpay_order_id: str
    amount: int = Field(..., description="Amount in paise")
    currency: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    ride_request_id: Optional[int] = None
    ride_option_name: Optional[str] = None


class PaymentVerifyRequest(BaseModel):
    """Checkout handler payload posted back for server-side verification."""

    razorpay_order_id: str = Field(..., min_length=1, max_length=64)
    razorpay_payment_id: str = Field(..., min_length=1, max_length=64)
    razorpay_signature: str = Field(..., min_length=1, max_length=256)


class PaymentResponse(BaseModel):
    """Internal payment record. Contains no Razorpay secrets."""

    id: int
    user_id: int
    ride_request_id: Optional[int] = None
    purpose: str
    amount: int
    currency: str
    status: str
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    verified: bool
    failure_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PaymentVerifyResponse(BaseModel):
    payment_id: int
    status: str
    verified: bool
    ride_request_id: Optional[int] = None
    message: Optional[str] = None


class WebhookResponse(BaseModel):
    received: bool
