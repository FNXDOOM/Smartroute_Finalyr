from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    notification_type: str
    title: str
    message: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    notification_metadata: Optional[dict] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    status: str
    unread_count: int
    notifications: list[NotificationResponse]


class NotificationReadResponse(BaseModel):
    status: str
    notification: NotificationResponse


class NotificationActionResponse(BaseModel):
    status: str
    updated_count: int = Field(default=0)
