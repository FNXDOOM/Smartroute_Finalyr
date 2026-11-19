"""Tracking broadcast: no idle DB work, change-only snapshots, initial snapshot, scoping."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from models.tracking_event import TrackingEvent
from models.user import User
from models.vehicle import Vehicle
from routers import tracking

PLATE = "TEST-TRACK-001"


class StubWebSocket:
    def __init__(self, offered="bearer, token"):
        self.headers = {"sec-websocket-protocol": offered}
        self.accepted_with = "NOT_CALLED"
        self.sent = []

    async def accept(self, subprotocol=None):
        self.accepted_with = subprotocol

    async def send_text(self, message):
        import json
        self.sent.append(json.loads(message))


def _cleanup(db, vehicle_ids=(), user_ids=()):
    if vehicle_ids:
        db.query(TrackingEvent).filter(TrackingEvent.vehicle_id.in_(vehicle_ids)).delete(
            synchronize_session=False
        )
        db.query(Vehicle).filter(Vehicle.id.in_(vehicle_ids)).delete(synchronize_session=False)
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()


def test_no_connections_skips_database(monkeypatch):
    monkeypatch.setattr(tracking, "manager", tracking.ConnectionManager())
    monkeypatch.setattr(
        tracking, "SessionLocal", lambda: (_ for _ in ()).throw(AssertionError("DB touched"))
    )
    assert asyncio.run(tracking.broadcast_once()) is False


def test_initial_snapshot_and_change_only_broadcast():
    db = SessionLocal()
    vehicle = Vehicle(license_plate=PLATE, capacity=4, mode="live", status="idle",
                      lat=12.9716, lng=77.5946)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    vehicle_id = vehicle.id
    manager = tracking.ConnectionManager()
    previous = tracking.manager
    tracking.manager = manager
    try:
        async def scenario():
            ws = StubWebSocket()
            entry = await manager.connect(ws, user_id=1, role="admin")
            await manager.send_initial_snapshot(entry)
            assert ws.sent and ws.sent[-1]["type"] == "tracking_snapshot"
            assert any(v["id"] == vehicle_id for v in ws.sent[-1]["vehicles"])

            assert await tracking.broadcast_once() is True   # first state
            sent_after_first = len(ws.sent)
            assert await tracking.broadcast_once() is False  # unchanged, no events
            assert len(ws.sent) == sent_after_first

            vehicle.lat = 12.9720
            db.commit()
            assert await tracking.broadcast_once() is True
            assert len(ws.sent) > sent_after_first

        asyncio.run(scenario())
    finally:
        tracking.manager = previous
        _cleanup(db, vehicle_ids=[vehicle_id])
        db.close()


def test_push_on_update_marks_event_cursor():
    db = SessionLocal()
    vehicle = Vehicle(license_plate="TEST-TRACK-EVT", capacity=4, mode="live", status="idle",
                      lat=12.90, lng=77.60)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    event = TrackingEvent(vehicle_id=vehicle.id, event_type="vehicle_location_update",
                          status="idle", lat=12.90, lng=77.60)
    db.add(event)
    db.commit()
    db.refresh(event)
    manager = tracking.ConnectionManager()
    previous = tracking.manager
    tracking.manager = manager
    try:
        manager.mark_vehicle_sent(vehicle, event)
        assert manager.last_event_cursor == event.created_at
        # With this vehicle/event marked sent, the periodic loop must not resend them.
        manager.last_vehicle_state = tracking._vehicle_state(tracking._vehicle_rows(db))
        assert asyncio.run(tracking.broadcast_once()) is False
    finally:
        tracking.manager = previous
        _cleanup(db, vehicle_ids=[vehicle.id])
        db.close()


def test_driver_snapshot_is_scoped_to_own_vehicle():
    db = SessionLocal()
    driver = User(name="Track Driver", email="track.driver@example.com",
                  password_hash="x", role="driver", driver_status="active")
    db.add(driver)
    db.commit()
    db.refresh(driver)
    own = Vehicle(license_plate="TEST-TRACK-DRV", capacity=4, mode="live",
                  status="idle", driver_user_id=driver.id, lat=12.90, lng=77.60)
    other = Vehicle(license_plate="TEST-TRACK-OTH", capacity=4, mode="live",
                    status="idle", lat=12.91, lng=77.61)
    db.add_all([own, other])
    db.commit()
    own_id, other_id = own.id, other.id
    manager = tracking.ConnectionManager()
    previous = tracking.manager
    tracking.manager = manager
    try:
        async def scenario():
            ws = StubWebSocket()
            entry = await manager.connect(ws, user_id=driver.id, role="driver")
            await manager.send_initial_snapshot(entry)
            ids = {v["id"] for v in ws.sent[-1]["vehicles"]}
            assert own_id in ids
            assert other_id not in ids

        asyncio.run(scenario())
    finally:
        tracking.manager = previous
        _cleanup(db, vehicle_ids=[own_id, other_id], user_ids=[driver.id])
        db.close()
