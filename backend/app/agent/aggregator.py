"""Merges WorkerResult[] into exactly one final_response.
Single result -> template it directly. 2+ -> one LLM call weaves them
together. Empty -> plain conversational reply. Any needs_human_input
result surfaces as a pending item instead of being silently dropped.

Note: `results` here is guaranteed scoped to the CURRENT turn only — the
orchestrator resets worker_results at the start of every turn (see
state.py / orchestrator.py), so this node no longer has to worry about
results left over from earlier turns bleeding into the reply."""
import logging

from app.agent.context import format_history
from app.agent.llm_factory import get_llm, to_text
from app.agent.state import AssistantState

logger = logging.getLogger(__name__)


def aggregator_node(state: AssistantState) -> dict:
    results = state.get("worker_results") or []

    if not results:
        history_block = format_history(state.get("history"))
        messages = [{"role": "system", "content": "You are a helpful personal assistant. Reply conversationally, "
                                                    "in the same language/dialect the user is using."}]
        if history_block:
            messages.append({"role": "system", "content": f"Recent conversation:\n{history_block}"})
        messages.append({"role": "user", "content": state["user_input"]})
        try:
            reply = get_llm(temperature=0.5).invoke(messages)
            return {"final_response": to_text(reply.content)}
        except Exception:
            logger.exception("aggregator_node: conversational LLM call failed")
            return {"final_response": "معلش، حصل عطل بسيط. جرب تاني كمان شوية."}

    pending = [r for r in results if r.status == "needs_human_input"]
    done = [r for r in results if r.status != "needs_human_input"]

    parts = []
    if len(done) == 1:
        parts.append(done[0].summary)
    elif done:
        joined = "\n".join(f"- [{r.task_type}] {r.summary}" for r in done)
        try:
            composed = get_llm(temperature=0.3).invoke([
                {"role": "system", "content": "Weave these task results into one short, coherent reply to the "
                                               "user, one section per task, in the order given. Don't repeat "
                                               "internal labels like [task_type]."},
                {"role": "user", "content": joined},
            ])
            parts.append(to_text(composed.content))
        except Exception:
            logger.exception("aggregator_node: compose LLM call failed, falling back to raw summaries")
            parts.append("\n\n".join(r.summary for r in done))

    if pending:
        parts.append("Still waiting on your input for: " + ", ".join(r.task_type for r in pending) + ".")

    return {"final_response": "\n\n".join(parts)}
