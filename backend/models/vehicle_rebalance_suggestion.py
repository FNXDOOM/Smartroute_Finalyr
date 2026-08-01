from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func

from backend.database import Base


class VehicleRebalanceSuggestion(Base):
    __tablename__ = "vehicle_rebalance_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    job_run_id = Column(Integer, ForeignKey("job_runs.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    target_h3_index = Column(String, index=True, nullable=False)
    target_lat = Column(Float, nullable=False)
    target_lng = Column(Float, nullable=False)
    score = Column(Float, default=0.0, nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

