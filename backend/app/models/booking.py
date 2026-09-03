import uuid
from datetime import datetime

from sqlalchemy import String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Booking(Base):
    """A confirmed flight booking.

    Any user's "list my bookings" would see every other user's bookings too, and
    "cancel my flight" had no way to know whose flight it even was.

    Rows here are always scoped by `user_id`, so lookups/cancellations are
    naturally isolated per user regardless of which conversation they were
    made from.
    """

    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), nullable=True, index=True)

    # Short, human-speakable reference the LLM/user can refer to ("BK0007"),
    # distinct from the internal uuid `id`.
    booking_ref: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)

    flight_id: Mapped[str] = mapped_column(String(16), nullable=False)
    passenger_name: Mapped[str] = mapped_column(String(255), nullable=False)
    origin: Mapped[str] = mapped_column(String(8), nullable=False)
    destination: Mapped[str] = mapped_column(String(8), nullable=False)
    date: Mapped[str] = mapped_column(String(16), nullable=False)
    departure_time: Mapped[str] = mapped_column(String(8), nullable=False)
    arrival_time: Mapped[str] = mapped_column(String(8), nullable=False)
    airline: Mapped[str] = mapped_column(String(64), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)

    # confirmed -> cancelled (soft delete, never hard-deleted, so the LLM
    # can still truthfully say "you cancelled BK0007 on ..." later).
    status: Mapped[str] = mapped_column(String(16), default="confirmed", nullable=False, index=True)

    calendar_link: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
