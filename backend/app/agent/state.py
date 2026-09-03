"""Shared state schema for the top-level orchestrator graph.

`worker_results` used to reduce with plain `operator.add`. Because the
Postgres checkpointer persists `AssistantState` per conversation
(`thread_id` == conversation id) across *every* turn, `operator.add` meant
each new turn's results kept getting appended on top of every previous
turn's results forever — the aggregator would then blend stale results
from turn 1 into the reply for turn 3, producing the "everything is mixed
up" symptom. `_reduce_worker_results` below still lets a single turn's
parallel `Send()` fan-out accumulate normally, but the orchestrator node
(which runs exactly once, first, on every turn) emits a `RESET_WORKER_RESULTS`
sentinel that clears the list before that turn's workers add anything.
"""
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

TaskType = Literal[
    "email_classify", "email_write", "extract_info",
    "summarize", "qa", "flight_booking", "research_assistant",
]

class PlannedTask(BaseModel):
    task_id: str = Field(description="short unique id, e.g. 't1', 't2'")
    task_type: TaskType
    input_text: str = Field(description="the slice of the user's message relevant to this task, verbatim")


class OrchestratorPlan(BaseModel):
    reasoning: str = Field(description="brief note on how the message was decomposed")
    tasks: list[PlannedTask]


class WorkerResult(BaseModel):
    task_id: str
    task_type: TaskType
    status: Literal["completed", "needs_human_input", "failed"]
    summary: str
    data: dict = Field(default_factory=dict)


RESET_WORKER_RESULTS = "__RESET_WORKER_RESULTS__"
"""Sentinel: when it's the first element of an incoming `worker_results`
update, the reducer drops everything accumulated so far instead of
appending. See module docstring.

Must be a plain, msgpack-serializable value (a str, not a custom class
instance) because the Postgres checkpointer persists every pending state
write via `ormsgpack`, which only knows how to encode plain data types —
an arbitrary Python object crashes serialization (see graph_service traceback:
`TypeError: Type is not msgpack serializable`). Compared by value (`==`),
not identity (`is`), since a value round-tripped through the checkpointer
is a new (but equal) string object, not the same object identity."""


def _reduce_worker_results(existing: list[WorkerResult], new: list) -> list[WorkerResult]:
    if new and new[0] == RESET_WORKER_RESULTS:
        return list(new[1:])
    return list(existing) + list(new)


class BookingSlot(BaseModel):
    """Structured record of the flight the user is *currently* searching /
    about to confirm / just booked or cancelled -- kept in the top-level,
    checkpointed `AssistantState` (NOT the flight_booking subgraph's own
    `messages`, which do not survive across turns since every turn is a
    fresh `Send()` invocation of that subgraph).

    This is what actually fixes the bug documented in
    `documentation/check.md` turn 2: without this, the agent has no
    structured `flight_id` to pass to `book_flight` on the confirming
    turn -- only a plain-text history sentence with no id in it -- so it
    re-asks "is this the one you meant?" instead of booking.

    This slot only ever tracks the ONE booking currently in flight through
    the search -> confirm -> book/modify/cancel conversation. Once a
    booking reaches "booked", the fact of its existence lives permanently
    in the `bookings` DB table (see app/models/booking.py), scoped by
    user_id -- this slot is not a list of a user's bookings and is allowed
    to be overwritten by the next search.
    """
    status: Literal["none", "searching", "awaiting_confirmation", "booked", "cancelled"] = "none"
    flight_id: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    date: Optional[str] = None
    passenger_name: Optional[str] = None
    booking_ref: Optional[str] = None


def _merge_booking(existing: BookingSlot, new: Optional[BookingSlot]) -> BookingSlot:
    """Last-write-wins; `None` means "no update this step" (the node simply
    didn't touch booking state), NOT "clear it". Nodes that genuinely want
    to reset the slot (e.g. after a cancellation) must return an explicit
    `BookingSlot()` (status="none"), not None."""
    return new if new is not None else existing


class AssistantState(TypedDict):
    user_id: str
    conversation_id: str
    user_input: str
    history: list[dict]
    summary: str
    plan: Optional[OrchestratorPlan]
    worker_results: Annotated[list[WorkerResult], _reduce_worker_results]
    active_booking: Annotated[BookingSlot, _merge_booking]
    final_response: str