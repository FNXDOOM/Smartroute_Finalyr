from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.sql import func

from database import Base


class DemandSnapshot(Base):
    __tablename__ = "demand_snapshots"
    __table_args__ = (
        # Latest-snapshot and per-cell history reads.
        Index("ix_demand_snapshots_created_at", "created_at"),
        Index("ix_demand_snapshots_h3_index_created_at", "h3_index", "created_at"),
    )

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

