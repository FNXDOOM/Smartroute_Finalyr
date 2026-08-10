from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from fastapi import WebSocket
from sqlalchemy.orm import Session

from backend.models.notification import Notification


class NotificationConnectionManager:
    """
    Tracks WebSocket connections per user_id so notifications only reach the
    user they belong to. Previously kept a single flat list and broadcast
    every notification to every connected client regardless of owner — a
    real cross-user data leak (User A would see User B's ride/notification
    events). Fixed by keying connections on user_id.
    """

    def __init__(self):
        self.connections_by_user: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.connections_by_user.setdefault(user_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        connections = self.connections_by_user.get(user_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.connections_by_user.pop(user_id, None)

    async def send_to_user(self, user_id: int, message: str):
        connections = self.connections_by_user.get(user_id)
        if not connections:
            return
        dead = []
        for connection in connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection, user_id)


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
