from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, ConversationDetail, ConversationOut, ResumeRequest
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/messages", response_model=ChatResponse)
def send_message(payload: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ChatService(db).send_message(user.id, payload.message, payload.conversation_id)


@router.post("/resume", response_model=ChatResponse)
def resume(payload: ResumeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ChatService(db).resume(user.id, payload)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ChatService(db).list_conversations(user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ChatService(db).get_conversation_detail(user.id, conversation_id)
