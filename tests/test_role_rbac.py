import sys
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import Base
from models.user import User
from utils.auth_utils import get_or_create_user_from_payload, require_roles

# Use in-memory SQLite for deterministic, fast, offline testing
test_engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
User.__table__.create(bind=test_engine)


def test_default_user_provisions_as_passenger():
    db = TestingSessionLocal()
    try:
        payload = {
            "sub": "test_clerk_passenger_999",
            "email": "passenger999@example.com",
            "name": "Test Passenger",
        }
        user = get_or_create_user_from_payload(payload, db)
        assert user.role == "passenger"
        assert user.driver_status == "active"
    finally:
        db.close()


def test_custom_jwt_role_claim_honored():
    db = TestingSessionLocal()
    try:
        payload = {
            "sub": "test_clerk_driver_888",
            "email": "driver888@example.com",
            "name": "Test Driver",
            "metadata": {
                "role": "driver",
                "driver_status": "pending_verification",
            },
        }
        user = get_or_create_user_from_payload(payload, db)
        assert user.role == "driver"
        assert user.driver_status == "pending_verification"
    finally:
        db.close()


def test_require_roles_dependency_guard():
    driver_only_guard = require_roles(["driver"])

    passenger_user = User(
        id=101,
        name="Passenger Joe",
        email="joe@example.com",
        role="passenger",
        driver_status="active",
    )

    # Passenger blocked from driver-only endpoints
    with pytest.raises(HTTPException) as exc_info:
        driver_only_guard(passenger_user)
    assert exc_info.value.status_code == 403
    assert "Access denied" in exc_info.value.detail

    # Pending driver blocked from active driver operations
    pending_driver = User(
        id=102,
        name="Driver Bob",
        email="bob@example.com",
        role="driver",
        driver_status="pending_verification",
    )
    with pytest.raises(HTTPException) as exc_info:
        driver_only_guard(pending_driver)
    assert exc_info.value.status_code == 403
    assert "pending verification" in exc_info.value.detail

    # Active driver allowed
    active_driver = User(
        id=103,
        name="Driver Alice",
        email="alice@example.com",
        role="driver",
        driver_status="active",
    )
    assert driver_only_guard(active_driver) == active_driver
