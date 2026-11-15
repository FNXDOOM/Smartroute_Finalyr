"""The coarse ride ladder only advances: terminal rides are never rewritten and no move goes backwards.
utils/ride_states.py documents the invariant; the PATCH endpoint used to accept any vocabulary value
from any state. Routers are called directly with a real session, per repo convention."""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from models.ride_request import RideRequest
from models.user import User
from routers.rides import update_ride_request_status
from schemas.ride_request import RideRequestStatusUpdate
from utils.ride_states import (
    RIDE_ASSIGNED,
    RIDE_CANCELLED,
    RIDE_COMPLETED,
    RIDE_IN_PROGRESS,
    RIDE_PENDING,
)

ADMIN_EMAIL = "status_guard_admin@example.com"
DRIVER_EMAIL = "status_guard_driver@example.com"
RIDER_EMAIL = "status_guard_rider@example.com"


def _user(db, email, role="passenger"):
    user = db.query(User).filter(User.email == email).first()
    if user:
        if role == "driver":
            user.driver_status = "active"
            db.commit()
        return user
    user = User(
        clerk_user_id=f"status_guard_{email}",
        email=email,
        name="Status Guard Tester",
        password_hash="test_hash",
        role=role,
        driver_status="active" if role == "driver" else "pending",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _ride(db, user, status):
    ride = RideRequest(
        user_id=user.id,
        pickup_lat=12.9716,
        pickup_lng=77.5946,
        dest_lat=12.9352,
        dest_lng=77.6245,
        status=status,
        is_shared=False,
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return ride


def _patch(db, ride, user, status):
    return update_ride_request_status(
        ride_id=ride.id,
        status_update=RideRequestStatusUpdate(status=status),
        db=db,
        current_user=user,
    )


def _cleanup(db, user_ids):
    db.query(RideRequest).filter(RideRequest.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()


@pytest.mark.parametrize("terminal", [RIDE_COMPLETED, RIDE_CANCELLED])
def test_a_terminal_ride_is_never_rewritten(terminal):
    db = SessionLocal()
    admin = _user(db, ADMIN_EMAIL, role="admin")
    try:
        ride = _ride(db, admin, terminal)
        with pytest.raises(HTTPException) as refused:
            _patch(db, ride, admin, RIDE_PENDING)
        assert refused.value.status_code == 409
        db.refresh(ride)
        assert ride.status == terminal
    finally:
        _cleanup(db, [admin.id])
        db.close()


def test_a_status_move_never_goes_backwards():
    db = SessionLocal()
    admin = _user(db, ADMIN_EMAIL, role="admin")
    try:
        ride = _ride(db, admin, RIDE_IN_PROGRESS)
        with pytest.raises(HTTPException) as refused:
            _patch(db, ride, admin, RIDE_ASSIGNED)
        assert refused.value.status_code == 409
        db.refresh(ride)
        assert ride.status == RIDE_IN_PROGRESS
    finally:
        _cleanup(db, [admin.id])
        db.close()


def test_forward_moves_and_manual_dispatch_still_work():
    db = SessionLocal()
    admin = _user(db, ADMIN_EMAIL, role="admin")
    driver = _user(db, DRIVER_EMAIL, role="driver")
    try:
        ride = _ride(db, admin, RIDE_PENDING)
        _patch(db, ride, admin, RIDE_ASSIGNED)
        db.refresh(ride)
        assert ride.status == RIDE_ASSIGNED

        # An unrouted private ride has no serving driver to compare against, so
        # manual dispatch stays editable by any active driver.
        private = _ride(db, admin, RIDE_PENDING)
        _patch(db, private, driver, RIDE_COMPLETED)
        db.refresh(private)
        assert private.status == RIDE_COMPLETED
    finally:
        _cleanup(db, [admin.id])
        db.close()


def test_the_owner_can_still_cancel_and_replays_are_no_ops():
    db = SessionLocal()
    rider = _user(db, RIDER_EMAIL)
    admin = _user(db, ADMIN_EMAIL, role="admin")
    try:
        ride = _ride(db, rider, RIDE_PENDING)
        _patch(db, ride, rider, RIDE_CANCELLED)
        db.refresh(ride)
        assert ride.status == RIDE_CANCELLED

        finished = _ride(db, admin, RIDE_COMPLETED)
        _patch(db, finished, admin, RIDE_COMPLETED)
        db.refresh(finished)
        assert finished.status == RIDE_COMPLETED
    finally:
        _cleanup(db, [rider.id, admin.id])
        db.close()


def test_passengers_still_cannot_set_a_non_cancel_status():
    db = SessionLocal()
    rider = _user(db, RIDER_EMAIL)
    try:
        ride = _ride(db, rider, RIDE_PENDING)
        with pytest.raises(HTTPException) as refused:
            _patch(db, ride, rider, RIDE_ASSIGNED)
        assert refused.value.status_code == 403
    finally:
        _cleanup(db, [rider.id])
        db.close()