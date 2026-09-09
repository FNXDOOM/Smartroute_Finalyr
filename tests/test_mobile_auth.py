"""Local auth + mobile WebSocket compat tests."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import Base  # noqa: E402  (Base only; tables created selectively below)
from models.user import User  # noqa: E402
from routers.auth import login_local_user, register_local_user  # noqa: E402
from schemas.user import UserLogin, UserRegister  # noqa: E402
from services.notifications import manager as notif_manager  # noqa: E402
from utils.auth_utils import (  # noqa: E402
    create_local_token,
    decode_clerk_token,
    decode_local_token,
    get_user_from_token,
    get_websocket_token,
    hash_password,
    verify_password,
)

test_engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
# Only users table; full metadata needs SpatiaLite
User.__table__.create(bind=test_engine)


def _db():
    return TestingSessionLocal()


# Password hashing

def test_password_roundtrip():
    hashed = hash_password("password123")
    assert hashed != "password123"
    assert verify_password("password123", hashed) is True
    assert verify_password("wrong-password", hashed) is False
    assert verify_password("anything", "not-a-valid-hash") is False


# Local token helpers

def test_local_token_roundtrip():
    token = create_local_token(42)
    assert decode_local_token(token) == 42


def test_local_token_rejects_garbage_and_foreign_tokens():
    assert decode_local_token("garbage") is None
    assert decode_local_token("") is None
    # Clerk payload must never pass as local token
    import jwt

    from config import LOCAL_JWT_SECRET

    foreign = jwt.encode({"sub": "clerk_user_123"}, LOCAL_JWT_SECRET, algorithm="HS256")
    assert decode_local_token(foreign) is None


# Register/login endpoint tests

def test_register_then_login_flow():
    db = _db()
    try:
        response = register_local_user(
            UserRegister(
                name="Mobile Rider",
                email="mobile.rider@example.com",
                password="password123",
                phone="+911234567890",
            ),
            db,
        )
        assert response.token_type == "bearer"
        assert response.access_token
        assert response.user.email == "mobile.rider@example.com"
        assert response.user.role == "passenger"
        user_id = response.user.id

        # Correct credentials return same user
        login = login_local_user(
            UserLogin(email="mobile.rider@example.com", password="password123"), db
        )
        assert login.user.id == user_id
        assert decode_local_token(login.access_token) == user_id

        # Token auths via shared dep, no JWKS
        authed = get_user_from_token(login.access_token, db)
        assert authed.id == user_id
        assert authed.email == "mobile.rider@example.com"
    finally:
        db.close()


def test_register_rejects_duplicate_email():
    db = _db()
    try:
        register_local_user(
            UserRegister(name="Dupe", email="dupe@example.com", password="password123"),
            db,
        )
        with pytest.raises(HTTPException) as exc_info:
            register_local_user(
                UserRegister(name="Dupe 2", email="DUPE@example.com", password="password123"),
                db,
            )
        assert exc_info.value.status_code == 400
    finally:
        db.close()


def test_login_rejects_bad_credentials():
    db = _db()
    try:
        with pytest.raises(HTTPException) as exc_info:
            login_local_user(
                UserLogin(email="nobody@example.com", password="password123"), db
            )
        assert exc_info.value.status_code == 401

        register_local_user(
            UserRegister(name="Real", email="real@example.com", password="password123"),
            db,
        )
        with pytest.raises(HTTPException) as exc_info:
            login_local_user(
                UserLogin(email="real@example.com", password="wrong"), db
            )
        assert exc_info.value.status_code == 401
    finally:
        db.close()


def test_unknown_local_user_id_is_rejected():
    db = _db()
    try:
        orphan = create_local_token(999999)
        with pytest.raises(HTTPException) as exc_info:
            get_user_from_token(orphan, db)
        assert exc_info.value.status_code == 401
    finally:
        db.close()


def test_clerk_path_still_reachable(monkeypatch):
    """Clerk tokens still reach decode_clerk_token."""
    seen = {}

    def fake_clerk(token: str):
        seen["token"] = token
        raise HTTPException(status_code=401, detail="Invalid Clerk authentication token")

    monkeypatch.setattr("utils.auth_utils.decode_clerk_token", fake_clerk)
    db = _db()
    try:
        with pytest.raises(HTTPException):
            get_user_from_token("some-clerk-jwt", db)
        assert seen["token"] == "some-clerk-jwt"
    finally:
        db.close()
    assert decode_clerk_token is not None  # import stays wired


# WebSocket token extraction

def _ws(headers=None, cookies=None, query_params=None):
    return SimpleNamespace(
        headers=headers or {},
        cookies=cookies or {},
        query_params=query_params or {},
    )


def test_ws_token_prefers_header_then_subprotocol_then_query():
    assert get_websocket_token(_ws(headers={"authorization": "Bearer h"})) == "h"
    assert (
        get_websocket_token(_ws(headers={"sec-websocket-protocol": "bearer, s"}))
        == "s"
    )
    assert get_websocket_token(_ws(cookies={"access_token": "c"})) == "c"
    assert get_websocket_token(_ws(query_params={"token": "q"})) == "q"
    assert get_websocket_token(_ws()) is None
    assert get_websocket_token(_ws(query_params={"token": "   "})) is None


# WS managers accept Flutter clients

class _StubWebSocket:
    """Minimal stand-in for accept() calls."""

    def __init__(self, offered_subprotocols=""):
        self.headers = {"sec-websocket-protocol": offered_subprotocols}
        self.accepted_with = "NOT_CALLED"
        self.sent = []

    async def accept(self, subprotocol=None):
        # Mirror Starlette: unoffered subprotocol fails
        offered = {
            p.strip().lower()
            for p in self.headers.get("sec-websocket-protocol", "").split(",")
            if p.strip()
        }
        if subprotocol is not None and subprotocol.lower() not in offered:
            raise RuntimeError("unoffered subprotocol")
        self.accepted_with = subprotocol

    async def send_text(self, message: str):
        self.sent.append(message)


def test_notification_manager_accepts_flutter_client_without_subprotocol():
    ws = _StubWebSocket(offered_subprotocols="")
    asyncio.run(notif_manager.connect(ws, user_id=7))
    assert ws.accepted_with is None
    assert 7 in notif_manager.connections_by_user
    notif_manager.disconnect(ws, 7)
    assert 7 not in notif_manager.connections_by_user


def test_notification_manager_still_negotiates_bearer_for_web():
    ws = _StubWebSocket(offered_subprotocols="bearer, some-clerk-jwt")
    asyncio.run(notif_manager.connect(ws, user_id=8, subprotocol="bearer"))
    assert ws.accepted_with == "bearer"
    notif_manager.disconnect(ws, 8)


def test_tracking_manager_accepts_flutter_client_without_subprotocol():
    from routers.tracking import manager as tracking_manager

    ws = _StubWebSocket(offered_subprotocols="")
    asyncio.run(tracking_manager.connect(ws, user_id=9, role="passenger"))
    assert ws.accepted_with is None
    assert any(entry.websocket is ws for entry in tracking_manager.active_connections)
    tracking_manager.disconnect(ws)
    assert all(entry.websocket is not ws for entry in tracking_manager.active_connections)
