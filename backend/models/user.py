from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, default="")
    password_hash = Column(String, nullable=False)
    clerk_user_id = Column(String, unique=True, index=True, nullable=True)
    role = Column(String, default="passenger", nullable=False)  # passenger | driver | admin
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ride_requests = relationship("RideRequest", back_populates="user")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
