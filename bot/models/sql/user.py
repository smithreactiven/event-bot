from sqlalchemy import Column, Integer, String, DateTime, BigInteger
from datetime import datetime

from .base import Base


class User(Base):
    __tablename__ = "user"

    index = Column(Integer, primary_key=True)
    id = Column(BigInteger)
    username = Column(String, default=None)
    first_name = Column(String)
    last_name = Column(String)

