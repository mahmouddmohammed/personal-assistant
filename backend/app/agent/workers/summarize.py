"""Worker 4 — summarize, then embed BOTH the raw text and the summary
(different source_types) so a detail dropped from the summary is still
retrievable for QA later."""
import logging

from pydantic import BaseModel

from app.agent.llm_factory import get_llm
from app.agent.memory.vector_store import persist_and_embed
from app.agent.state import WorkerResult

logger = logging.getLogger(__name__)


class SummaryResult(BaseModel):
    summary_text: str
    key_points: list[str]


def summarize_worker(task: dict) -> dict:
    llm = get_llm(SummaryResult)
    prompt = f"Summarize:\n\n{task['input_text']}"
    result = None
    last_exc = None
    for attempt in range(2):
        try:
            result = llm.invoke(prompt)
            break
        except Exception as exc:
            last_exc = exc
            logger.warning("summarize_worker: attempt %d failed for task_id=%s input_text=%r: %s",
                            attempt + 1, task.get("task_id"), task.get("input_text"), exc)

    if result is None:
        logger.error("summarize_worker: giving up after retries for task_id=%s input_text=%r",
                      task.get("task_id"), task.get("input_text"), exc_info=last_exc)
        wr = WorkerResult(task_id=task["task_id"], task_type="summarize", status="failed",
                           summary="معلش، مقدرتش ألخص النص ده دلوقتي.", data={})
        return {"worker_results": [wr]}

    # Persisting to memory is best-effort — a storage hiccup shouldn't hide
    # the summary the user actually asked for.
    try:
        persist_and_embed(task["user_id"], "transcript", task["task_id"], task["input_text"])
        persist_and_embed(task["user_id"], "summary", task["task_id"], result.summary_text)
    except Exception:
        logger.exception("summarize_worker: persist_and_embed failed")

    wr = WorkerResult(
        task_id=task["task_id"], task_type="summarize", status="completed",
        summary=result.summary_text, data=result.model_dump(),
    )
    return {"worker_results": [wr]}