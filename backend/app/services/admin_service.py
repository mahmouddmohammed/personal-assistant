"""Business logic backing the admin dashboard: user list, every
conversation across all users, and the per-prompt node-firing trace
(mirrors the notebook's `graph.stream(..., stream_mode='updates')` output,
persisted instead of printed)."""
from sqlalchemy.orm import Session

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.session_log_repository import SessionLogRepository
from app.repositories.user_repository import UserRepository
from app.schemas.admin import AdminConversationSummary, AdminUserSummary, SessionLogOut


class AdminService:
    def __init__(self, db: Session):
        self.users = UserRepository(db)
        self.conversations = ConversationRepository(db)
        self.session_logs = SessionLogRepository(db)

    def list_users(self) -> list[AdminUserSummary]:
        return [
            AdminUserSummary(
                id=u.id, username=u.username, email=u.email, is_admin=u.is_admin,
                is_active=u.is_active, conversation_count=self.users.count_conversations(u.id),
                created_at=u.created_at,
            )
            for u in self.users.list_all()
        ]

    def list_all_conversations(self) -> list[AdminConversationSummary]:
        result = []
        for c in self.conversations.list_all():
            result.append(AdminConversationSummary(
                id=c.id, user_id=c.user_id, username=c.user.username if c.user else "?",
                title=c.title, message_count=len(c.messages),
                created_at=c.created_at, updated_at=c.updated_at,
            ))
        return result

    def get_conversation_trace(self, conversation_id: str) -> list[SessionLogOut]:
        logs = self.session_logs.list_for_conversation(conversation_id)
        return [SessionLogOut.model_validate(l) for l in logs]

    def get_turn_trace(self, turn_id: str) -> list[SessionLogOut]:
        logs = self.session_logs.list_for_turn(turn_id)
        return [SessionLogOut.model_validate(l) for l in logs]

    def recent_logs(self, limit: int = 500) -> list[SessionLogOut]:
        return [SessionLogOut.model_validate(l) for l in self.session_logs.list_all(limit)]
