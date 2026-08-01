from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class RoutePlan(Base):
    __tablename__ = "route_plans"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(String, unique=True, index=True, nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    source_cluster_run_id = Column(Integer, ForeignKey("cluster_runs.id"), nullable=True)
    status = Column(String, default="solved", nullable=False)
    depot_lat = Column(Float, nullable=False)
    depot_lng = Column(Float, nullable=False)
    total_distance_meters = Column(Float, default=0.0, nullable=False)
    estimated_duration_seconds = Column(Float, default=0.0, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    route_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vehicle = relationship("Vehicle")
    source_cluster_run = relationship("ClusterRun")
    created_by = relationship("User")
    waypoints = relationship(
        "RouteWaypointRecord",
        back_populates="route_plan",
        cascade="all, delete-orphan",
        order_by="RouteWaypointRecord.sequence",
    )

