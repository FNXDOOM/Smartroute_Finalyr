from sqlalchemy import Column, Integer, ForeignKey, DateTime
from geoalchemy2 import Geometry
from sqlalchemy.sql import func
from backend.database import Base


class RideRequest(Base):
    __tablename__ = "ride_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pickup_location = Column(Geometry("POINT", srid=4326))
    destination_location = Column(Geometry("POINT", srid=4326))
    request_time = Column(DateTime(timezone=True), server_default=func.now())
