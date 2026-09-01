"""Worker 5 — RAG. Refuses rather than hallucinates when nothing relevant
was retrieved."""
from pydantic import BaseModel, Field

from app.agent.llm_factory import get_llm
from app.agent.memory.vector_store import vector_search
from app.agent.state import WorkerResult


class QAAnswer(BaseModel):
    answer: str
    grounded: bool = Field(description="true if retrieved context actually supported the answer")


def qa_worker(task: dict) -> dict:
    chunks = vector_search(task["user_id"], task["input_text"], k=5)
    context = "\n---\n".join(c["text"] for c in chunks) if chunks else "(nothing found)"

    result: QAAnswer = get_llm(QAAnswer).invoke([
        {"role": "system", "content": "Answer using ONLY the context below. If the context doesn't "
                                       "support an answer, set grounded=false and say you don't know "
                                       "— never guess from outside knowledge."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {task['input_text']}"},
    ])

    wr = WorkerResult(
        task_id=task["task_id"], task_type="qa",
        status="completed", summary=result.answer,
        data={**result.model_dump(), "source_chunk_ids": [c["source_id"] for c in chunks]},
    )
    return {"worker_results": [wr]}
