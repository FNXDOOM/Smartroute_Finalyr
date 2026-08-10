from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.notification import Notification
from backend.models.user import User
from backend.schemas.notification import (
    NotificationActionResponse,
    NotificationListResponse,
    NotificationReadResponse,
    NotificationResponse,
)
from backend.services.notifications import manager
from backend.utils.auth_utils import get_current_user, decode_access_token

router = APIRouter()


def _get_notification_for_user(db: Session, notification_id: int, user_id: int) -> Notification:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@router.get("/", response_model=NotificationListResponse)
def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))

    notifications = query.order_by(Notification.created_at.desc()).limit(limit).all()
    unread_count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .count()
    )
    return NotificationListResponse(
        status="ok",
        unread_count=unread_count,
        notifications=[NotificationResponse.model_validate(notification) for notification in notifications],
    )


@router.get("/unread-count", response_model=NotificationActionResponse)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .count()
    )
    return NotificationActionResponse(status="ok", updated_count=count)


@router.patch("/{notification_id}/read", response_model=NotificationReadResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = _get_notification_for_user(db, notification_id, current_user.id)
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)
    return NotificationReadResponse(status="ok", notification=NotificationResponse.model_validate(notification))


@router.patch("/read-all", response_model=NotificationActionResponse)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .all()
    )
    count = 0
    for notification in notifications:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        count += 1
    db.commit()
    return NotificationActionResponse(status="ok", updated_count=count)


@router.websocket("/ws")
async def websocket_notifications(websocket: WebSocket):
    """
    WebSocket endpoint for real-time notifications.
    Clients must pass a valid JWT as a query parameter: /ws/notifications?token=<jwt>
    Notifications are scoped to the authenticated user — the connection is
    registered under their user_id so broadcasts never cross between users.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing authentication token")
        return

    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception:
        manager.disconnect(websocket, user_id)

