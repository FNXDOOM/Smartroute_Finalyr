from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func

from backend.database import Base


class JobRun(Base):
    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String, index=True, nullable=False)
    status = Column(String, default="running", nullable=False)
    triggered_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_scheduled = Column(Boolean, default=True, nullable=False)
    summary = Column(JSON, nullable=True)
    error_message = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

