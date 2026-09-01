"""Worker 1 — simplest possible: one LLM call, structured output, no loop."""
from typing import Literal, Optional

from pydantic import BaseModel

from app.agent.llm_factory import get_llm
from app.agent.state import WorkerResult


class EmailClassification(BaseModel):
    category: Literal["Respond", "Notify", "Ignore"]
    urgency: Literal["low", "medium", "high"]
    reasoning: str
    suggested_action: Optional[str] = None


def email_classify_worker(task: dict) -> dict:
    result: EmailClassification = get_llm(EmailClassification).invoke(
        f"Classify this email:\n\n{task['input_text']}, The reasoning Language should be the same as user."
    )
    wr = WorkerResult(
        task_id=task["task_id"], task_type="email_classify", status="completed",
        summary=f"Classification: {result.category} ({result.urgency} urgency) — {result.reasoning}",
        data=result.model_dump(),
    )
    return {"worker_results": [wr]}
