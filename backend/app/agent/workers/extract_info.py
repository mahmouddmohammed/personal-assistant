"""Worker 3 — Router + Parallelization. One LLM call classifies+extracts
items, then a second, stricter per-category pass fans out via Send.
persist_and_embed is the only function allowed to write to memory."""
import operator
from enum import Enum
from typing import Annotated, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from app.agent.llm_factory import get_llm
from app.agent.memory.vector_store import persist_and_embed
from app.agent.state import WorkerResult


class ItemCategory(str, Enum):
    MEETING = "meeting"
    BUSINESS = "business"
    MEDICAL = "medical"
    SOCIAL = "social"


class RawExtractedItem(BaseModel):
    category: ItemCategory
    title: str
    date: Optional[str] = None
    time: Optional[str] = None
    people: list[str] = Field(default_factory=list)
    raw_snippet: str


class ExtractionRouterOutput(BaseModel):
    items: list[RawExtractedItem]


class MeetingItem(BaseModel):
    title: str; date: Optional[str]; time: Optional[str]; attendees: list[str]; location: Optional[str]


class BusinessItem(BaseModel):
    title: str; counterparty: Optional[str]; amount: Optional[float]; currency: Optional[str]; due_date: Optional[str]


class MedicalItem(BaseModel):
    title: str; provider: Optional[str]; date: Optional[str]; symptom_or_reason: Optional[str]; follow_up_needed: bool = False


class SocialItem(BaseModel):
    title: str; people: list[str]; date: Optional[str]; location: Optional[str]


_SCHEMA_BY_CATEGORY = {
    ItemCategory.MEETING: MeetingItem, ItemCategory.BUSINESS: BusinessItem,
    ItemCategory.MEDICAL: MedicalItem, ItemCategory.SOCIAL: SocialItem,
}


class ExtractInfoState(TypedDict):
    task_id: str
    task_type: str
    input_text: str
    metadata: dict
    user_id: str
    worker_results: Annotated[list[WorkerResult], operator.add]
    item: Optional[dict]                                   # set only on refine_* branches
    refined_items: Annotated[list[dict], operator.add]


def extract_and_classify(state: ExtractInfoState) -> dict:
    result: ExtractionRouterOutput = get_llm(ExtractionRouterOutput).invoke(
        f"Extract every meeting/business/medical/social item from this text(Egyptian Arabic / English), tagging each with its "
        f"category:\n\n{state['input_text']}"
    )
    return {"_items": result.items}


def dispatch_refine(state: ExtractInfoState) -> list[Send]:
    items = state.get("_items") or []
    if not items:
        return [Send("extract_join", {**state, "refined_items": []})]
    node_by_cat = {ItemCategory.MEETING: "refine_meeting", ItemCategory.BUSINESS: "refine_business",
                   ItemCategory.MEDICAL: "refine_medical", ItemCategory.SOCIAL: "refine_social"}
    return [Send(node_by_cat[i.category], {**state, "item": i.model_dump()}) for i in items]


def _make_refiner(category: ItemCategory):
    schema = _SCHEMA_BY_CATEGORY[category]

    def refine(state: ExtractInfoState) -> dict:
        item = state["item"]
        refined = get_llm(schema).invoke(
            f"Extract precise {category.value} fields from: {item['raw_snippet']}"
        )
        return {"refined_items": [{"category": category.value, **refined.model_dump()}]}

    return refine


refine_meeting = _make_refiner(ItemCategory.MEETING)
refine_business = _make_refiner(ItemCategory.BUSINESS)
refine_medical = _make_refiner(ItemCategory.MEDICAL)
refine_social = _make_refiner(ItemCategory.SOCIAL)


def extract_join(state: ExtractInfoState) -> dict:
    items = state.get("refined_items") or []
    for item in items:
        persist_and_embed(state["user_id"], f"extracted_{item['category']}", state["task_id"], str(item))
    summary = f"Extracted {len(items)} item(s): " + ", ".join(i["title"] for i in items) if items else "No items found."
    wr = WorkerResult(task_id=state["task_id"], task_type="extract_info", status="completed",
                       summary=summary, data={"items": items})
    return {"worker_results": [wr]}


def build_extract_info_subgraph():
    g = StateGraph(ExtractInfoState)
    g.add_node("extract_and_classify", extract_and_classify)
    for name, fn in [("refine_meeting", refine_meeting), ("refine_business", refine_business),
                      ("refine_medical", refine_medical), ("refine_social", refine_social)]:
        g.add_node(name, fn)
        g.add_edge(name, "extract_join")
    g.add_node("extract_join", extract_join)
    g.add_edge(START, "extract_and_classify")
    g.add_conditional_edges("extract_and_classify", dispatch_refine,
                             ["refine_meeting", "refine_business", "refine_medical", "refine_social", "extract_join"])
    g.add_edge("extract_join", END)
    return g.compile()


extract_info_worker = build_extract_info_subgraph()
