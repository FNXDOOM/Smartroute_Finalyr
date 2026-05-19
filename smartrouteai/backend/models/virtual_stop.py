from sqlalchemy import Column, Integer
from geoalchemy2 import Geometry
from backend.database import Base


class VirtualStop(Base):
    __tablename__ = "virtual_stops"

    id = Column(Integer, primary_key=True, index=True)
    coordinates = Column(Geometry("POINT", srid=4326))
    cluster_id = Column(Integer, nullable=False)
