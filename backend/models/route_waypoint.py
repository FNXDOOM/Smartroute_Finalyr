from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class RouteWaypointRecord(Base):
    __tablename__ = "route_waypoints"

    id = Column(Integer, primary_key=True, index=True)
    route_plan_id = Column(Integer, ForeignKey("route_plans.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    stop_id = Column(Integer, nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    waypoint_type = Column(String, nullable=False)
    passenger_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    route_plan = relationship("RoutePlan", back_populates="waypoints")

