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

# In-memory SQLite for fast offline tests
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


def test_jwt_role_claim_cannot_grant_a_role():
    """Clerk's public_metadata is writable by the signed-in user, so honouring a role claim is a self-service admin grant."""
    db = TestingSessionLocal()
    try:
        payload = {
            "sub": "test_clerk_claimer_888",
            "email": "claimer888@example.com",
            "name": "Claim Runner",
            "metadata": {"role": "admin", "driver_status": "active"},
            "public_metadata": {"role": "admin", "driver_status": "active"},
        }
        user = get_or_create_user_from_payload(payload, db)
        assert user.role == "passenger"
    finally:
        db.close()


def test_jwt_role_claim_cannot_escalate_an_existing_user():
    db = TestingSessionLocal()
    try:
        base = {
            "sub": "test_clerk_escalator_777",
            "email": "escalator777@example.com",
            "name": "Escalator",
        }
        user = get_or_create_user_from_payload(base, db)
        assert user.role == "passenger"

        escalated = dict(base, public_metadata={"role": "admin", "driver_status": "active"})
        again = get_or_create_user_from_payload(escalated, db)
        assert again.id == user.id
        assert again.role == "passenger"
        assert again.driver_status == "active"
    finally:
        db.close()


def test_rejected_driver_application_is_not_granted_the_role():
    from routers.auth import verify_driver
    from schemas.user import DriverVerifyRequest

    db = TestingSessionLocal()
    try:
        admin = User(
            id=900,
            name="Admin",
            email="admin900@example.com",
            password_hash="test_hash",
            role="admin",
            driver_status="active",
        )
        applicant = User(
            id=901,
            name="Applicant",
            email="applicant901@example.com",
            password_hash="test_hash",
            role="passenger",
            driver_status="pending_verification",
        )
        db.add_all([admin, applicant])
        db.commit()

        verify_driver(
            user_id=applicant.id,
            verify_in=DriverVerifyRequest(status="rejected"),
            db=db,
            current_user=admin,
        )
        db.refresh(applicant)
        assert applicant.driver_status == "rejected"
        assert applicant.role == "passenger"

        verify_driver(
            user_id=applicant.id,
            verify_in=DriverVerifyRequest(status="active"),
            db=db,
            current_user=admin,
        )
        db.refresh(applicant)
        assert applicant.role == "driver"
    finally:
        db.close()


def test_suspended_driver_is_blocked_even_on_a_mixed_allowlist():
    """require_roles used to skip the status check whenever passengers were also allowed, so a suspended driver kept operating."""
    mixed_guard = require_roles(["driver", "passenger"])
    suspended = User(
        id=104,
        name="Suspended Sam",
        email="sam@example.com",
        role="driver",
        driver_status="suspended",
    )
    with pytest.raises(HTTPException) as exc_info:
        mixed_guard(suspended)
    assert exc_info.value.status_code == 403
    assert "pending verification" in exc_info.value.detail

    active = User(id=105, name="Active Amy", email="amy@example.com", role="driver", driver_status="active")
    assert mixed_guard(active) == active

    # Admins act in their own capacity and are not gated on driver status.
    admin_guard = require_roles(["driver", "admin"])
    admin = User(id=106, name="Admin", email="admin106@example.com", role="admin", driver_status=None)
    assert admin_guard(admin) == admin


def _get_as(user, path):
    """Issue one ASGI request with `user` substituted for the auth dependency."""
    import asyncio

    import httpx

    from main import app
    from utils.auth_utils import get_current_user

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        return asyncio.run(run())
    finally:
        # A leaked override would silently disable auth for every later test.
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous


def test_suspended_driver_is_refused_by_the_converted_endpoints():
    """These routers re-checked `role` by hand and ignored driver_status, so this walks the dependency graph rather than the helper."""
    suspended = User(
        id=801,
        name="Suspended Sam",
        email="suspended801@example.com",
        password_hash="test_hash",
        role="driver",
        driver_status="suspended",
    )
    active = User(
        id=802,
        name="Active Amy",
        email="active802@example.com",
        password_hash="test_hash",
        role="driver",
        driver_status="active",
    )

    for path in ("/cluster/history", "/vehicle/", "/tracking/feed"):
        response = _get_as(suspended, path)
        assert response.status_code == 403, "%s admitted a suspended driver (%s)" % (path, response.status_code)
        assert "pending verification" in response.json()["detail"]

    assert _get_as(active, "/cluster/history").status_code == 200, "an active driver must still be served"


def test_require_roles_dependency_guard():
    driver_only_guard = require_roles(["driver"])

    passenger_user = User(
        id=101,
        name="Passenger Joe",
        email="joe@example.com",
        role="passenger",
        driver_status="active",
    )

    # Passenger blocked from driver routes
    with pytest.raises(HTTPException) as exc_info:
        driver_only_guard(passenger_user)
    assert exc_info.value.status_code == 403
    assert "Access denied" in exc_info.value.detail

    # Pending driver blocked from active ops
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
