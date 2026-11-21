import pytest
from fastapi import HTTPException

from database import SessionLocal
from models.user import User
from models.vehicle import Vehicle
from routers import auth
from routers.auth import update_driver_presence
from schemas.user import DriverApplyRequest


def test_presence_activates_only_unassigned_live_vehicle():
    with SessionLocal() as db:
        driver = User(name="Presence test", email="presence-test@example.test",
                      password_hash="test", role="driver", driver_status="active")
        db.add(driver)
        db.flush()
        vehicles = [
            Vehicle(license_plate="PRESENCE-LIVE", driver_user_id=driver.id,
                    status="offline", mode="live", capacity=4),
            Vehicle(license_plate="PRESENCE-DEMO", driver_user_id=driver.id,
                    status="offline", mode="presentation_demo", capacity=4),
            Vehicle(license_plate="PRESENCE-ACTIVE", driver_user_id=driver.id,
                    status="active", mode="live", capacity=4),
        ]
        db.add_all(vehicles)
        db.flush()
        try:
            update_driver_presence(db=db, current_user=driver)
            for vehicle in vehicles:
                db.refresh(vehicle)
            assert [v.status for v in vehicles] == ["idle", "offline", "active"]
            assert driver.driver_last_seen_at is not None
        finally:
            for vehicle in vehicles:
                db.delete(vehicle)
            db.delete(driver)
            db.commit()


def test_unapproved_driver_cannot_go_online():
    with SessionLocal() as db:
        driver = User(role="driver", driver_status="pending_verification")
        with pytest.raises(HTTPException) as exc:
            update_driver_presence(db=db, current_user=driver)
        assert exc.value.status_code == 403


@pytest.mark.parametrize("review_status", ["active", "suspended"])
def test_reapplication_preserves_review_state_in_db_and_identity_metadata(monkeypatch, review_status):
    synced = []
    monkeypatch.setattr(auth, "sync_clerk_user_metadata", lambda _, metadata: synced.append(metadata))
    with SessionLocal() as db:
        driver = User(name="Review test", email="review-test@example.test", password_hash="test",
                      clerk_user_id="review-test", role="driver", driver_status=review_status)
        db.add(driver)
        db.flush()
        try:
            auth.apply_for_driver(DriverApplyRequest(license_plate="REVIEW-TEST"), db=db, current_user=driver)
            assert driver.driver_status == review_status
            assert synced[-1]["role"] == "driver"
            assert synced[-1]["driver_status"] == review_status
        finally:
            db.query(Vehicle).filter(Vehicle.driver_user_id == driver.id).delete()
            db.delete(driver)
            db.commit()
