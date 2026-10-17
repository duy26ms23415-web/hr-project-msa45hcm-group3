"""Validated plan for one message, built from the understood catalog action(s).

`app.ai.understanding` asks Gemini which catalog action(s) a message means;
this module turns those validated calls into a ChatPlan, the internal contract
of the dispatcher (intent + target + typed slots). Nothing here reads data.
"""
import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

from app.ai.actions import BY_NAME, INTENT_ACTIONS, REPORT_INTENTS
from app.ai.understanding import ActionCall, Understanding, understand
from app.schemas.ai import AIIntentResult

Target = Literal["SELF", "EMPLOYEE", "DIRECT_REPORTS", "COMPANY", "NONE", "UNSPECIFIED"]
IntentName = Literal[
    "LEAVE_BALANCE", "ATTENDANCE_SUMMARY", "DRAFT_LEAVE", "DRAFT_FIX",
    "REPORT_ATTENDANCE", "REPORT_LEAVE", "REPORT_ATTENDANCE_FIX",
    "REPORT_LEAVE_QUEUE", "REPORT_ATTENDANCE_QUEUE", "REPORT_HEADCOUNT",
    "REPORT_PAYSLIP", "REPORT_PAYROLL", "REPORT_ANY", "ANALYZE_REPORT", "OPEN_KNOWLEDGE", "LEAVE_STATUS",
    "POLICY_QUERY", "OUT_OF_SCOPE",
]
Slots = dict[str, Annotated[StrictStr, Field(max_length=300)]]


class SubRequest(BaseModel):
    """One part of a multi-part message; dispatched only through the same checks."""
    model_config = ConfigDict(extra="forbid")
    intent: IntentName
    target: Target
    question: StrictStr | None = Field(default=None, min_length=1, max_length=300)
    employee_reference: StrictStr | None = Field(default=None, min_length=1, max_length=200)
    slots: Slots = Field(default_factory=dict)


class ChatPlan(AIIntentResult):
    target: Target
    employee_reference: StrictStr | None = Field(default=None, min_length=1, max_length=200)
    multiple_actions: StrictBool = False
    retrieval_queries: list[Annotated[StrictStr, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=3)
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    alternative_intent: IntentName | None = None
    # Clean, complete rewrite (accents, spelling, expanded abbreviations) for retrieval.
    standalone_question: StrictStr | None = Field(default=None, min_length=1, max_length=300)
    question_kind: Literal["FACT", "PERMISSION", "PROCEDURE", "CONSEQUENCE"] = "FACT"
    sub_requests: list[SubRequest] = Field(default_factory=list, max_length=3)
    follow_up: Literal["NONE", "PREVIOUS_EMPLOYEE", "PREVIOUS_PERIOD", "PREVIOUS_TOPIC", "PREVIOUS_ACTION"] = "NONE"
    # Typed values the message already states (form fields, report kind/period), as text.
    slots: Slots = Field(default_factory=dict)
    # The message is too vague for any single action; ask with server-written options.
    needs_clarification: StrictBool = False

    @model_validator(mode="after")
    def consistent_target(self):
        if self.target == "EMPLOYEE" and not self.employee_reference:
            self.target = "UNSPECIFIED"
        elif self.target != "EMPLOYEE" and self.employee_reference is not None:
            # A contradictory entity hint is a clarification, not an outage or
            # permission to substitute the authenticated user's records.
            self.target = "UNSPECIFIED"
            self.employee_reference = None
        if self.alternative_intent == self.intent:
            self.alternative_intent = None
        if len(self.sub_requests) == 1:
            self.sub_requests = []
        return self


def mask_contacts(message: str) -> str:
    message = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[email]", message)
    return re.sub(r"(?<!\w)(?:\+?84|0)(?:[ .-]?\d){9}(?!\d)", "[phone]", message)




_TARGETS = {"SELF": "SELF", "EMPLOYEE": "EMPLOYEE", "MY_TEAM": "DIRECT_REPORTS", "COMPANY": "COMPANY",
            "UNSTATED": "UNSPECIFIED", "SAME_AS_BEFORE": "UNSPECIFIED"}
_REPORT_KINDS = {"PAYSLIP": "MY_PAYSLIP"}
# Server-written choice per candidate action when a message fits several.
_CHOICE_INTENTS = {"create_report": "REPORT_ATTENDANCE", "open_approval_queue": "REPORT_LEAVE_QUEUE"}


def _first_person(message: str) -> bool:
    from app.ai.parsing.lexicon import canonical
    from app.services.ai_employee_query import explicitly_requests_self
    return explicitly_requests_self(message) or bool(re.search(
        r"\b(?:cua|cho|ve) (?:toi|minh|em|tui|to)\b|\b(?:toi|minh|em|tui) (?:da|co|di|nghi|lam)\b|\bmy\b", canonical(message)))


def _text(value) -> str | None:
    value = value.strip() if isinstance(value, str) else None
    return value or None


def _form_slots(call: ActionCall, message: str) -> dict:
    from app.services.knowledge_retrieval import normalize
    args, slots = call.args, {}
    for key in ("date", "end_date", "session", "reason", "time"):
        if _text(getattr(args, key, None)):
            slots[key] = _text(getattr(args, key))
    if call.spec.name == "draft_leave_request":
        code = "REMOTE" if args.mode == "REMOTE" else args.leave_type
        # A guess must not pick a type for the user: annual leave would silently spend the
        # balance, and unpaid leave would stand in for it (and skip the balance warning).
        # Accept them only when named; sick leave may be implied by the illness.
        named = {"ANNUAL": r"\b(?:phep nam|annual)\b", "UNPAID": r"\b(?:khong (?:huong )?luong|unpaid)\b"}
        if code in named and not re.search(named[code], normalize(message)):
            code = None
        if code:
            slots["leave_code"] = code
    elif args.event:
        slots["event"] = args.event
    return slots


def _part(call: ActionCall, message: str, previous_target: str | None) -> dict:
    """Intent, target and slots for one understood action."""
    spec, args = call.spec, call.args
    part = {"intent": spec.intent, "target": "NONE", "employee_reference": None, "slots": {}}
    follow_up = "NONE"
    subject = getattr(args, "subject", None)
    if subject:
        part["target"] = _TARGETS[subject]
        if subject == "EMPLOYEE":
            part["employee_reference"] = _text(args.employee_reference)
        elif subject == "SAME_AS_BEFORE":
            follow_up = "PREVIOUS_EMPLOYEE" if previous_target == "EMPLOYEE" else "PREVIOUS_PERIOD"
    if spec.name == "answer_policy_question":
        part["question"] = args.question.strip()[:300] or None
        if args.refers_to_previous_answer:
            follow_up = "PREVIOUS_TOPIC"
    elif spec.name in {"show_my_leave_requests", "show_my_salary"}:
        part["target"] = "SELF"
    elif spec.name == "open_approval_queue":
        part["intent"] = "REPORT_ATTENDANCE_QUEUE" if args.queue == "ATTENDANCE_FIX" else "REPORT_LEAVE_QUEUE"
        part["target"] = "DIRECT_REPORTS"
    elif spec.kind == "FORM":
        other = _text(args.for_other_person)
        part["target"], part["employee_reference"] = ("EMPLOYEE", other) if other else ("SELF", None)
        part["slots"] = _form_slots(call, message)
    elif spec.kind == "REPORT":
        # A report scope is asked with options, never inferred: SELF needs first-person wording.
        if part["target"] == "SELF" and not _first_person(message):
            part["target"] = "UNSPECIFIED"
        if spec.name == "create_report":
            part["intent"] = REPORT_INTENTS[args.report] if args.report else "REPORT_ANY"
        if args.report:
            part["slots"]["kind"] = _REPORT_KINDS.get(args.report, args.report)
        if _text(args.period):
            part["slots"]["period"] = _text(args.period)
    if spec.name in {"show_attendance", "show_my_salary"} and _text(args.period):
        part["slots"]["period"] = _text(args.period)
    return {**part, "follow_up": follow_up}


def to_plan(understanding: Understanding, message: str, previous_target: str | None = None) -> ChatPlan:
    calls = [call for call in understanding.calls if call.spec.kind != "META"] or understanding.calls[:1]
    first = calls[0]
    if first.spec.name == "clarify_request":
        intents = [_CHOICE_INTENTS.get(name) or getattr(BY_NAME.get(name), "intent", None)
                   for name in first.args.candidates]
        intents = [intent for intent in dict.fromkeys(intents) if intent and intent != "OUT_OF_SCOPE"]
        return ChatPlan(intent=intents[0] if intents else "POLICY_QUERY", target="NONE", confidence="LOW",
                        alternative_intent=intents[1] if len(intents) > 1 else None, needs_clarification=True)
    if first.spec.name == "decline_request":
        return ChatPlan(intent="OUT_OF_SCOPE", target="NONE",
                        question_kind="PERMISSION" if first.args.reason == "NOT_PERMITTED" else "FACT")
    parts = [_part(call, message, previous_target) for call in calls]
    head = parts[0]
    plan = {
        "intent": head["intent"], "target": head["target"], "employee_reference": head["employee_reference"],
        "slots": head["slots"], "follow_up": head["follow_up"], "standalone_question": head.get("question"),
    }
    if first.spec.name == "answer_policy_question":
        plan["question_kind"] = first.args.kind
        plan["retrieval_queries"] = [query.strip()[:120] for query in first.args.search_queries if query.strip()][:3]
    names = [call.spec.name for call in calls]
    # The same action twice (two employees, two forms) is several tasks, never one silent choice.
    plan["multiple_actions"] = len(set(names)) < len(names)
    if len(parts) > 1 and not plan["multiple_actions"]:
        plan["sub_requests"] = [SubRequest(intent=part["intent"], target=part["target"], question=part.get("question"),
                                           employee_reference=part["employee_reference"], slots=part["slots"])
                                for part in parts]
        if "answer_policy_question" in names:
            policy = calls[names.index("answer_policy_question")].args
            plan["retrieval_queries"] = [query.strip()[:120] for query in policy.search_queries if query.strip()][:3]
            plan["question_kind"] = policy.kind
    return ChatPlan(**plan)


async def interpret_chat_request(message: str, today: date, *, previous_intent: str | None = None,
                                 previous_target: str | None = None) -> ChatPlan:
    understanding = await understand(message, today, previous_action=INTENT_ACTIONS.get(previous_intent))
    return to_plan(understanding, message, previous_target)
