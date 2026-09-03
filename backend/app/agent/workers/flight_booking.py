"""Worker 6 — standard ReAct tool-calling loop. Only book_flight,
cancel_flight, and modify_flight (side-effecting) pause for confirmation —
search/check/list are read-only and run freely.
"""
import logging
import operator
from typing import Annotated, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from app.agent.context import format_context
from app.agent.llm_factory import get_llm, to_text
from app.agent.state import BookingSlot, WorkerResult, _merge_booking
from app.agent.tools.flight_tools import build_flight_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a friendly voice+text flight booking assistant.

Workflow you must follow:
1. search_flights takes origin, destination and date, and ALL THREE ARE OPTIONAL — call it
   with whatever the user has actually given you so far, even just one field (e.g. only a
   destination for "what flights go to Dubai", only a date for "what's flying out on the 5th").
   Do not ask the user to fill in fields they haven't mentioned just to have all three — only
   ask a follow-up question if the results are too broad to read out loud or the user needs to
   narrow things down to pick a specific flight to book.
2. If search_flights returns status "unavailable" (only possible when origin, destination AND
   date were all given), read out the alternative times/dates it returns and ask the user to
   pick one instead of guessing. If a broader search (missing fields) returns several flights,
   summarize them briefly and ask which one they want, rather than reading out every result.
3. Before booking, call check_calendar_availability for the chosen flight's boarding window
   (2 hours before departure through arrival). If it's not available, tell the user about the
   conflict and ask how they'd like to proceed.
4. Only call book_flight after the user explicitly confirms the specific flight and passenger name.
5. After booking, tell the user it's booked and that a link to add it to their Google Calendar is
   shown in the chat.
6. If the user asks what they've booked, call list_calendar_events.
7. If the user wants to cancel a booking: if you already know which booking_ref they mean (from
   the structured booking-state message below, or because there's exactly one booking from
   list_calendar_events), call cancel_flight directly with it. If there's more than one active
   booking and it's not clear which one, call list_calendar_events and ask the user to pick
   before calling cancel_flight — never guess which booking to cancel.
8. If the user wants to change/move a booking to a different flight: search_flights for the new
   option, confirm it with the user, then call modify_flight with the existing booking_ref and
   the new flight_id. Same rule as cancellation — don't guess the booking_ref if it's ambiguous.

Speak in Egyptian Arabic with code switching with English if needed, if user speaks different language speak the language of the user.
Keep spoken responses short and conversational. Never invent flight data — always use the tools."""


class FlightBookingState(TypedDict):
    task_id: str
    task_type: str
    input_text: str
    metadata: dict
    user_id: str
    conversation_id: Optional[str]
    worker_results: Annotated[list[WorkerResult], operator.add]
    messages: Annotated[list[BaseMessage], add_messages]
    active_booking: Annotated[BookingSlot, _merge_booking]
    _agent_error: bool


def _slot_from_tool_calls(response) -> Optional[BookingSlot]:
    """Captures the LLM's own booking/cancel/modify intent the moment it
    decides to call one of those tools — BEFORE interrupt() pauses the
    whole graph — so a structured flight_id/booking_ref is already
    checkpointed even though the tool call itself hasn't completed yet."""
    if not isinstance(response, AIMessage) or not response.tool_calls:
        return None
    for call in response.tool_calls:
        name, args = call.get("name"), call.get("args") or {}
        if name == "book_flight":
            return BookingSlot(status="awaiting_confirmation", flight_id=args.get("flight_id"),
                                passenger_name=args.get("passenger_name"))
        if name == "cancel_flight":
            return BookingSlot(status="awaiting_confirmation", booking_ref=args.get("booking_ref"))
        if name == "modify_flight":
            return BookingSlot(status="awaiting_confirmation", booking_ref=args.get("booking_ref"),
                                flight_id=args.get("new_flight_id"))
        if name == "search_flights":
            return BookingSlot(status="searching", origin=args.get("origin") or None,
                                destination=args.get("destination") or None, date=args.get("date") or None)
    return None


def agent(state: FlightBookingState) -> dict:
    tools = build_flight_tools(state["user_id"], state.get("conversation_id"))
    llm_with_tools = get_llm().bind_tools(tools)

    messages = state.get("messages")
    if not messages:
        meta = state.get("metadata") or {}
        context_block = format_context(meta.get("_summary"), meta.get("_history"))
        seed = [SystemMessage(content=SYSTEM_PROMPT)]
        if context_block:
            seed.append(SystemMessage(
                content=f"Conversation context so far (flights/dates already discussed):\n{context_block}"
            ))
        booking = state.get("active_booking")
        if booking and booking.status != "none":
            seed.append(SystemMessage(content=(
                "Structured booking state carried over from earlier in this conversation. This is "
                "more reliable than free text above — use its flight_id/booking_ref directly instead "
                "of re-deriving or re-confirming it from scratch, unless the user's new message "
                f"contradicts it: {booking.model_dump_json(exclude_none=True)}"
            )))
        seed.append(HumanMessage(content=state["input_text"]))
        try:
            response = llm_with_tools.invoke(seed)
        except Exception:
            logger.exception("flight_booking agent: LLM call failed on first turn")
            return {"messages": seed, "_agent_error": True}
        update: dict = {"messages": seed + [response]}
    else:
        try:
            response = llm_with_tools.invoke(messages)
        except Exception:
            logger.exception("flight_booking agent: LLM call failed")
            return {"_agent_error": True}
        update = {"messages": [response]}

    slot = _slot_from_tool_calls(response)
    if slot is not None:
        update["active_booking"] = slot
    return update


def sync_booking_state(state: FlightBookingState) -> dict:
    """Runs right after the tools node. Reads the structured `artifact` off
    the booking-related tools (book_flight/cancel_flight/modify_flight use
    `response_format="content_and_artifact"` precisely so this doesn't have
    to re-parse stringified tool output) and reconciles `active_booking`
    with what actually happened, rather than what the LLM merely asked for.
    """
    messages = state.get("messages") or []
    tool_msgs: list[ToolMessage] = []
    for m in reversed(messages):
        if isinstance(m, ToolMessage):
            tool_msgs.append(m)
        else:
            break
    tool_msgs.reverse()

    for tm in tool_msgs:
        artifact = getattr(tm, "artifact", None)
        if not isinstance(artifact, dict):
            continue
        status = artifact.get("status")
        if status == "booked":
            b = artifact.get("booking") or {}
            return {"active_booking": BookingSlot(status="booked", flight_id=b.get("flight_id"),
                                                   passenger_name=b.get("passenger_name"), booking_ref=b.get("id"))}
        if status in ("cancelled", "kept", "error"):
            return {"active_booking": BookingSlot(status="none")}
    return {}


def should_continue(state: FlightBookingState) -> str:
    if state.get("_agent_error"):
        return "finalize"
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else "finalize"


def finalize(state: FlightBookingState) -> dict:
    if state.get("_agent_error") or not state.get("messages"):
        summary = "معلش، حصل عطل وأنا بدور على الرحلات. جرب تاني كمان شوية."
        status = "failed"
    else:
        summary = to_text(state["messages"][-1].content)
        status = "completed"
    wr = WorkerResult(task_id=state["task_id"], task_type="flight_booking", status=status,
                       summary=summary, data={})
    return {"worker_results": [wr]}


def tools_node(state: FlightBookingState) -> dict:
    # Rebuilt per call (not a module-level singleton) since it must be
    # bound to *this* task's user_id — see build_flight_tools docstring.
    tools = build_flight_tools(state["user_id"], state.get("conversation_id"))
    return ToolNode(tools).invoke(state)


def build_flight_booking_subgraph():
    g = StateGraph(FlightBookingState)
    g.add_node("agent", agent)
    g.add_node("tools", tools_node)
    g.add_node("sync_booking_state", sync_booking_state)
    g.add_node("finalize", finalize)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", should_continue, {"tools": "tools", "finalize": "finalize"})
    g.add_edge("tools", "sync_booking_state")
    g.add_edge("sync_booking_state", "agent")
    g.add_edge("finalize", END)
    return g.compile()


flight_booking_worker = build_flight_booking_subgraph()
