"""LLM factory — one function, used by every node (Factory pattern).

Centralizing construction here means the model name, provider, and any
future retry/rate-limit wrapping live in exactly one place.
"""
from typing import Optional, Type

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.core.config import settings


def get_llm(structured_output: Optional[Type[BaseModel]] = None, temperature: float = 0.0):
    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        temperature=temperature,
        google_api_key=settings.GEMINI_API_KEY,
    )
    if structured_output:
        return llm.with_structured_output(structured_output)
    return llm


def to_text(content) -> str:
    """AIMessage.content can be str or a list of content-block dicts
    (Gemini sometimes returns multi-part output). Normalize to plain str."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b if isinstance(b, str) else b.get("text", "")
            for b in content if isinstance(b, (str, dict))
        )
    return str(content)
