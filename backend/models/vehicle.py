from sqlalchemy import Column, Integer, String
from geoalchemy2 import Geometry
from backend.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    current_location = Column(Geometry("POINT", srid=4326))
    capacity = Column(Integer, nullable=False)
    status = Column(String, default="idle")  # idle | active
