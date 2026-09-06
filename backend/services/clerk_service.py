import logging
from typing import Any, Dict, Optional
import httpx

from config import CLERK_SECRET_KEY

logger = logging.getLogger(__name__)
CLERK_API_BASE = "https://api.clerk.com/v1"


def sync_clerk_user_metadata(
    clerk_user_id: str,
    public_metadata: Dict[str, Any],
) -> bool:
    """
    Synchronize user metadata (e.g. role, driver_status) back into Clerk's publicMetadata.
    Requires CLERK_SECRET_KEY in environment variables. If omitted, operates gracefully
    without raising fatal errors.
    """
    if not clerk_user_id:
        return False

    if not CLERK_SECRET_KEY:
        logger.info(
            "CLERK_SECRET_KEY not set; skipped remote Clerk metadata sync for user %s. Local DB updated.",
            clerk_user_id,
        )
        return False

    url = f"{CLERK_API_BASE}/users/{clerk_user_id}/metadata"
    headers = {
        "Authorization": f"Bearer {CLERK_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"public_metadata": public_metadata}

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.patch(url, headers=headers, json=payload)
            if response.status_code in (200, 204):
                logger.info("Successfully updated Clerk publicMetadata for %s: %s", clerk_user_id, public_metadata)
                return True
            else:
                logger.warning(
                    "Failed to update Clerk publicMetadata for %s. Status %d: %s",
                    clerk_user_id,
                    response.status_code,
                    response.text,
                )
                return False
    except Exception as exc:
        logger.warning("Error communicating with Clerk API for user %s: %s", clerk_user_id, exc)
        return False
