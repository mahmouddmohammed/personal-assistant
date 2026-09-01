from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None  # None -> a new conversation is created


class InterruptAction(BaseModel):
    """One button the frontend should render for a paused (human-in-the-loop) turn."""
    action: str          # e.g. "approve" | "reject" | "confirm" | "cancel" | "edit"
    label: str           # human readable button text


class PendingInterrupt(BaseModel):
    type: str                       # "email_review" | "confirm_booking"
    payload: dict[str, Any]         # raw interrupt value (draft text, flight id, etc.)
    actions: list[InterruptAction]  # exactly the buttons the frontend should show
    requires_feedback: bool = False  # true when an "edit" action needs a text field too


class ChatResponse(BaseModel):
    conversation_id: str
    final_response: Optional[str] = None
    pending_interrupt: Optional[PendingInterrupt] = None
    trace: list[str] = []  # ordered list of node names fired for this turn


class ResumeRequest(BaseModel):
    conversation_id: str
    action: str                 # "approve" | "edit" | "reject" | "confirm" | "cancel"
    feedback: Optional[str] = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    is_pending_interrupt: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []
