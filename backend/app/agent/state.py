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


class SubTask(BaseModel):
    task_id: str = Field(description="short unique id, e.g. 't1', 't2'")
    task_type: TaskType
    input_text: str = Field(description="the slice of the user's message relevant to this task, verbatim")
    metadata: dict = Field(default_factory=dict)


class OrchestratorPlan(BaseModel):
    reasoning: str = Field(description="brief note on how the message was decomposed")
    tasks: list[SubTask]


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


class AssistantState(TypedDict):
    user_id: str
    user_input: str
    # Compact recent turns (list of {"role", "content"}), oldest first.
    # Supplied fresh by chat_service on every call to run_turn — this key
    # has NO reducer, so (unlike worker_results) it's simply overwritten
    # each turn rather than accumulated, which is exactly what we want.
    history: list[dict]
    plan: Optional[OrchestratorPlan]
    worker_results: Annotated[list[WorkerResult], _reduce_worker_results]
    final_response: str