import bcrypt
import logging
import secrets
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from config import (
    ALLOWED_ORIGINS,
    AUTH_PROVIDER,
    CLERK_AUDIENCE,
    CLERK_AUTHORIZED_PARTIES,
    CLERK_ISSUER,
    CLERK_JWKS_URL,
)
from database import get_db
from models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="")
logger = logging.getLogger(__name__)
_clerk_jwks_client: Optional[jwt.PyJWKClient] = None


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
        if authorized_parties and (not token_azp or str(token_azp).rstrip("/") not in authorized_parties):
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


def get_or_create_user_from_payload(payload: dict, db: Session) -> User:
    """Retrieve or automatically provision a User from a decoded Clerk JWT payload."""
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(
            status_code=401, detail="Clerk token missing subject claim", headers={"WWW-Authenticate": "Bearer"}
        )

    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
    if user is None:
        email = payload.get("email") or payload.get("email_address") or f"{clerk_user_id}@clerk.local"
        name = payload.get("name") or payload.get("first_name") or "Clerk User"
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
