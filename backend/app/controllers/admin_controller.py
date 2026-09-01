from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import require_admin
from app.schemas.admin import AdminConversationSummary, AdminUserSummary, SessionLogOut
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=list[AdminUserSummary])
def list_users(db: Session = Depends(get_db)):
    return AdminService(db).list_users()


@router.get("/conversations", response_model=list[AdminConversationSummary])
def list_conversations(db: Session = Depends(get_db)):
    return AdminService(db).list_all_conversations()


@router.get("/conversations/{conversation_id}/trace", response_model=list[SessionLogOut])
def conversation_trace(conversation_id: str, db: Session = Depends(get_db)):
    return AdminService(db).get_conversation_trace(conversation_id)


@router.get("/turns/{turn_id}/trace", response_model=list[SessionLogOut])
def turn_trace(turn_id: str, db: Session = Depends(get_db)):
    return AdminService(db).get_turn_trace(turn_id)


@router.get("/logs/recent", response_model=list[SessionLogOut])
def recent_logs(limit: int = 500, db: Session = Depends(get_db)):
    return AdminService(db).recent_logs(limit)
