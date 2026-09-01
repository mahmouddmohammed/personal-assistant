"""Orchestrator node + dispatch fan-out. Routing lives in the structured
output itself — no separate classification pass before it."""
from langgraph.types import Send

from app.agent.llm_factory import get_llm
from app.agent.state import AssistantState, OrchestratorPlan

SYSTEM_PROMPT = """You decompose a user's message into subtasks for these workers:
- email_classify: classify an email as Respond/Notify/Ignore
- email_write: draft an email (needs recipient + what to say)
- extract_info: pull out meetings/business/medical/social items to remember
- summarize: summarize a chunk of text if user asks you to summarize
- qa: answer a question using previously stored memory
- flight_booking: search/check/book flights
- research_assistant: find arXiv papers on a topic

Rules:
- Accept input in English, Egyptian Arabic (Arabic script), or Egyptian Franco/Ammiya.
- One SubTask per distinct intent. A message can have zero, one, or several.
- input_text is the verbatim slice of the message relevant to that task.
- Plain chit-chat or casual greetings with no actionable intent -> empty tasks list.

Examples:
English:
"how's it going" -> tasks: []
"Classify this email: [text]" -> email_classify task
"Write to sara@x.com about postponing Thursday's meeting to Friday" -> email_write task
"Dentist Tuesday 3pm, also the Acme invoice of $4200 is due Friday" -> extract_info task
"Classify the landlord's email, extract the meeting he mentioned, and check flights to Dubai" -> email_classify, extract_info, flight_booking

Egyptian Arabic (العامية المصرية):
"إزيك عامل ايه" -> tasks: []
"صنفلي الميل ده: [text]" -> email_classify task
"اكتب ميل لسارة على sara@x.com أأجل فيه اجتماع الخميس لجمعة" -> email_write task
"دكتور السنان الثلاثاء الساعة ٣، وفاتورة الشركة بـ ٤٢٠٠ دولار ميعادها الجمعة" -> extract_info task
"ملخص المقالة دي إيه؟" -> summarize task
"صنف إيميل المؤجر، وطلع الميعاد اللي قاله، وشوفلي رحلات لدبي" -> email_classify, extract_info, flight_booking
"ابحثلي عن أوراق بحثية عن الذكاء الاصطناعي على arXiv" -> research_assistant task
"""


def orchestrator_node(state: AssistantState) -> dict:
    llm = get_llm(OrchestratorPlan)
    plan = llm.invoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": state["user_input"]},
    ])
    return {"plan": plan}


def dispatch(state: AssistantState) -> list[Send]:
    tasks = state["plan"].tasks if state.get("plan") else []
    if not tasks:
        return [Send("aggregator", state)]
    return [
        Send(f"{t.task_type}_worker", {
            "task_id": t.task_id, "task_type": t.task_type, "input_text": t.input_text,
            "metadata": t.metadata, "user_id": state["user_id"], "worker_results": [],
        })
        for t in tasks
    ]
