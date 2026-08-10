from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    notification_type = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    related_entity_type = Column(String, nullable=True)
    related_entity_id = Column(Integer, nullable=True, index=True)
    notification_metadata = Column("metadata", JSON, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="notifications")
