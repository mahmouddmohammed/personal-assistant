"""Shared state schema for the top-level orchestrator graph.

Ported 1:1 from the notebook's Section 1. `worker_results` uses
`operator.add` as its reducer, which is what lets parallel `Send()`
fan-outs each append their own result without clobbering the others.
"""
import operator
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


class AssistantState(TypedDict):
    user_id: str
    user_input: str
    plan: Optional[OrchestratorPlan]
    worker_results: Annotated[list[WorkerResult], operator.add]
    final_response: str
