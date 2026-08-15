import bcrypt
import secrets

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from config import AUTH_PROVIDER, CLERK_AUDIENCE, CLERK_ISSUER, CLERK_JWKS_URL
from database import get_db
from models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="")
clerk_jwks_client = jwt.PyJWKClient(CLERK_JWKS_URL)


def hash_password(password: str) -> str:
    """Hash a seed-only placeholder password for legacy fixture data."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def decode_clerk_token(token: str) -> dict:
    """Verify a Clerk session JWT using Clerk's published JWKS keys."""
    if AUTH_PROVIDER != "clerk":
        raise HTTPException(status_code=500, detail="Clerk authentication is not enabled")

    try:
        signing_key = clerk_jwks_client.get_signing_key_from_jwt(token)
        options = {"verify_aud": bool(CLERK_AUDIENCE)}
        kwargs = {"issuer": CLERK_ISSUER, "options": options}
        if CLERK_AUDIENCE:
            kwargs["audience"] = CLERK_AUDIENCE
        return jwt.decode(token, signing_key.key, algorithms=["RS256"], **kwargs)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Clerk token has expired", headers={"WWW-Authenticate": "Bearer"}) from exc
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Clerk authentication token", headers={"WWW-Authenticate": "Bearer"}) from exc


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Verify the Clerk token and return the mapped application profile."""
    payload = decode_clerk_token(token)
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Clerk token missing subject claim", headers={"WWW-Authenticate": "Bearer"})

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


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Restrict access to admin users."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user
