from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func

from backend.database import Base


class DemandSnapshot(Base):
    __tablename__ = "demand_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    job_run_id = Column(Integer, ForeignKey("job_runs.id"), nullable=False, index=True)
    h3_index = Column(String, index=True, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    lookback_days = Column(Integer, default=30, nullable=False)
    historical_request_count = Column(Integer, default=0, nullable=False)
    predicted_demand = Column(Float, default=0.0, nullable=False)
    model_name = Column(String, nullable=True)
    method = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

