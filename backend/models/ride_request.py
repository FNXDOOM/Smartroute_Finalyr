from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base, PortableGeometry


class RideRequest(Base):
    __tablename__ = "ride_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pickup_lat = Column(Float, nullable=False)
    pickup_lng = Column(Float, nullable=False)
    dest_lat = Column(Float, nullable=False)
    dest_lng = Column(Float, nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending | clustered | assigned | in_progress | completed | cancelled
    mode = Column("ride_mode", String, default="live", nullable=False, index=True)  # live | presentation_demo
    demo_run_id = Column(String, nullable=True, index=True)
    h3_index = Column(String, index=True, nullable=True)
    cluster_id = Column(Integer, nullable=True)
    virtual_stop_id = Column(Integer, ForeignKey("virtual_stops.id"), nullable=True)
    pickup_location = Column(PortableGeometry, nullable=True)
    destination_location = Column(PortableGeometry, nullable=True)
    # Python-side default: per-row timestamps.
    request_time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    # Labels from mobile client
    pickup_label = Column(String, nullable=True)
    destination_label = Column(String, nullable=True)
    # Ride-option display metadata
    ride_option_id = Column(String, nullable=True)
    ride_option_name = Column(String, nullable=True)
    ride_option_price = Column(String, nullable=True)

    user = relationship("User", back_populates="ride_requests")
    virtual_stop = relationship("VirtualStop", back_populates="ride_requests")
