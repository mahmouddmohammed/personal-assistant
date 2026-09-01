import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SessionLog(Base):
    """One row per LangGraph node execution for a given user turn.

    This is what powers the admin 'which node fired' trace view — it
    mirrors the `graph.stream(..., stream_mode='updates')` trace the
    original notebook printed to stdout, but persisted per request.
    """

    __tablename__ = "session_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    turn_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # groups nodes fired for one prompt
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False)
    node_output: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="session_logs")
