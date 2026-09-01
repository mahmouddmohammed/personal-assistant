"""Worker 4 — summarize, then embed BOTH the raw text and the summary
(different source_types) so a detail dropped from the summary is still
retrievable for QA later."""
from pydantic import BaseModel

from app.agent.llm_factory import get_llm
from app.agent.memory.vector_store import persist_and_embed
from app.agent.state import WorkerResult


class SummaryResult(BaseModel):
    summary_text: str
    key_points: list[str]


def summarize_worker(task: dict) -> dict:
    result: SummaryResult = get_llm(SummaryResult).invoke(f"Summarize:\n\n{task['input_text']}")

    persist_and_embed(task["user_id"], "transcript", task["task_id"], task["input_text"])
    persist_and_embed(task["user_id"], "summary", task["task_id"], result.summary_text)

    wr = WorkerResult(
        task_id=task["task_id"], task_type="summarize", status="completed",
        summary=result.summary_text, data=result.model_dump(),
    )
    return {"worker_results": [wr]}
