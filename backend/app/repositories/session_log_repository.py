from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.session_log import SessionLog
from app.repositories.base_repository import BaseRepository


class SessionLogRepository(BaseRepository[SessionLog]):
    model = SessionLog

    def bulk_add(self, logs: list[SessionLog]) -> None:
        self.db.add_all(logs)
        self.db.commit()

    def list_for_turn(self, turn_id: str) -> list[SessionLog]:
        stmt = select(SessionLog).where(SessionLog.turn_id == turn_id).order_by(SessionLog.sequence.asc())
        return list(self.db.scalars(stmt))

    def list_for_conversation(self, conversation_id: str) -> list[SessionLog]:
        stmt = (
            select(SessionLog)
            .where(SessionLog.conversation_id == conversation_id)
            .order_by(SessionLog.created_at.asc(), SessionLog.sequence.asc())
        )
        return list(self.db.scalars(stmt))

    def list_all(self, limit: int = 500) -> list[SessionLog]:
        stmt = select(SessionLog).order_by(SessionLog.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))
