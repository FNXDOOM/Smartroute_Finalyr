from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class ClusterRun(Base):
    __tablename__ = "cluster_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_uuid = Column(String, unique=True, index=True, nullable=False)
    resolution = Column(Integer, nullable=False)
    min_cluster_size = Column(Integer, nullable=False)
    status = Column(String, default="clustered", nullable=False)
    total_processed_requests = Column(Integer, default=0, nullable=False)
    clusters_formed = Column(Integer, default=0, nullable=False)
    noise_requests_count = Column(Integer, default=0, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cluster_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_by = relationship("User")

