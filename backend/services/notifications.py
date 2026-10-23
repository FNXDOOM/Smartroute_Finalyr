from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Iterable, List, Optional

from fastapi import WebSocket
from sqlalchemy.orm import Session

from models.notification import Notification
from services.websocket_hub import accept_connection, fan_out


class NotificationConnectionManager:
    """Per-user WebSocket connections."""

    def __init__(self):
        self.connections_by_user: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int, subprotocol: str | None = None):
        """Register a WebSocket connection."""
        await accept_connection(websocket, subprotocol)
        self.connections_by_user.setdefault(user_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        """Remove a WebSocket connection."""
        connections = self.connections_by_user.get(user_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.connections_by_user.pop(user_id, None)

    async def send_to_user(self, user_id: int, message: str):
        """Send a payload to every connection owned by a user."""
        connections = list(self.connections_by_user.get(user_id) or [])
        if not connections:
            return
        for connection in await fan_out(connections, lambda ws: ws.send_text(message)):
            self.disconnect(connection, user_id)


manager = NotificationConnectionManager()


def serialize_notification(notification: Notification) -> dict:
    """Convert a notification model into WebSocket payload data."""
    return {
        "id": notification.id,
        "user_id": notification.user_id,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "related_entity_type": notification.related_entity_type,
        "related_entity_id": notification.related_entity_id,
        "notification_metadata": notification.notification_metadata,
        "is_read": notification.is_read,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


def create_notification(
    db: Session,
    *,
    user_id: int,
    notification_type: str,
        title: str,
        message: str,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    broadcast: bool = True,
) -> Notification:
    """Create a notification and deliver it to connected clients."""
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        notification_metadata=metadata,
    )
    db.add(notification)
    db.flush()

    if broadcast:
        try:
            asyncio.get_running_loop().create_task(
                manager.send_to_user(
                    user_id,
                    json.dumps(
                        {
                            "type": "notification",
                            "notification": serialize_notification(notification),
                        },
                        default=str,
                    ),
                )
            )
        except RuntimeError:
            pass

    return notification


def create_notifications_for_users(
    db: Session,
    *,
    user_ids: Iterable[int],
    notification_type: str,
    title: str,
    message: str,
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
    broadcast: bool = True,
) -> List[Notification]:
    """Create and deliver the same notification to multiple users."""
    notifications: List[Notification] = []
    for user_id in sorted(set(int(user_id) for user_id in user_ids)):
        notifications.append(
            create_notification(
                db,
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                related_entity_type=related_entity_type,
                related_entity_id=related_entity_id,
                metadata=metadata,
                broadcast=broadcast,
            )
        )
    return notifications
