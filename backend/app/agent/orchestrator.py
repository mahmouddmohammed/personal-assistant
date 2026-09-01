"""Orchestrator node + dispatch fan-out. Routing lives in the structured
output itself — no separate classification pass before it.

1. The orchestrator now sees the last few turns of the conversation, not
   just the current message in isolation. Without that, short follow-ups
   like "احجزلي الرحلة دي" ("book that one for me") right after a flight
   search had nothing to anchor "that one" to, and the model would guess —
   often landing on extract_info instead of continuing flight_booking.
2. `orchestrator_node` always emits a `RESET_WORKER_RESULTS` sentinel
   (see state.py) so a new turn never inherits worker results left over
   from a previous turn on the same conversation thread.
"""
import logging

from langgraph.types import Send

from app.agent.context import format_history
from app.agent.llm_factory import get_llm
from app.agent.state import RESET_WORKER_RESULTS, AssistantState, OrchestratorPlan

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You decompose a user's message into subtasks for these workers:
- email_classify: classify an email as Respond/Notify/Ignore
- email_write: draft an email (needs recipient + what to say)
- extract_info: pull out NEW meetings/business/medical/social items to remember for later recall
- summarize: summarize a chunk of text if user asks you to summarize
- qa: answer a question using previously stored memory
- flight_booking: search/check/choose/confirm/book flights, or continue an in-progress flight search or booking
- research_assistant: find arXiv papers on a topic

Rules:
- Accept input in English, Egyptian Arabic (Arabic script), or Egyptian Franco/Ammiya.
- One SubTask per distinct intent. A message can have zero, one, or several.
- input_text is the verbatim slice of the message relevant to that task.
- Plain chit-chat or casual greetings with no actionable intent -> empty tasks list.
- You may be given a short "Recent conversation" block for context. Use it ONLY to resolve
  what a short follow-up message refers to (pronouns like "it/that/ده/دي", or a bare date/time/
  choice) and to route continuations to the SAME worker that was already handling that topic.
  Do not turn past turns into new tasks — only decompose the CURRENT user message.
- A follow-up that picks a date/time/flight/option right after flights were discussed (e.g. "يوم
  25 اغسطس", "الرحلة التالتة", "اه احجزها") is a flight_booking continuation, never extract_info.
  extract_info is ONLY for genuinely new personal/business/medical/social facts the user wants
  remembered — not for continuing an in-progress booking or search.
- Likewise, a short "yes/confirm/ابعتها/عدلها" right after an email draft was shown is an
  email_write continuation, not a new task.

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

Follow-up routing (uses the "Recent conversation" block):
Assistant just listed CAI->DXB flights; user says "حب احجز رحلة يوم 25 اغسطس الساعة 8" ->
  flight_booking task (continue the booking), NOT extract_info
Assistant just showed an email draft; user says "تمام ابعتها" -> email_write task (continuation)
"""


def _fallback_plan(reason: str) -> OrchestratorPlan:
    """Used when the planning LLM call itself fails — better to degrade to
    a plain conversational turn (handled by the aggregator) than to 500."""
    logger.exception("orchestrator_node: planning failed, falling back to empty plan (%s)", reason)
    return OrchestratorPlan(reasoning=f"planning failed ({reason}); no tasks dispatched", tasks=[])


def orchestrator_node(state: AssistantState) -> dict:
    history_block = format_history(state.get("history"))

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history_block:
        messages.append({
            "role": "system",
            "content": f"Recent conversation (context only — see rules above):\n{history_block}",
        })
    messages.append({"role": "user", "content": state["user_input"]})

    try:
        plan = get_llm(OrchestratorPlan).invoke(messages)
    except Exception as exc:  # LLM/API hiccup should never crash the whole turn
        plan = _fallback_plan(str(exc))

    # RESET_WORKER_RESULTS must be emitted here (not in dispatch) because
    # orchestrator_node is the one node that runs exactly once at the start
    # of every turn, before any worker Send() has a chance to append.
    return {"plan": plan, "worker_results": [RESET_WORKER_RESULTS]}


def dispatch(state: AssistantState) -> list[Send]:
    tasks = state["plan"].tasks if state.get("plan") else []
    if not tasks:
        return [Send("aggregator", state)]

    history = state.get("history") or []
    return [
        Send(f"{t.task_type}_worker", {
            "task_id": t.task_id, "task_type": t.task_type, "input_text": t.input_text,
            # Continuity-sensitive workers (flight_booking, email_write) read
            # metadata["_history"]; everyone else just ignores the extra key.
            "metadata": {**t.metadata, "_history": history},
            "user_id": state["user_id"], "worker_results": [],
        })
        for t in tasks
    ]
