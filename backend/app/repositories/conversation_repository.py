from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.conversation import Conversation
from app.repositories.base_repository import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    def list_for_user(self, user_id: str) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(self.db.scalars(stmt))

    def get_with_messages(self, conversation_id: str) -> Optional[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(joinedload(Conversation.messages))
        )
        return self.db.scalar(stmt)

    def get_owned_by(self, conversation_id: str, user_id: str) -> Optional[Conversation]:
        conv = self.get(conversation_id)
        if conv and conv.user_id == user_id:
            return conv
        return None

    def list_all(self) -> list[Conversation]:
        return list(self.db.scalars(select(Conversation).order_by(Conversation.updated_at.desc())))
