"""Memory infra: chunk -> embed -> store -> search.

In-process vector store (list of dicts), same as the notebook prototype.
Swap this module for a pgvector/Chroma-backed implementation later without
touching any worker — `persist_and_embed` and `vector_search` are the only
two functions the rest of the agent is allowed to call.
"""
import math
import uuid
from functools import lru_cache

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import settings

_STORE: list[dict] = []  # {id, user_id, source_type, source_id, text, vector}


@lru_cache(maxsize=1)
def _embeddings() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(model=settings.EMBEDDING_MODEL, google_api_key=settings.GEMINI_API_KEY)


def chunk_text(text: str, words_per_chunk: int = 150, overlap: int = 30) -> list[str]:
    """Word-count chunker with overlap."""
    words = text.split()
    if not words:
        return []
    chunks, start = [], 0
    while start < len(words):
        end = start + words_per_chunk
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


def embed(text: str) -> list[float]:
    return _embeddings().embed_query(text)


def persist_and_embed(user_id: str, source_type: str, source_id: str, text: str) -> None:
    """The ONLY function allowed to write to the store."""
    for chunk in chunk_text(text):
        _STORE.append({
            "id": str(uuid.uuid4()), "user_id": user_id, "source_type": source_type,
            "source_id": source_id, "text": chunk, "vector": embed(chunk),
        })


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def vector_search(user_id: str, query: str, k: int = 5) -> list[dict]:
    """MUST filter by user_id — never let one user's search see another's chunks."""
    qvec = embed(query)
    scored = [
        (entry, _cosine(qvec, entry["vector"]))
        for entry in _STORE if entry["user_id"] == user_id
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [
        {"text": e["text"], "source_type": e["source_type"], "source_id": e["source_id"], "score": s}
        for e, s in scored[:k]
    ]
