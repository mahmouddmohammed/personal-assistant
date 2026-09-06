"""Business logic for chat turns: creates/loads conversations, drives the
LangGraph facade, persists messages + the per-node execution trace, and
translates a paused graph into a `PendingInterrupt` the frontend can render
as buttons.
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agent.graph_service import graph_service
from app.agent.llm_factory import get_llm, to_text
from app.exceptions import ConversationNotFoundError

logger = logging.getLogger(__name__)

# How many prior messages (user+assistant combined) to hand to the graph as
# raw context each turn. Kept small on purpose (PRESERVE TOKENS) — this
# only needs to be enough for the orchestrator/continuity-sensitive workers
# to resolve a short follow-up, not a full transcript. Anything older than
# this window is folded into `Conversation.summary` instead of just being
# dropped — see `_maybe_update_summary` below.
HISTORY_WINDOW = 8

# Only start summarizing once a conversation has grown past this many
# messages — short conversations never lose anything to the truncation
# window in the first place, so there's nothing worth summarizing yet.
SUMMARY_TRIGGER_MESSAGES = 20
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
    "confirm_cancel_booking": [
        InterruptAction(action="confirm", label="Yes, cancel it"),
        InterruptAction(action="cancel", label="No, keep it"),
    ],
    "confirm_modify_booking": [
        InterruptAction(action="confirm", label="Yes, change it"),
        InterruptAction(action="cancel", label="No, keep original"),
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

    def _maybe_update_summary(self, conv: Conversation) -> None:
        """Folds messages that have aged out of HISTORY_WINDOW into
        `conv.summary`, instead of letting them just disappear.

        Runs BEFORE the new user message is persisted (same ordering as
        `_recent_history`), and only touches the slice of messages between
        what's already summarized (`summary_through`) and what's about to
        fall outside the raw window — so nothing is summarized twice and
        nothing in the raw window is redundantly summarized early.
        """
        all_msgs = self.messages.list_for_conversation(conv.id)
        total = len(all_msgs)
        if total < SUMMARY_TRIGGER_MESSAGES:
            return

        already = conv.summary_through or 0
        fold_end = max(0, total - HISTORY_WINDOW)
        if fold_end <= already:
            return  # nothing new has aged out of the window since last time

        new_slice = [m for m in all_msgs[already:fold_end] if not m.is_pending_interrupt]
        if not new_slice:
            conv.summary_through = fold_end
            return

        text_block = "\n".join(f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in new_slice)
        if conv.summary:
            prompt = (f"This is the summary of the conversation so far:\n{conv.summary}\n\n"
                      "Extend the summary by taking into account the new messages below. Keep it concise, "
                      "and keep concrete facts (names, dates, flight/booking ids, decisions made) intact "
                      "rather than vaguely paraphrasing them away.\n\n" + text_block)
        else:
            prompt = ("Create a concise summary of the conversation below. Keep concrete facts (names, "
                      "dates, flight/booking ids, decisions made) intact rather than vaguely paraphrasing "
                      "them away.\n\n" + text_block)

        try:
            response = get_llm(temperature=0.2).invoke(prompt)
            conv.summary = to_text(response.content)
            conv.summary_through = fold_end
        except Exception:
            # Non-fatal: worst case we fall back to the old behavior (raw
            # window only, older context missing) for this turn and retry
            # on the next one — never blocks the actual chat turn.
            logger.exception("chat_service: summary update failed for conversation %s", conv.id)

    @staticmethod
    def _touch(conv: Conversation) -> None:
        """
        Assign an actually new timestamp to updated_at so the change is persisted and list_for_user correctly surfaces the most recently active conversation first.

        The bug was that conv.updated_at = conv.updated_at marked the object dirty but did not actually change its value, so SQLAlchemy skipped the UPDATE. As a result, conversations stayed ordered by creation time instead of recent activity.
        """
        conv.updated_at = datetime.utcnow()

    def send_message(self, user_id: str, message: str, conversation_id: Optional[str]) -> ChatResponse:
        conv = self._get_or_create_conversation(user_id, conversation_id, title_hint=message)
        self._maybe_update_summary(conv)
        history = self._recent_history(conv.id)
        self.messages.add(Message(conversation_id=conv.id, role="user", content=message))

        trace, pending_raw, final_response = graph_service.run_turn(
            conv.id, user_id, message, history, summary=conv.summary or "",
        )
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

        self._touch(conv)
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

        
        self._touch(conv)
        self.db.commit()

        return ChatResponse(
            conversation_id=conv.id,
            final_response=final_response,
            pending_interrupt=pending,
            trace=[n for n, _ in trace],
        )
