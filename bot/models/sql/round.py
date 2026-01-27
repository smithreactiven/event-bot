from sqlalchemy import Column, Integer, String, DateTime, SmallInteger, ForeignKey
from datetime import datetime

from .base import Base


class Round(Base):
    __tablename__ = "round"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("event.id"), nullable=False)
    number = Column(SmallInteger, nullable=False)
    name = Column(String(256), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    list_shown_at = Column(DateTime, default=None)
    ended_at = Column(DateTime, default=None)
