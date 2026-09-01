from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SessionLogOut(BaseModel):
    id: str
    turn_id: str
    sequence: int
    node_name: str
    node_output: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class AdminConversationSummary(BaseModel):
    id: str
    user_id: str
    username: str
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class AdminUserSummary(BaseModel):
    id: str
    username: str
    email: str
    is_admin: bool
    is_active: bool
    conversation_count: int
    created_at: datetime
