from sqlalchemy import Column, Integer, BigInteger, Text, DateTime, SmallInteger, ForeignKey
from datetime import datetime

from .base import Base


class Opinion(Base):
    __tablename__ = "opinion"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("event.id"), nullable=False)
    round_number = Column(SmallInteger, nullable=False)
    from_user_id = Column(BigInteger, nullable=False)
    about_user_id = Column(BigInteger, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
