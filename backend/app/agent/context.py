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


def format_context(summary: str | None, history: list[dict] | None) -> str:
    """Combines the persisted running summary (everything older than the
    raw window — see chat_service._maybe_update_summary) with the recent
    raw turns, into one block callers can drop straight into a prompt.

    Without `summary`, anything past MAX_HISTORY_TURNS used to just
    vanish with no trace — a fact mentioned 10 turns ago was gone forever,
    not condensed. This is the fix for that: older context degrades to a
    summary instead of disappearing outright."""
    parts = []
    if summary and summary.strip():
        parts.append(f"Summary of the conversation before that (older context):\n{summary.strip()}")
    recent = format_history(history)
    if recent:
        parts.append(f"Most recent messages:\n{recent}")
    return "\n\n".join(parts)
