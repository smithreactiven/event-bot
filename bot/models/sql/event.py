from sqlalchemy import Column, Integer, Boolean, DateTime, SmallInteger
from datetime import datetime

from .base import Base


class Event(Base):
    __tablename__ = "event"

    id = Column(Integer, primary_key=True, autoincrement=True)
    is_started = Column(Boolean, default=False)
    is_ended = Column(Boolean, default=False)
    total_rounds = Column(SmallInteger, default=0)
    current_round = Column(SmallInteger, default=0)
    round_started_at = Column(DateTime, default=None)
    created_at = Column(DateTime, default=datetime.utcnow)
