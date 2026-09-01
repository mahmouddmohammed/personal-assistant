"""Worker 7 — linear chain: build a good arXiv query, search, summarize.
No Send fan-out needed — nothing here is parallel."""
from typing import Optional

from pydantic import BaseModel, Field

from app.agent.llm_factory import get_llm, to_text
from app.agent.state import WorkerResult
from app.agent.tools.arxiv_tool import search_arxiv


class PaperResult(BaseModel):
    title: str
    authors: list[str]
    url: str
    published: Optional[str]
    summary: str = Field(description="1-2 sentence relevance note, NOT the raw abstract verbatim")


class ResearchAnswer(BaseModel):
    query_used: str
    papers: list[PaperResult]
    note: str = ""


def research_worker(task: dict) -> dict:
    query = to_text(get_llm(temperature=0.2).invoke(
        f"Turn this into a 2-4 word arXiv keyword search query (no punctuation, no explanation): "
        f"{task['input_text']}"
    ).content).strip()

    raw_papers = search_arxiv(query, max_results=5)

    if not raw_papers:
        result = ResearchAnswer(query_used=query, papers=[],
                                 note="No strong matches — try broadening the topic.")
    else:
        result: ResearchAnswer = get_llm(ResearchAnswer).invoke(
            f"Query used: {query}\n\nRank and write an original 1-2 sentence relevance note per paper "
            f"(don't copy the abstract) for the user's request: {task['input_text']}\n\n"
            f"Papers:\n{raw_papers}"
        )

    summary = (f"Found {len(result.papers)} papers for '{result.query_used}'."
               if result.papers else result.note)
    wr = WorkerResult(
        task_id=task["task_id"], task_type="research_assistant", status="completed",
        summary=summary, data=result.model_dump(),
    )
    return {"worker_results": [wr]}
