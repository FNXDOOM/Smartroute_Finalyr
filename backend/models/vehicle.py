from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from database import Base, PortableGeometry


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    license_plate = Column(String, unique=True, index=True, nullable=False)
    capacity = Column(Integer, nullable=False)
    status = Column(String, default="idle", nullable=False)  # idle | active | en_route | offline
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    assigned_route_id = Column(String, nullable=True)
    current_location = Column(PortableGeometry, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


