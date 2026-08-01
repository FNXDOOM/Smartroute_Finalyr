from sqlalchemy import Column, Integer, Float, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.database import Base, PortableGeometry


class VirtualStop(Base):
    __tablename__ = "virtual_stops"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, nullable=False)
    h3_index = Column(String, index=True, nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    snapped_node_id = Column(String, nullable=True)
    passenger_count = Column(Integer, default=0)
    coordinates = Column(PortableGeometry, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ride_requests = relationship("RideRequest", back_populates="virtual_stop")


