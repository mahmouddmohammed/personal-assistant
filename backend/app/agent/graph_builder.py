"""Wires all 7 workers into the top-level orchestrator -> Send -> workers ->
aggregator graph. A checkpointer is mandatory: email_write and
flight_booking both use interrupt(), which requires one to pause/resume.

WORKER_NODES acts as a small Strategy registry: task_type -> worker
callable/subgraph, so adding an 8th worker later means adding one entry
here, not touching the graph wiring logic.
"""
from langgraph.graph import StateGraph, START, END

from app.agent.aggregator import aggregator_node
from app.agent.orchestrator import orchestrator_node, dispatch
from app.agent.state import AssistantState
from app.agent.workers import (
    email_classify_worker,
    email_write_worker,
    extract_info_worker,
    summarize_worker,
    qa_worker,
    flight_booking_worker,
    research_worker,
)


def _worker_results_only(subgraph):
    """Adapter for the 3 workers built as their own compiled subgraph
    (email_write, extract_info, flight_booking). Their internal state
    schemas share field names with the parent AssistantState (user_id,
    task_id, input_text, metadata, ...) because Send() payloads are built
    from AssistantState in the first place. Registering such a subgraph
    directly as a node (`add_node(name, subgraph)`) makes LangGraph treat
    its ENTIRE final state as that node's output — so every one of those
    shared-but-unchanged fields, `user_id` in particular, gets "written"
    back to the parent graph too. `user_id` has no reducer (a plain,
    single-writer-per-step channel), so the moment two of these three
    subgraph-workers complete within the same Send() fan-out step — the
    normal case, that's the whole point of the fan-out — LangGraph raises
    `InvalidUpdateError: At key 'user_id': Can receive only one value per
    step`.

    Invoking the subgraph through a plain wrapper node instead, and
    returning only the keys the parent graph actually tracks, keeps every
    other field a purely internal detail of that subgraph. Passing `config`
    through preserves checkpointing/interrupt behavior exactly as if the
    subgraph were still registered directly.
    """
    def _node(state, config=None):
        result = subgraph.invoke(state, config)
        out = {"worker_results": result.get("worker_results", [])}
        if "active_booking" in result:
            out["active_booking"] = result["active_booking"]
        return out
    return _node


WORKER_NODES = {
    "email_classify_worker": email_classify_worker,
    "email_write_worker": _worker_results_only(email_write_worker),
    "extract_info_worker": _worker_results_only(extract_info_worker),
    "summarize_worker": summarize_worker,
    "qa_worker": qa_worker,
    "flight_booking_worker": _worker_results_only(flight_booking_worker),
    "research_assistant_worker": research_worker,
}


def build_graph(checkpointer):
    g = StateGraph(AssistantState)
    g.add_node("orchestrator", orchestrator_node)
    for name, fn in WORKER_NODES.items():
        g.add_node(name, fn)
    g.add_node("aggregator", aggregator_node)

    g.add_edge(START, "orchestrator")
    g.add_conditional_edges("orchestrator", dispatch, list(WORKER_NODES) + ["aggregator"])
    for name in WORKER_NODES:
        g.add_edge(name, "aggregator")
    g.add_edge("aggregator", END)

    return g.compile(checkpointer=checkpointer)