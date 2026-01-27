from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, UniqueConstraint
from datetime import datetime

from .base import Base


class Participant(Base):
    __tablename__ = "participant"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_participant_event_user"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("event.id"), nullable=False)
    user_id = Column(BigInteger, nullable=False)
    full_name = Column(String(256), nullable=False)
    instagram = Column(String(512), default=None)
    telegram = Column(String(512), default=None)
    vk = Column(String(512), default=None)
    created_at = Column(DateTime, default=datetime.utcnow)
