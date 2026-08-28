import asyncio
import json
from dataclasses import dataclass
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models.tracking_event import TrackingEvent
from models.route_plan import RoutePlan
from models.route_waypoint import RouteWaypointRecord
from models.ride_request import RideRequest
from models.virtual_stop import VirtualStop
from models.user import User
from models.vehicle import Vehicle
from schemas.tracking import (
    TrackingEventResponse,
    TrackingFeedResponse,
    VehicleSnapshot,
    VehicleTelemetryUpdate,
)
from services.notifications import create_notification, create_notifications_for_users
from services.stadia_client import extract_route_details, map_match
from utils.auth_utils import get_current_user, get_user_from_token, get_websocket_token
from config import ALLOWED_ORIGINS
from utils.ride_scope import LIVE_MODE

router = APIRouter()


@dataclass
class TrackingConnection:
    websocket: WebSocket
    user_id: int
    role: str


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[TrackingConnection] = []

    async def connect(self, websocket: WebSocket, user_id: int, role: str):
        await websocket.accept(subprotocol="bearer")
        self.active_connections.append(TrackingConnection(websocket, user_id, role))

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [entry for entry in self.active_connections if entry.websocket is not websocket]

    async def broadcast_snapshot(self, db: Session, vehicles: list[Vehicle], events: list[TrackingEvent]):
        dead = []
        for entry in self.active_connections:
            try:
                visible_vehicle_ids, visible_ride_ids = _visible_tracking_ids(db, entry)
                visible_vehicles = vehicles if entry.role == "admin" else [
                    vehicle for vehicle in vehicles if vehicle.id in visible_vehicle_ids
                ]
                visible_events = events if entry.role == "admin" else [
                    event for event in events
                    if event.vehicle_id in visible_vehicle_ids or event.ride_request_id in visible_ride_ids
                ]
                await entry.websocket.send_text(json.dumps({
                    "type": "tracking_snapshot",
                    "vehicles": [_serialize_vehicle(vehicle) for vehicle in visible_vehicles],
                    "events": [_serialize_event(event) for event in visible_events],
                }, default=str))
            except Exception:
                dead.append(entry.websocket)
        for websocket in dead:
            self.disconnect(websocket)

    async def broadcast_vehicle_update(self, vehicle: dict, event: dict):
        db = SessionLocal()
        try:
            dead = []
            for entry in self.active_connections:
                try:
                    visible_vehicle_ids, _ = _visible_tracking_ids(db, entry)
                    if entry.role != "admin" and vehicle["id"] not in visible_vehicle_ids:
                        continue
                    await entry.websocket.send_text(json.dumps({
                        "type": "vehicle_location_update",
                        "vehicle": vehicle,
                        "event": event,
                    }, default=str))
                except Exception:
                    dead.append(entry.websocket)
            for websocket in dead:
                self.disconnect(websocket)
        finally:
            db.close()


def _visible_tracking_ids(db: Session, entry: TrackingConnection) -> tuple[set[int], set[int]]:
    """Return vehicle and ride IDs visible to a tracking connection."""
    if entry.role == "admin":
        return set(), set()

    if entry.role == "driver":
        vehicle_ids = {
            vehicle_id for (vehicle_id,) in db.query(Vehicle.id)
            .filter(Vehicle.mode == LIVE_MODE, Vehicle.driver_user_id == entry.user_id).all()
        }
        return vehicle_ids, set()

    rides = db.query(RideRequest).filter(
        RideRequest.user_id == entry.user_id,
        RideRequest.mode == LIVE_MODE,
        RideRequest.status.in_(["pending", "clustered", "assigned", "arriving", "in_progress"]),
    ).all()
    ride_ids = {ride.id for ride in rides}
    if not ride_ids:
        return set(), set()

    waypoints = db.query(RouteWaypointRecord).filter(RouteWaypointRecord.passenger_ids.isnot(None)).all()
    route_plan_ids = {
        waypoint.route_plan_id
        for waypoint in waypoints
        if ride_ids.intersection(set(waypoint.passenger_ids or []))
    }
    if not route_plan_ids:
        return set(), ride_ids
    vehicle_ids = {
        vehicle_id for (vehicle_id,) in db.query(RoutePlan.vehicle_id)
        .filter(RoutePlan.id.in_(route_plan_ids)).all()
    }
    return vehicle_ids, ride_ids


manager = ConnectionManager()
_simulation_task = None


def _serialize_vehicle(vehicle: Vehicle) -> dict:
    return {
        "id": vehicle.id,
        "license_plate": vehicle.license_plate,
        "status": vehicle.status,
        "lat": vehicle.lat,
        "lng": vehicle.lng,
        "assigned_route_id": vehicle.assigned_route_id,
    }


def _serialize_event(event: TrackingEvent) -> dict:
    return {
        "id": event.id,
        "vehicle_id": event.vehicle_id,
        "ride_request_id": event.ride_request_id,
        "route_plan_id": event.route_plan_id,
        "event_type": event.event_type,
        "status": event.status,
        "lat": event.lat,
        "lng": event.lng,
        "payload": event.payload,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _get_snapshot(db: Session, limit: int = 20) -> tuple[list[VehicleSnapshot], list[TrackingEventResponse]]:
    vehicles = db.query(Vehicle).filter(Vehicle.mode == LIVE_MODE).order_by(Vehicle.id.asc()).all()
    events = db.query(TrackingEvent).order_by(TrackingEvent.created_at.desc()).limit(limit).all()
    vehicle_snapshots = [VehicleSnapshot.model_validate(vehicle) for vehicle in vehicles]
    event_responses = [TrackingEventResponse.model_validate(event) for event in events]
    return vehicle_snapshots, event_responses


async def broadcast_live_feed():
    """Broadcast current vehicle snapshot and recent telemetry events."""
    while True:
        db = SessionLocal()
        try:
            vehicles = db.query(Vehicle).filter(Vehicle.mode == LIVE_MODE).order_by(Vehicle.id.asc()).all()
            events = db.query(TrackingEvent).order_by(TrackingEvent.created_at.desc()).limit(10).all()
            await manager.broadcast_snapshot(db, vehicles, events)
        except Exception:
            pass
        finally:
            db.close()
        await asyncio.sleep(2)


def start_simulation():
    """Launch the background WebSocket broadcast loop."""
    global _simulation_task
    if _simulation_task is None or _simulation_task.done():
        _simulation_task = asyncio.create_task(broadcast_live_feed())


@router.get("/feed", response_model=TrackingFeedResponse)
def get_tracking_feed(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view tracking data",
        )

    if current_user.role == "admin":
        vehicles, events = _get_snapshot(db, limit=limit)
    else:
        vehicles = db.query(Vehicle).filter(Vehicle.mode == LIVE_MODE, Vehicle.driver_user_id == current_user.id).order_by(Vehicle.id.asc()).all()
        vehicle_ids = {vehicle.id for vehicle in vehicles}
        events = db.query(TrackingEvent).filter(TrackingEvent.vehicle_id.in_(vehicle_ids)).order_by(TrackingEvent.created_at.desc()).limit(limit).all() if vehicle_ids else []
    return TrackingFeedResponse(status="ok", vehicles=vehicles, events=events)


@router.get("/events", response_model=List[TrackingEventResponse])
def list_tracking_events(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can view tracking events",
        )

    if current_user.role == "admin":
        events = db.query(TrackingEvent).order_by(TrackingEvent.created_at.desc()).limit(limit).all()
    else:
        vehicle_ids = [vehicle_id for (vehicle_id,) in db.query(Vehicle.id).filter(Vehicle.mode == LIVE_MODE, Vehicle.driver_user_id == current_user.id).all()]
        events = db.query(TrackingEvent).filter(TrackingEvent.vehicle_id.in_(vehicle_ids)).order_by(TrackingEvent.created_at.desc()).limit(limit).all() if vehicle_ids else []
    return [TrackingEventResponse.model_validate(event) for event in events]


@router.post("/vehicles/{vehicle_id}/location", response_model=VehicleSnapshot)
async def update_vehicle_location(
    vehicle_id: int,
    payload: VehicleTelemetryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update vehicle GPS location and broadcast to WebSocket subscribers."""
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can update vehicle telemetry",
        )

    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    if current_user.role == "driver" and vehicle.driver_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Vehicle is not assigned to this driver")

    matched_lat = payload.lat
    matched_lng = payload.lng
    recent_events = (
        db.query(TrackingEvent)
        .filter(
            TrackingEvent.vehicle_id == vehicle.id,
            TrackingEvent.lat.isnot(None),
            TrackingEvent.lng.isnot(None),
        )
        .order_by(TrackingEvent.created_at.desc())
        .limit(4)
        .all()
    )
    trace = [
        {"lat": event.lat, "lon": event.lng}
        for event in reversed(recent_events)
    ] + [{"lat": payload.lat, "lon": payload.lng}]
    map_matched = False
    if len(trace) >= 2:
        try:
            matched = await asyncio.to_thread(map_match, trace)
            matched_geometry = extract_route_details(matched).get("geometry", [])
            if matched_geometry:
                matched_lng, matched_lat = matched_geometry[-1]
                map_matched = True
        except RuntimeError:
            # GPS telemetry must continue even when the optional map-matching
            # request is unavailable or the account has no routing quota.
            pass

    vehicle.lat = matched_lat
    vehicle.lng = matched_lng
    if payload.status is not None:
        vehicle.status = payload.status

    event = TrackingEvent(
        vehicle_id=vehicle.id,
        event_type="vehicle_location_update",
        status=vehicle.status,
        lat=matched_lat,
        lng=matched_lng,
        payload={
            **(payload.payload or {}),
            "raw_lat": payload.lat,
            "raw_lng": payload.lng,
            "map_matched": map_matched,
        },
    )
    db.add(event)

    passenger_user_ids = []
    if vehicle.assigned_route_id:
        route_plan = db.query(RoutePlan).filter(RoutePlan.route_id == vehicle.assigned_route_id).first()
        if route_plan and route_plan.route_metadata and isinstance(route_plan.route_metadata, dict):
            assigned_stop_ids = route_plan.route_metadata.get("assigned_stop_ids", []) or []
            if assigned_stop_ids:
                virtual_stops = db.query(VirtualStop).filter(VirtualStop.id.in_(assigned_stop_ids)).all()
                for virtual_stop in virtual_stops:
                    passenger_user_ids.extend(request.user_id for request in virtual_stop.ride_requests)
        passenger_user_ids = sorted(set(passenger_user_ids))

    if passenger_user_ids:
        create_notifications_for_users(
            db,
            user_ids=passenger_user_ids,
            notification_type="vehicle_tracking_update",
            title="Your vehicle has a new live update",
            message=f"Vehicle {vehicle.license_plate} is now at ({matched_lat:.5f}, {matched_lng:.5f}).",
            related_entity_type="vehicle",
            related_entity_id=vehicle.id,
            metadata={
                "vehicle_id": vehicle.id,
                "route_id": vehicle.assigned_route_id,
                "status": vehicle.status,
            },
        )

    create_notification(
        db,
        user_id=current_user.id,
        notification_type="vehicle_location_logged",
        title="Vehicle telemetry recorded",
        message=f"Vehicle {vehicle.license_plate} location was updated successfully.",
        related_entity_type="vehicle",
        related_entity_id=vehicle.id,
        metadata={
            "lat": matched_lat,
            "lng": matched_lng,
            "status": vehicle.status,
            "map_matched": map_matched,
        },
    )
    db.commit()
    db.refresh(vehicle)
    db.refresh(event)

    # Broadcast through the scoped manager so passengers only receive their
    # assigned vehicle, while admin/driver connections receive fleet updates.
    asyncio.create_task(manager.broadcast_vehicle_update(_serialize_vehicle(vehicle), _serialize_event(event)))

    return VehicleSnapshot.model_validate(vehicle)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for live vehicle tracking.
    Clients must pass a valid JWT as the ``bearer`` WebSocket subprotocol.
    """
    token = get_websocket_token(websocket)
    if not token:
        await websocket.close(code=4401, reason="Missing authentication token")
        return

    origin = websocket.headers.get("origin")
    if origin and origin.rstrip("/") not in ALLOWED_ORIGINS:
        await websocket.close(code=4403, reason="Origin not allowed")
        return

    db = SessionLocal()
    try:
        user = get_user_from_token(token, db)
    except Exception:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return
    finally:
        db.close()

    await manager.connect(websocket, user.id, user.role)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
