"""Worker 6 — standard ReAct tool-calling loop. Only book_flight
(side-effecting) pauses for confirmation — search/check/list are
read-only and run freely."""
import operator
from functools import lru_cache
from typing import Annotated

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from app.agent.llm_factory import get_llm, to_text
from app.agent.state import WorkerResult
from app.agent.tools.flight_tools import FLIGHT_TOOLS

#SYSTEM_PROMPT = ("You are a flight booking assistant. Search flights, check/list the user's calendar, "
#                  "and book flights. Check calendar availability before booking if the user hasn't "
#                  "confirmed the time works. Never call book_flight without a specific flight_id and "
#                  "the passenger's name.")


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

Speak in Egyptian Arabic with code switching with English if needed, if user speaks different language speak the language of the user.
Keep spoken responses short and conversational. Never invent flight data — always use the tools."""

class FlightBookingState(TypedDict):
    task_id: str
    task_type: str
    input_text: str
    metadata: dict
    user_id: str
    worker_results: Annotated[list[WorkerResult], operator.add]
    messages: Annotated[list[BaseMessage], add_messages]


@lru_cache(maxsize=1)
def _llm_with_tools():
    return get_llm().bind_tools(FLIGHT_TOOLS)


def agent(state: FlightBookingState) -> dict:
    messages = state.get("messages")
    if not messages:
        # First call: seed with system+user and PERSIST both into state,
        # not just use them locally for this one invoke.
        seed = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=state["input_text"])]
        response = _llm_with_tools().invoke(seed)
        return {"messages": seed + [response]}
    response = _llm_with_tools().invoke(messages)
    return {"messages": [response]}


def should_continue(state: FlightBookingState) -> str:
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else "finalize"


def finalize(state: FlightBookingState) -> dict:
    wr = WorkerResult(task_id=state["task_id"], task_type="flight_booking", status="completed",
                       summary=to_text(state["messages"][-1].content), data={})
    return {"worker_results": [wr]}


def build_flight_booking_subgraph():
    g = StateGraph(FlightBookingState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(FLIGHT_TOOLS))
    g.add_node("finalize", finalize)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", should_continue, {"tools": "tools", "finalize": "finalize"})
    g.add_edge("tools", "agent")
    g.add_edge("finalize", END)
    return g.compile()


flight_booking_worker = build_flight_booking_subgraph()
