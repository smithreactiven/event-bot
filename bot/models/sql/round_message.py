from sqlalchemy import Column, Integer, BigInteger, SmallInteger, ForeignKey, UniqueConstraint

from .base import Base


class RoundMessage(Base):
    __tablename__ = "round_message"
    __table_args__ = (UniqueConstraint("event_id", "round_number", "user_id", name="uq_round_message"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("event.id"), nullable=False)
    round_number = Column(SmallInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    message_id = Column(Integer, nullable=False)
