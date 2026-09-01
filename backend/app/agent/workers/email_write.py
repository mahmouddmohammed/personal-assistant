"""Worker 2 — Evaluator-Optimizer (self-critique loop) + Human-in-the-Loop.

Compiled as its own subgraph, added as a node in the top-level graph so it
shares the top-level checkpointer (required for interrupt()).
"""
import operator
from typing import Annotated, Literal

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from pydantic import BaseModel
from typing_extensions import TypedDict

from app.agent.llm_factory import get_llm, to_text
from app.agent.state import WorkerResult

MAX_RETRIES = 2


class EmailEvaluation(BaseModel):
    approved: bool
    feedback: str = ""


class EmailWriteState(TypedDict):
    task_id: str
    task_type: str
    input_text: str          # instructions: recipient, content, sender/signoff
    metadata: dict
    user_id: str
    worker_results: Annotated[list[WorkerResult], operator.add]
    draft: str
    evaluator_feedback: str
    human_feedback: str
    human_action: Literal["approve", "edit", "reject", ""]
    revision_count: int


def draft_email(state: EmailWriteState) -> dict:
    feedback = state.get("evaluator_feedback") or state.get("human_feedback") or ""
    prompt = f"Instructions: {state['input_text']}"
    if feedback:
        prompt += f"\n\nRevise based on this feedback: {feedback}"
    draft = to_text(get_llm(temperature=0.6).invoke(prompt).content)
    return {"draft": draft, "revision_count": state.get("revision_count", 0) + 1}


def evaluate_email(state: EmailWriteState) -> dict:
    ev: EmailEvaluation = get_llm(EmailEvaluation).invoke(
        f"Instructions: {state['input_text']}\n\nDraft:\n{state['draft']}\n\n"
        f"Approve only if it fully satisfies the instructions, tone, and length."
    )
    return {"evaluator_feedback": "" if ev.approved else ev.feedback, "_approved": ev.approved}


def route_after_eval(state: EmailWriteState) -> str:
    if state.get("_approved") or state["revision_count"] >= MAX_RETRIES:
        return "human_review"
    return "draft_email"


def human_review(state: EmailWriteState) -> dict:
    decision = interrupt({"type": "email_review", "draft": state["draft"],
                           "question": "approve, edit, or reject?"})
    return {"human_action": decision.get("action", "reject"), "human_feedback": decision.get("feedback", "")}


def route_after_human(state: EmailWriteState) -> str:
    return {"approve": "finalize", "edit": "draft_email", "reject": "finalize"}[state["human_action"]]


def finalize(state: EmailWriteState) -> dict:
    status = "completed" if state["human_action"] != "reject" else "failed"
    summary = state["draft"] if status == "completed" else "Draft rejected by user."
    wr = WorkerResult(task_id=state["task_id"], task_type="email_write", status=status,
                       summary=summary, data={"draft": state["draft"]})
    return {"worker_results": [wr]}


def build_email_write_subgraph():
    g = StateGraph(EmailWriteState)
    g.add_node("draft_email", draft_email)
    g.add_node("evaluate_email", evaluate_email)
    g.add_node("human_review", human_review)
    g.add_node("finalize", finalize)
    g.add_edge(START, "draft_email")
    g.add_edge("draft_email", "evaluate_email")
    g.add_conditional_edges("evaluate_email", route_after_eval, {"human_review": "human_review", "draft_email": "draft_email"})
    g.add_conditional_edges("human_review", route_after_human, {"finalize": "finalize", "draft_email": "draft_email"})
    g.add_edge("finalize", END)
    return g.compile()


email_write_worker = build_email_write_subgraph()
