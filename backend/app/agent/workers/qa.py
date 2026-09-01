"""Worker 5 — RAG. Refuses rather than hallucinates when nothing relevant
was retrieved."""
import logging

from pydantic import BaseModel, Field

from app.agent.llm_factory import get_llm
from app.agent.memory.vector_store import vector_search
from app.agent.state import WorkerResult

logger = logging.getLogger(__name__)


class QAAnswer(BaseModel):
    answer: str
    grounded: bool = Field(description="true if retrieved context actually supported the answer")


def qa_worker(task: dict) -> dict:
    try:
        chunks = vector_search(task["user_id"], task["input_text"], k=5)
    except Exception:
        logger.exception("qa_worker: vector_search failed")
        chunks = []
    context = "\n---\n".join(c["text"] for c in chunks) if chunks else "(nothing found)"

    try:
        result: QAAnswer = get_llm(QAAnswer).invoke([
            {"role": "system", "content": "Answer using ONLY the context below. If the context doesn't "
                                           "support an answer, set grounded=false and say you don't know "
                                           "— never guess from outside knowledge."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {task['input_text']}"},
        ])
    except Exception:
        logger.exception("qa_worker: LLM call failed")
        wr = WorkerResult(task_id=task["task_id"], task_type="qa", status="failed",
                           summary="معلش، مقدرتش أدور على إجابة دلوقتي.", data={})
        return {"worker_results": [wr]}

    wr = WorkerResult(
        task_id=task["task_id"], task_type="qa",
        status="completed", summary=result.answer,
        data={**result.model_dump(), "source_chunk_ids": [c["source_id"] for c in chunks]},
    )
    return {"worker_results": [wr]}
