from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.conversation import Conversation
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_username(self, username: str) -> Optional[User]:
        return self.db.scalar(select(User).where(User.username == username))

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.scalar(select(User).where(User.email == email))

    def list_all(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.created_at.desc())))

    def count_conversations(self, user_id: str) -> int:
        return self.db.scalar(
            select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
        ) or 0
