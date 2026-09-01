"""Merges WorkerResult[] into exactly one final_response.
Single result -> template it directly. 2+ -> one LLM call weaves them
together. Empty -> plain conversational reply. Any needs_human_input
result surfaces as a pending item instead of being silently dropped."""
from app.agent.llm_factory import get_llm, to_text
from app.agent.state import AssistantState


def aggregator_node(state: AssistantState) -> dict:
    results = state.get("worker_results") or []

    if not results:
        reply = get_llm(temperature=0.5).invoke([
            {"role": "system", "content": "You are a helpful personal assistant. Reply conversationally."},
            {"role": "user", "content": state["user_input"]},
        ])
        return {"final_response": to_text(reply.content)}

    pending = [r for r in results if r.status == "needs_human_input"]
    done = [r for r in results if r.status != "needs_human_input"]

    parts = []
    if len(done) == 1:
        parts.append(done[0].summary)
    elif done:
        joined = "\n".join(f"- [{r.task_type}] {r.summary}" for r in done)
        composed = get_llm(temperature=0.3).invoke([
            {"role": "system", "content": "Weave these task results into one short, coherent reply to the "
                                           "user, one section per task, in the order given. Don't repeat "
                                           "internal labels like [task_type]."},
            {"role": "user", "content": joined},
        ])
        parts.append(to_text(composed.content))

    if pending:
        parts.append("Still waiting on your input for: " + ", ".join(r.task_type for r in pending) + ".")

    return {"final_response": "\n\n".join(parts)}
