"""Worker 1 — simplest possible: one LLM call, structured output, no loop."""
import logging
from typing import Literal, Optional

from pydantic import BaseModel

from app.agent.llm_factory import get_llm
from app.agent.state import WorkerResult

logger = logging.getLogger(__name__)


class EmailClassification(BaseModel):
    category: Literal["Respond", "Notify", "Ignore"]
    urgency: Literal["low", "medium", "high"]
    reasoning: str
    suggested_action: Optional[str] = None


def email_classify_worker(task: dict) -> dict:
    try:
        result: EmailClassification = get_llm(EmailClassification).invoke(
            f"Classify this email:\n\n{task['input_text']}, The reasoning Language should be the same as user."
        )
    except Exception:
        logger.exception("email_classify_worker: LLM call failed")
        wr = WorkerResult(task_id=task["task_id"], task_type="email_classify", status="failed",
                           summary="معلش، مقدرتش أصنف الإيميل ده دلوقتي.", data={})
        return {"worker_results": [wr]}

    wr = WorkerResult(
        task_id=task["task_id"], task_type="email_classify", status="completed",
        summary=f"Classification: {result.category} ({result.urgency} urgency) — {result.reasoning}",
        data=result.model_dump(),
    )
    return {"worker_results": [wr]}
