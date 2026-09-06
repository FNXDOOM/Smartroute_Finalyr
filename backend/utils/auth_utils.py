import bcrypt
import logging
import secrets
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from config import (
    ALLOWED_ORIGINS,
    AUTH_PROVIDER,
    CLERK_AUDIENCE,
    CLERK_ALLOW_NATIVE_CLIENTS,
    CLERK_AUTHORIZED_PARTIES,
    CLERK_ISSUER,
    CLERK_JWKS_URL,
    CLERK_SECRET_KEY,
)
from database import get_db
from models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="")
logger = logging.getLogger(__name__)
_clerk_jwks_client: Optional[jwt.PyJWKClient] = None


def get_websocket_token(websocket: WebSocket) -> Optional[str]:
    """Extract a bearer token without putting it in the WebSocket URL.

    Browsers cannot set arbitrary WebSocket headers, so the frontend sends the
    token as the second WebSocket subprotocol: ``bearer, <JWT>``. A secure
    HttpOnly cookie is also accepted for deployments that terminate auth at a
    gateway. Query-string tokens are intentionally rejected.
    """
    authorization = websocket.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None

    protocols = [part.strip() for part in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    if len(protocols) >= 2 and protocols[0].lower() == "bearer":
        return protocols[1] or None

    return websocket.cookies.get("access_token")


def get_jwks_client() -> jwt.PyJWKClient:
    """Lazily initialize and return the PyJWKClient for Clerk."""
    global _clerk_jwks_client
    if _clerk_jwks_client is None:
        if not CLERK_JWKS_URL:
            raise HTTPException(
                status_code=500,
                detail="CLERK_JWKS_URL is not configured in backend environment",
            )
        _clerk_jwks_client = jwt.PyJWKClient(CLERK_JWKS_URL)
    return _clerk_jwks_client


def hash_password(password: str) -> str:
    """Hash a seed-only placeholder password for legacy fixture data."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def decode_clerk_token(token: str) -> dict:
    """Verify a Clerk session JWT using Clerk's published JWKS keys."""
    if AUTH_PROVIDER != "clerk":
        raise HTTPException(status_code=500, detail="Clerk authentication is not enabled")

    try:
        client = get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        options = {"verify_aud": bool(CLERK_AUDIENCE)}
        # Clerk instances may serialize the issuer with or without a trailing slash.
        # Verify the signature first, then compare normalized issuer values below.
        kwargs = {"options": {**options, "verify_iss": False}}
        if CLERK_AUDIENCE:
            kwargs["audience"] = CLERK_AUDIENCE
        # Allow minor clock drift between the local backend machine and Clerk.
        # This still enforces iat/nbf/exp; it only tolerates up to one minute skew.
        payload = jwt.decode(token, signing_key.key, algorithms=["RS256"], leeway=60, **kwargs)
        token_issuer = str(payload.get("iss", "")).rstrip("/")
        expected_issuer = CLERK_ISSUER.rstrip("/")
        if not expected_issuer or token_issuer != expected_issuer:
            raise jwt.InvalidIssuerError(
                f"Clerk token issuer '{token_issuer}' does not match configured issuer '{expected_issuer}'"
            )
        authorized_parties = CLERK_AUTHORIZED_PARTIES or ALLOWED_ORIGINS
        token_azp = payload.get("azp")
        native_client_without_azp = CLERK_ALLOW_NATIVE_CLIENTS and not token_azp
        if authorized_parties and not native_client_without_azp and (
            not token_azp or str(token_azp).rstrip("/") not in authorized_parties
        ):
            raise jwt.InvalidAudienceError("Clerk token authorized party is not allowed")
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=401, detail="Clerk token has expired", headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        logger.warning("Clerk token rejected: %s: %s", exc.__class__.__name__, exc)
        raise HTTPException(
            status_code=401, detail="Invalid Clerk authentication token", headers={"WWW-Authenticate": "Bearer"}
        ) from exc


def get_clerk_user_profile(clerk_user_id: str) -> dict:
    """Fetch profile fields omitted from a standard Clerk session token."""
    if not CLERK_SECRET_KEY:
        return {}

    request = Request(
        f"https://api.clerk.com/v1/users/{clerk_user_id}",
        headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Could not fetch Clerk profile for %s: %s", clerk_user_id, exc)
        return {}


def get_profile_fields(payload: dict, clerk_user_id: str) -> tuple[str, str]:
    """Resolve display name and email from the token or Clerk's user profile."""
    email = payload.get("email") or payload.get("email_address")
    name = payload.get("name") or payload.get("first_name")
    if email and name:
        return str(name), str(email)

    profile = get_clerk_user_profile(clerk_user_id)
    email_addresses = profile.get("email_addresses") or []
    primary_email_id = profile.get("primary_email_address_id")
    primary_email = next(
        (item.get("email_address") for item in email_addresses if item.get("id") == primary_email_id),
        None,
    )
    email = email or primary_email or (email_addresses[0].get("email_address") if email_addresses else None)
    first_name = profile.get("first_name") or ""
    last_name = profile.get("last_name") or ""
    name = name or " ".join(part for part in (first_name, last_name) if part).strip()
    return name or "Clerk User", email or f"{clerk_user_id}@clerk.local"


def get_or_create_user_from_payload(payload: dict, db: Session) -> User:
    """Retrieve or automatically provision a User from a decoded Clerk JWT payload."""
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(
            status_code=401, detail="Clerk token missing subject claim", headers={"WWW-Authenticate": "Bearer"}
        )

    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
    if user is None:
        name, email = get_profile_fields(payload, clerk_user_id)
        user = User(
            name=name,
            email=email,
            password_hash=secrets.token_urlsafe(32),
            clerk_user_id=clerk_user_id,
            role="passenger",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.email.endswith("@clerk.local") or user.name == "Clerk User":
        name, email = get_profile_fields(payload, clerk_user_id)
        user.name = name
        user.email = email
        db.commit()
        db.refresh(user)
    return user


def get_user_from_token(token: str, db: Session) -> User:
    """Verify the Clerk token and return the associated database User model."""
    payload = decode_clerk_token(token)
    return get_or_create_user_from_payload(payload, db)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """FastAPI dependency to verify the Clerk token and return the mapped application profile."""
    return get_user_from_token(token, db)


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Restrict access to admin users."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user
