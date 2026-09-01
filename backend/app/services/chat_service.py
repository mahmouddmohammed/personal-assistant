"""Business logic for chat turns: creates/loads conversations, drives the
LangGraph facade, persists messages + the per-node execution trace, and
translates a paused graph into a `PendingInterrupt` the frontend can render
as buttons.
"""
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agent.graph_service import graph_service
from app.exceptions import ConversationNotFoundError

# How many prior messages (user+assistant combined) to hand to the graph as
# context each turn. Kept small on purpose (PRESERVE TOKENS) — this only
# needs to be enough for the orchestrator/continuity-sensitive workers to
# resolve a short follow-up, not a full transcript.
HISTORY_WINDOW = 8
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.session_log import SessionLog
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.session_log_repository import SessionLogRepository
from app.schemas.chat import (
    ChatResponse, ConversationDetail, ConversationOut, InterruptAction,
    PendingInterrupt, ResumeRequest,
)

# Declarative mapping from interrupt "type" -> the buttons the frontend renders.
# Adding a new HITL worker later means adding one entry here (Open/Closed principle).
_INTERRUPT_ACTIONS: dict[str, list[InterruptAction]] = {
    "email_review": [
        InterruptAction(action="approve", label="Approve"),
        InterruptAction(action="edit", label="Request changes"),
        InterruptAction(action="reject", label="Reject"),
    ],
    "confirm_booking": [
        InterruptAction(action="confirm", label="Confirm booking"),
        InterruptAction(action="cancel", label="Cancel"),
    ],
}


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.conversations = ConversationRepository(db)
        self.messages = MessageRepository(db)
        self.session_logs = SessionLogRepository(db)

    # ------------------------------------------------------------------ #
    # Conversation bookkeeping
    # ------------------------------------------------------------------ #
    def _get_or_create_conversation(self, user_id: str, conversation_id: Optional[str], title_hint: str) -> Conversation:
        if conversation_id:
            conv = self.conversations.get_owned_by(conversation_id, user_id)
            if not conv:
                raise ConversationNotFoundError("Conversation not found")
            return conv
        conv = Conversation(id=str(uuid.uuid4()), user_id=user_id, title=title_hint[:80])
        return self.conversations.add(conv)

    def list_conversations(self, user_id: str) -> list[ConversationOut]:
        return [ConversationOut.model_validate(c) for c in self.conversations.list_for_user(user_id)]

    def get_conversation_detail(self, user_id: str, conversation_id: str) -> ConversationDetail:
        conv = self.conversations.get_owned_by(conversation_id, user_id)
        if not conv:
            raise ConversationNotFoundError("Conversation not found")
        from app.schemas.chat import MessageOut

        msgs = self.messages.list_for_conversation(conversation_id)
        detail = ConversationDetail.model_validate(conv)
        detail.messages = [MessageOut.model_validate(m) for m in msgs]
        return detail

    # ------------------------------------------------------------------ #
    # Turn execution
    # ------------------------------------------------------------------ #
    def _persist_trace(self, conversation: Conversation, user_id: str, trace: list[tuple[str, Any]]) -> None:
        turn_id = str(uuid.uuid4())
        logs = [
            SessionLog(
                conversation_id=conversation.id,
                user_id=user_id,
                turn_id=turn_id,
                sequence=i,
                node_name=node_name,
                node_output=graph_service.serialize_node_output(node_output),
            )
            for i, (node_name, node_output) in enumerate(trace)
        ]
        if logs:
            self.session_logs.bulk_add(logs)

    @staticmethod
    def _build_pending_interrupt(raw: dict) -> PendingInterrupt:
        itype = raw.get("type", "unknown")
        return PendingInterrupt(
            type=itype,
            payload=raw,
            actions=_INTERRUPT_ACTIONS.get(itype, [InterruptAction(action="acknowledge", label="OK")]),
            requires_feedback=itype == "email_review",
        )

    def _recent_history(self, conversation_id: str) -> list[dict]:
        """Compact {role, content} pairs for the last HISTORY_WINDOW messages,
        oldest first — fetched BEFORE the new user message is persisted, so
        it's genuinely "what happened before this turn"."""
        prior = self.messages.list_for_conversation(conversation_id)[-HISTORY_WINDOW:]
        return [
            {"role": m.role, "content": m.content}
            for m in prior
            if not m.is_pending_interrupt  # "[Waiting for your input — ...]" placeholders add no value
        ]

    def send_message(self, user_id: str, message: str, conversation_id: Optional[str]) -> ChatResponse:
        conv = self._get_or_create_conversation(user_id, conversation_id, title_hint=message)
        history = self._recent_history(conv.id)
        self.messages.add(Message(conversation_id=conv.id, role="user", content=message))

        trace, pending_raw, final_response = graph_service.run_turn(conv.id, user_id, message, history)
        self._persist_trace(conv, user_id, trace)

        pending = None
        if pending_raw is not None:
            pending = self._build_pending_interrupt(pending_raw)
            self.messages.add(Message(
                conversation_id=conv.id, role="assistant",
                content=f"[Waiting for your input — {pending.type}]", is_pending_interrupt=True,
            ))
        else:
            self.messages.add(Message(conversation_id=conv.id, role="assistant", content=final_response or ""))

        conv.updated_at = conv.updated_at  # touch handled by onupdate on commit below
        self.db.commit()

        return ChatResponse(
            conversation_id=conv.id,
            final_response=final_response,
            pending_interrupt=pending,
            trace=[n for n, _ in trace],
        )

    def resume(self, user_id: str, payload: ResumeRequest) -> ChatResponse:
        conv = self.conversations.get_owned_by(payload.conversation_id, user_id)
        if not conv:
            raise ConversationNotFoundError("Conversation not found")

        if payload.action in ("confirm", "cancel"):
            resume_value: Any = payload.action
        else:
            resume_value = {"action": payload.action, "feedback": payload.feedback or ""}

        trace, pending_raw, final_response = graph_service.resume_turn(conv.id, resume_value)
        self._persist_trace(conv, user_id, trace)

        pending = None
        if pending_raw is not None:
            pending = self._build_pending_interrupt(pending_raw)
            self.messages.add(Message(
                conversation_id=conv.id, role="assistant",
                content=f"[Waiting for your input — {pending.type}]", is_pending_interrupt=True,
            ))
        else:
            self.messages.add(Message(conversation_id=conv.id, role="assistant", content=final_response or ""))

        self.db.commit()

        return ChatResponse(
            conversation_id=conv.id,
            final_response=final_response,
            pending_interrupt=pending,
            trace=[n for n, _ in trace],
        )
