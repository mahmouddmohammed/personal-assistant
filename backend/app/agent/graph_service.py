"""Facade over the compiled LangGraph (Facade + Singleton patterns).

Controllers/services never touch `graph.stream`/`graph.get_state` directly;
they call `graph_service.run_turn(...)` / `.resume_turn(...)` and get back
plain Python data: the ordered list of node names that fired (for the
admin trace view) plus either a final response or a pending interrupt.

The LangGraph checkpointer is backed by Postgres so paused
(human-in-the-loop) threads survive a backend restart — required for a
real deployment, unlike the notebook's in-memory `MemorySaver`.
"""
import logging
from typing import Any, Optional

from langgraph.types import Command
from pydantic import BaseModel

from app.agent.graph_builder import build_graph
from app.core.config import settings

logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    """Best-effort conversion of arbitrary node output into JSON-safe data
    for persistence in the SessionLog.node_output JSON column."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if hasattr(value, "content") and hasattr(value, "type"):  # LangChain message objects
        return {"type": getattr(value, "type", "message"), "content": str(getattr(value, "content", ""))}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class GraphService:
    """Singleton wrapper around the compiled graph + its checkpointer."""

    _instance: Optional["GraphService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._checkpointer_cm = None
        self._checkpointer = None
        self._graph = None
        self._initialized = True

    def setup(self) -> None:
        """Called once at FastAPI startup."""
        if self._graph is not None:
            return
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            self._checkpointer_cm = PostgresSaver.from_conn_string(settings.CHECKPOINTER_DATABASE_URL)
            self._checkpointer = self._checkpointer_cm.__enter__()
            self._checkpointer.setup()
            logger.info("LangGraph checkpointer: Postgres (persistent)")
        except Exception as exc:  # pragma: no cover - fallback path for local/dev use
            logger.warning("Falling back to in-memory checkpointer (%s). "
                            "Interrupted threads will NOT survive a restart.", exc)
            from langgraph.checkpoint.memory import MemorySaver
            self._checkpointer = MemorySaver()

        self._graph = build_graph(self._checkpointer)

    def close(self) -> None:
        if self._checkpointer_cm is not None:
            self._checkpointer_cm.__exit__(None, None, None)

    @property
    def graph(self):
        if self._graph is None:
            raise RuntimeError("GraphService.setup() must be called before use")
        return self._graph

    def _drain(self, stream_input, thread_id: str) -> list[tuple[str, Any]]:
        config = {"configurable": {"thread_id": thread_id}}
        trace: list[tuple[str, Any]] = []
        for update in self.graph.stream(stream_input, config=config, stream_mode="updates"):
            for node_name, node_output in update.items():
                trace.append((node_name, node_output))
        return trace

    def _read_result(self, thread_id: str) -> tuple[Optional[dict], Optional[str]]:
        config = {"configurable": {"thread_id": thread_id}}
        state = self.graph.get_state(config)
        if state.next:
            # Multiple workers can be fanned out via Send() in the same step
            # (e.g. summarize + email_write dispatched together). Only ONE of
            # them may actually call interrupt() (email_write's human review),
            # and state.tasks does not guarantee that task is first — a
            # finished, non-interrupting task can sit at index 0. Checking
            # only tasks[0] silently dropped real interrupts that landed
            # later in the list (see incident 2026-09-03).
            for task in state.tasks:
                if task.interrupts:
                    return task.interrupts[0].value, None
            logger.warning("Graph paused on thread %s with no interrupt payload", thread_id)
            return None, state.values.get("final_response", "")
        final_response = state.values.get("final_response", "")
        return None, final_response

    def run_turn(self, thread_id: str, user_id: str, message: str, history: Optional[list[dict]] = None,
                 summary: str = ""):
        """Starts (or continues, on a fresh thread) a top-level graph turn.

        `history` is the recent-turns context (list of {"role","content"}),
        and `summary` is the persisted running summary of anything older
        than that window (see chat_service._maybe_update_summary) — both
        supplied fresh by chat_service from persisted state each call, and
        both have no reducer in AssistantState, so they're simply
        overwritten each turn rather than accumulated.

        Returns (trace, pending_interrupt_or_None, final_response_or_None).
        """
        payload = {
            "user_id": user_id, "conversation_id": thread_id, "user_input": message,
            "history": history or [], "summary": summary, "worker_results": [],
        }
        try:
            trace = self._drain(payload, thread_id)
            pending, final_response = self._read_result(thread_id)
        except Exception:
            logger.exception("graph_service.run_turn: unhandled error on thread %s", thread_id)
            return [], None, "معلش، حصل عطل غير متوقع وأنا بحاول أصلحه. ممكن تجرب تاني؟"
        return trace, pending, final_response

    def resume_turn(self, thread_id: str, resume_value: Any):
        try:
            trace = self._drain(Command(resume=resume_value), thread_id)
            pending, final_response = self._read_result(thread_id)
        except Exception:
            logger.exception("graph_service.resume_turn: unhandled error on thread %s", thread_id)
            return [], None, "معلش، حصل عطل غير متوقع وأنا بحاول أصلحه. ممكن تجرب تاني؟"
        return trace, pending, final_response

    @staticmethod
    def serialize_node_output(node_output: Any) -> dict:
        result = _jsonable(node_output)
        return result if isinstance(result, dict) else {"value": result}


graph_service = GraphService()