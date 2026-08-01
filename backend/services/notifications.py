from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

from fastapi import WebSocket
from sqlalchemy.orm import Session

from backend.models.notification import Notification


class NotificationConnectionManager:
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


manager = NotificationConnectionManager()


def serialize_notification(notification: Notification) -> dict:
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
                manager.broadcast(
                    json.dumps(
                        {
                            "type": "notification",
                            "notification": serialize_notification(notification),
                        },
                        default=str,
                    )
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
