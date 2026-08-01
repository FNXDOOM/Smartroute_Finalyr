from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func

from backend.database import Base


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    ride_request_id = Column(Integer, ForeignKey("ride_requests.id"), nullable=True, index=True)
    route_plan_id = Column(Integer, ForeignKey("route_plans.id"), nullable=True, index=True)
    event_type = Column(String, nullable=False)
    status = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

