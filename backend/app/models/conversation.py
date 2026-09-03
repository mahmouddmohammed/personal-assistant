import uuid
from datetime import datetime

from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    """A chat thread. Its `id` doubles as the LangGraph `thread_id`
    used by the checkpointer, so resuming an interrupted graph and
    loading chat history always refer to the same identifier."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Running summary of everything OLDER than the raw recent-history window
    # (see app/agent/context.py MAX_HISTORY_TURNS). Persisted per-conversation
    # (unlike the old approach, which just silently truncated anything past
    # the last few messages with no summarization at all).
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    # How many of this conversation's messages (in created_at order) are
    # already folded into `summary`, so `_maybe_update_summary` only
    # summarizes the slice that has aged out of the window since last time.
    summary_through: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan",
                             order_by="Message.created_at")
    session_logs = relationship("SessionLog", back_populates="conversation", cascade="all, delete-orphan")
