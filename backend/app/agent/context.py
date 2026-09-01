"""Shared helper for turning persisted chat messages into a compact,
token-frugal string that the orchestrator / continuity-sensitive workers
(flight_booking, email_write) can drop into a prompt.

Nothing here calls an LLM or a DB — it's pure formatting, kept in one place
so every consumer trims to the same bounded size (PRESERVE TOKENS: we never
forward the full conversation, only a short recent window).
"""

MAX_HISTORY_TURNS = 6
MAX_CHARS_PER_TURN = 300


def format_history(history: list[dict] | None) -> str:
    """history: list of {"role": "user"|"assistant", "content": str}, oldest
    first (as stored). Returns "" when there's nothing usable, so callers
    can cheaply skip adding an empty context block."""
    if not history:
        return ""
    trimmed = history[-MAX_HISTORY_TURNS:]
    lines = []
    for turn in trimmed:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = (turn.get("content") or "").strip().replace("\n", " ")
        if not content:
            continue
        if len(content) > MAX_CHARS_PER_TURN:
            content = content[:MAX_CHARS_PER_TURN] + "…"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
