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

WORKER_NODES = {
    "email_classify_worker": email_classify_worker,
    "email_write_worker": email_write_worker,          # compiled subgraph
    "extract_info_worker": extract_info_worker,         # compiled subgraph
    "summarize_worker": summarize_worker,
    "qa_worker": qa_worker,
    "flight_booking_worker": flight_booking_worker,     # compiled subgraph
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
