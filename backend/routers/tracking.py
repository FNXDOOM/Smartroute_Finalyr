import asyncio
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from backend.database import SessionLocal, get_db
from backend.models.tracking_event import TrackingEvent
from backend.models.route_plan import RoutePlan
from backend.models.virtual_stop import VirtualStop
from backend.models.user import User
from backend.models.vehicle import Vehicle
from backend.schemas.tracking import (
    TrackingEventResponse,
    TrackingFeedResponse,
    VehicleSnapshot,
    VehicleTelemetryUpdate,
)
from backend.services.notifications import create_notification, create_notifications_for_users
from backend.utils.auth_utils import get_current_user

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)


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
    vehicles = db.query(Vehicle).order_by(Vehicle.id.asc()).all()
    events = db.query(TrackingEvent).order_by(TrackingEvent.created_at.desc()).limit(limit).all()
    vehicle_snapshots = [VehicleSnapshot.model_validate(vehicle) for vehicle in vehicles]
    event_responses = [TrackingEventResponse.model_validate(event) for event in events]
    return vehicle_snapshots, event_responses


async def broadcast_live_feed():
    """Broadcast current vehicle snapshot and recent telemetry events."""
    while True:
        db = SessionLocal()
        try:
            vehicles = db.query(Vehicle).order_by(Vehicle.id.asc()).all()
            events = db.query(TrackingEvent).order_by(TrackingEvent.created_at.desc()).limit(10).all()
            payload = json.dumps(
                {
                    "type": "tracking_snapshot",
                    "vehicles": [_serialize_vehicle(vehicle) for vehicle in vehicles],
                    "events": [_serialize_event(event) for event in events],
                },
                default=str,
            )
            await manager.broadcast(payload)
        except Exception:
            # Keep the live feed resilient even if a telemetry query fails.
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

    vehicles, events = _get_snapshot(db, limit=limit)
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

    events = db.query(TrackingEvent).order_by(TrackingEvent.created_at.desc()).limit(limit).all()
    return [TrackingEventResponse.model_validate(event) for event in events]


@router.post("/vehicles/{vehicle_id}/location", response_model=VehicleSnapshot)
def update_vehicle_location(
    vehicle_id: int,
    payload: VehicleTelemetryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "driver"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or driver users can update vehicle telemetry",
        )

    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    vehicle.lat = payload.lat
    vehicle.lng = payload.lng
    if payload.status is not None:
        vehicle.status = payload.status

    event = TrackingEvent(
        vehicle_id=vehicle.id,
        event_type="vehicle_location_update",
        status=vehicle.status,
        lat=payload.lat,
        lng=payload.lng,
        payload=payload.payload,
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
            message=f"Vehicle {vehicle.license_plate} is now at ({payload.lat:.5f}, {payload.lng:.5f}).",
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
            "lat": payload.lat,
            "lng": payload.lng,
            "status": vehicle.status,
        },
    )
    db.commit()
    db.refresh(vehicle)
    db.refresh(event)

    asyncio.create_task(
        manager.broadcast(
            json.dumps(
                {
                    "type": "vehicle_location_update",
                    "vehicle": _serialize_vehicle(vehicle),
                    "event": _serialize_event(event),
                },
                default=str,
            )
        )
    )

    return VehicleSnapshot.model_validate(vehicle)


@router.websocket("/ws/tracking")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
