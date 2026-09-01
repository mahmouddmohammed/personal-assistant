from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message
from app.repositories.base_repository import BaseRepository


class MessageRepository(BaseRepository[Message]):
    model = Message

    def list_for_conversation(self, conversation_id: str) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(self.db.scalars(stmt))
