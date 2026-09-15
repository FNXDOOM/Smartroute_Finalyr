"""Server-side Razorpay client and payment helpers.

The Razorpay Key Secret and Webhook Secret live ONLY here (server side).
No function in this module returns a secret, and no secret is ever logged.

Integration follows Razorpay's current recommended flow:
  1. Backend creates a Razorpay Order (amount comes from server-side fares).
  2. Frontend opens Razorpay Checkout with the public Key ID + order_id.
  3. Backend verifies the checkout signature (HMAC-SHA256 of
     ``razorpay_order_id|razorpay_payment_id`` keyed by the Key Secret).
  4. Webhooks are verified with HMAC-SHA256 of the raw request body keyed by
     the Webhook Secret (X-Razorpay-Signature header).
"""

import hashlib
import hmac
import logging
import time
from typing import Any, Dict, Optional

import httpx

from config import RAZORPAY_API_BASE, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET

logger = logging.getLogger(__name__)

RAZORPAY_CHECKOUT_SCRIPT = "https://checkout.razorpay.com/v1/checkout.js"

# Server-side fare table. Prices are in RUPEES; converted to paise (x100)
# when a Razorpay order is created. The client NEVER supplies amounts —
# it may only name one of these option IDs.
RIDE_FARES: Dict[str, Dict[str, Any]] = {
    "swift-x": {"name": "SwiftX", "base_rupees": 12, "per_km_rupees": 6, "min_rupees": 12, "max_rupees": 15},
    "swift-xl": {"name": "SwiftXL", "base_rupees": 18, "per_km_rupees": 8, "min_rupees": 18, "max_rupees": 22},
    "swift-lux": {"name": "Lux Black", "base_rupees": 32, "per_km_rupees": 14, "min_rupees": 32, "max_rupees": 40},
    "swift-moto": {"name": "Moto", "base_rupees": 6, "per_km_rupees": 4, "min_rupees": 6, "max_rupees": 9},
}

VALID_FARE_IDS = set(RIDE_FARES)

# Transient network failures worth retrying (DNS blips, VPN/proxy toggles,
# connection resets). Real HTTP error responses (4xx/5xx) are NOT retried —
# they are definitive answers and must fail fast.
_TRANSIENT_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)
RAZORPAY_HTTP_ATTEMPTS = 3
RAZORPAY_RETRY_BACKOFF_SECONDS = 0.5


def is_configured() -> bool:
    """True when Razorpay credentials are present in the environment."""
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


class RazorpayError(Exception):
    """Raised when the Razorpay API request fails.

    The exception message intentionally contains no secret material and no
    raw Razorpay error bodies (those can echo back auth challenges).
    """


class RazorpayClient:
    """Minimal Razorpay Orders API client (basic auth, httpx).

    Mirrors the project's service-client pattern (see stadia_client.py,
    clerk_service.py): small, dependency-light, dependency-injection friendly.
    """

    def __init__(self, key_id: Optional[str] = None, key_secret: Optional[str] = None, timeout: float = 10.0):
        self._key_id = key_id if key_id is not None else RAZORPAY_KEY_ID
        self._key_secret = key_secret if key_secret is not None else RAZORPAY_KEY_SECRET
        self._timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self._key_id and self._key_secret)

    def _request(self, method: str, url: str, **kwargs):
        """HTTP request with bounded retry on transient connection errors.

        Intermittent ``ConnectError`` (VPN/proxy toggles, DNS blips, firewall)
        is the main cause of "checkout succeeded but verification failed":
        the payment itself happens in the browser, so only the backend's
        outbound Razorpay call fails. Retries only transient exceptions;
        HTTP error responses still fail fast. Never logs secrets or bodies.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, RAZORPAY_HTTP_ATTEMPTS + 1):
            try:
                return httpx.request(method, url, **kwargs)
            except _TRANSIENT_EXCEPTIONS as exc:
                last_exc = exc
                if attempt >= RAZORPAY_HTTP_ATTEMPTS:
                    break
                delay = RAZORPAY_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Razorpay API %s transient failure (%s); retrying in %.1fs (attempt %d/%d)",
                    method,
                    exc.__class__.__name__,
                    delay,
                    attempt + 1,
                    RAZORPAY_HTTP_ATTEMPTS,
                )
                time.sleep(delay)
        logger.error(
            "Razorpay API %s failed after %d attempts: %s",
            method,
            RAZORPAY_HTTP_ATTEMPTS,
            last_exc.__class__.__name__ if last_exc else "unknown",
        )
        raise last_exc  # type: ignore[misc]

    def create_order(self, *, amount: int, currency: str = "INR", receipt: str, notes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a Razorpay Order. ``amount`` is in paise."""
        if not self.is_configured:
            raise RazorpayError("Razorpay is not configured on the server")
        try:
            response = self._request(
                "POST",
                f"{RAZORPAY_API_BASE}/orders",
                auth=(self._key_id, self._key_secret),
                json={
                    "amount": int(amount),
                    "currency": currency,
                    "receipt": receipt,
                    "notes": notes or {},
                },
                timeout=self._timeout,
            )
        except (httpx.HTTPError, httpx.StreamError) as exc:
            logger.error("Razorpay order creation request failed: %s", exc.__class__.__name__)
            raise RazorpayError("Razorpay order request failed") from exc
        if response.status_code not in (200, 201):
            # Log only the status code — never the response body (may echo auth data).
            logger.error(
                "Razorpay order creation failed with HTTP %d", response.status_code
            )
            raise RazorpayError(f"Razorpay order creation failed (HTTP {response.status_code})")
        return response.json()

    def fetch_payment(self, payment_id: str) -> Dict[str, Any]:
        """Fetch a payment entity from Razorpay (used for defence-in-depth checks)."""
        if not self.is_configured:
            raise RazorpayError("Razorpay is not configured on the server")
        try:
            response = self._request(
                "GET",
                f"{RAZORPAY_API_BASE}/payments/{payment_id}",
                auth=(self._key_id, self._key_secret),
                timeout=self._timeout,
            )
        except (httpx.HTTPError, httpx.StreamError) as exc:
            logger.error("Razorpay payment fetch failed: %s", exc.__class__.__name__)
            raise RazorpayError("Razorpay payment fetch failed") from exc
        if response.status_code != 200:
            logger.error("Razorpay payment fetch failed with HTTP %d", response.status_code)
            raise RazorpayError(f"Razorpay payment fetch failed (HTTP {response.status_code})")
        return response.json()


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    signature: str,
    *,
    key_secret: Optional[str] = None,
) -> bool:
    """Verify the Checkout handler signature:

    HMAC-SHA256(order_id + '|' + payment_id, key_secret) == signature.
    """
    secret = key_secret if key_secret is not None else RAZORPAY_KEY_SECRET
    if not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def verify_webhook_signature(body: bytes, signature: str, *, webhook_secret: Optional[str] = None) -> bool:
    """Verify the webhook signature:

    HMAC-SHA256(raw_request_body, webhook_secret) == X-Razorpay-Signature.
    """
    secret = webhook_secret if webhook_secret is not None else RAZORPAY_WEBHOOK_SECRET
    if not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def compute_fare_amount_paise(ride_option_id: str, distance_km: float) -> int:
    """Compute the ride fare in paise from the server-side fare table.

    ``distance_km`` comes from the server-side route estimate (backend
    routing), never from the client. Result is clamped to the tier's
    [min, max] band and rounded to the nearest rupee.
    """
    fare = RIDE_FARES.get(ride_option_id)
    if fare is None:
        raise ValueError(f"Unknown ride option: {ride_option_id}")
    rupees = fare["base_rupees"] + fare["per_km_rupees"] * max(0.0, float(distance_km))
    rupees = max(fare["min_rupees"], min(fare["max_rupees"], round(rupees)))
    return int(round(rupees * 100))
