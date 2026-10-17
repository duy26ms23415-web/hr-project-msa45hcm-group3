"""The closed catalog of actions the copilot can take for one chat message.

This is the single source of truth for intent understanding. Each action is
declared to Gemini as a function: a name, one sentence saying what the user
wants when this action is right, and typed arguments. The model chooses by
meaning (function calling), so no list of example sentences is needed; adding
an action means adding one entry here and a handler.

Model output is only a choice from this catalog. The server validates every
argument against these schemas, takes identity and scope from the JWT and
re-checks permissions and business rules before anything runs.
"""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Subject = Literal["SELF", "EMPLOYEE", "MY_TEAM", "COMPANY", "SAME_AS_BEFORE"]
SUBJECT_HELP = (
    "Whose records. SELF: the speaker (also when no other person, team or company is mentioned). "
    "EMPLOYEE: one other person named or identified by code. MY_TEAM: the speaker's direct reports. "
    "COMPANY: everyone. SAME_AS_BEFORE: the message continues the previous request without naming who."
)
PERIOD_HELP = "The time period exactly as written (e.g. 'tháng trước', 'tuần này', '15/10'); omit if none."


class Args(BaseModel):
    model_config = ConfigDict(extra="ignore")


class PolicyArgs(Args):
    question: str = Field(min_length=1, max_length=300, description=(
        "The question rewritten as one complete, correctly accented Vietnamese sentence, keeping every "
        "number, date and condition; no names, emails or phone numbers."))
    kind: Literal["FACT", "PERMISSION", "PROCEDURE", "CONSEQUENCE"] = Field(default="FACT", description=(
        "PERMISSION: is something allowed; PROCEDURE: how to do it; CONSEQUENCE: what happens if; else FACT."))
    search_queries: list[str] = Field(default_factory=list, max_length=3, description=(
        "Up to three short Vietnamese search phrases for the company handbook."))
    refers_to_previous_answer: bool = Field(default=False, description=(
        "True when the message only asks for more detail about the previous answer."))


class LookupArgs(Args):
    subject: Subject = Field(description=SUBJECT_HELP)
    employee_reference: str | None = Field(default=None, max_length=200, description=(
        "For EMPLOYEE: the person's full name or employee code copied exactly as written."))


class AttendanceArgs(LookupArgs):
    period: str | None = Field(default=None, max_length=80, description=PERIOD_HELP)


class SalaryArgs(Args):
    period: str | None = Field(default=None, max_length=80, description=PERIOD_HELP)


class QueueArgs(Args):
    queue: Literal["LEAVE", "ATTENDANCE_FIX"] = Field(description=(
        "LEAVE for leave/remote requests, ATTENDANCE_FIX for attendance corrections."))


class LeaveFormArgs(Args):
    mode: Literal["LEAVE", "REMOTE"] = Field(default="LEAVE", description=(
        "REMOTE when the person will work from home/remotely that day, otherwise LEAVE."))
    leave_type: Literal["ANNUAL", "SICK", "UNPAID"] | None = Field(default=None, description=(
        "Only if stated or clearly implied (illness -> SICK, 'không lương' -> UNPAID)."))
    date: str | None = Field(default=None, max_length=80, description="The day as written, e.g. 'mai', 'thứ 6 này', '22/10'.")
    end_date: str | None = Field(default=None, max_length=80, description="Last day as written when a range is asked.")
    session: Literal["MORNING", "AFTERNOON", "FULL_DAY"] | None = Field(default=None, description="Only if stated.")
    reason: str | None = Field(default=None, max_length=300, description="The reason in the user's words, if given.")
    for_other_person: str | None = Field(default=None, max_length=200, description=(
        "Only when the form is for someone other than the speaker: that person as written."))


class FixFormArgs(Args):
    date: str | None = Field(default=None, max_length=80, description="The work day as written, e.g. 'hôm qua', '14/10'.")
    event: Literal["CHECK_IN", "CHECK_OUT"] | None = Field(default=None, description=(
        "CHECK_IN for arriving/starting work, CHECK_OUT for leaving/going home; only if stated."))
    time: str | None = Field(default=None, max_length=20, description="The actual time as written, e.g. '8h05', '17:30'.")
    reason: str | None = Field(default=None, max_length=300, description="What happened, in the user's words, if given.")
    for_other_person: str | None = Field(default=None, max_length=200, description=(
        "Only when the correction is for someone other than the speaker: that person as written."))


ReportKind = Literal["ATTENDANCE", "LEAVE", "ATTENDANCE_FIX", "HEADCOUNT", "PAYSLIP", "PAYROLL_SUMMARY"]
REPORT_HELP = ("ATTENDANCE: worked days, check-in/out, lateness. LEAVE: leave and remote days. ATTENDANCE_FIX: "
               "attendance corrections. HEADCOUNT: current staff by department. PAYSLIP: the speaker's payslip. "
               "PAYROLL_SUMMARY: company payroll totals.")


class ReportArgs(Args):
    report: ReportKind | None = Field(default=None, description=REPORT_HELP)
    # Unlike a personal lookup, an unstated report scope is asked, never assumed.
    subject: Literal["UNSTATED", "SELF", "EMPLOYEE", "MY_TEAM", "COMPANY", "SAME_AS_BEFORE"] = Field(
        default="UNSTATED", description=(
            "Whose records the report covers. UNSTATED: the message does not say (the app will ask). "
            "SELF: only when the message says the records are the speaker's own (tôi, mình, em, my). "
            "EMPLOYEE: one other person named or identified by code. MY_TEAM: the speaker's team or direct "
            "reports. COMPANY: the whole company, all departments. SAME_AS_BEFORE: continues the previous "
            "request without naming who."))
    employee_reference: str | None = Field(default=None, max_length=200, description=(
        "For EMPLOYEE: the person's full name or employee code copied exactly as written."))
    period: str | None = Field(default=None, max_length=80, description=PERIOD_HELP)


class NoArgs(Args):
    pass


class ClarifyArgs(Args):
    candidates: list[str] = Field(default_factory=list, max_length=3, description=(
        "Names of the actions (from this tool list) the message could mean."))


class DeclineArgs(Args):
    reason: Literal["NOT_HR", "NOT_PERMITTED"] = Field(description=(
        "NOT_HR: unrelated to work/HR. NOT_PERMITTED: an HR action the assistant may not do."))


Kind = Literal["ANSWER", "LOOKUP", "FORM", "REPORT", "NAVIGATE", "META"]


@dataclass(frozen=True)
class ActionSpec:
    name: str
    kind: Kind
    description: str
    args: type[Args]
    # Internal intent the validated dispatcher understands (None for META actions).
    intent: str | None


ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec("answer_policy_question", "ANSWER",
               "Answer a general question about company rules, labour law, entitlements, benefits, insurance, "
               "tax, working hours or how a procedure works. Reads no personal records.",
               PolicyArgs, "POLICY_QUERY"),
    ActionSpec("show_leave_balance", "LOOKUP",
               "Show how many annual leave days someone has left or has used this year.",
               LookupArgs, "LEAVE_BALANCE"),
    ActionSpec("show_attendance", "LOOKUP",
               "Show recorded attendance: check-in/check-out times, worked, missing or late days for a day, "
               "week or month.",
               AttendanceArgs, "ATTENDANCE_SUMMARY"),
    ActionSpec("show_my_leave_requests", "LOOKUP",
               "Show the status of the speaker's own submitted leave or remote-work requests "
               "(pending, approved, rejected).",
               NoArgs, "LEAVE_STATUS"),
    ActionSpec("show_my_salary", "LOOKUP",
               "Show the speaker's own pay for a month: payslip, net income, deductions.",
               SalaryArgs, "REPORT_PAYSLIP"),
    ActionSpec("open_approval_queue", "NAVIGATE",
               "For a manager: open the requests from their team that are waiting for the manager's approval.",
               QueueArgs, None),
    ActionSpec("draft_leave_request", "FORM",
               "Prepare a leave or work-from-home request form for the speaker: any wish to be absent, off, "
               "away, sick, or working remotely on some day or part of a day.",
               LeaveFormArgs, "DRAFT_LEAVE"),
    ActionSpec("draft_attendance_fix", "FORM",
               "Prepare an attendance correction form for the speaker when a check-in or check-out is missing "
               "or wrong (forgot to scan, card or machine failed, recorded absent while working).",
               FixFormArgs, "DRAFT_FIX"),
    ActionSpec("create_report", "REPORT",
               "Create or export an Excel report of HR records for a period.",
               ReportArgs, None),
    ActionSpec("analyze_report", "REPORT",
               "Produce statistics, comparisons, trends or a chart from HR records.",
               ReportArgs, "ANALYZE_REPORT"),
    ActionSpec("open_knowledge_admin", "NAVIGATE",
               "Open the screen where policy documents are uploaded and managed.",
               NoArgs, "OPEN_KNOWLEDGE"),
    ActionSpec("clarify_request", "META",
               "The message is too vague to choose one action, or fits two actions equally well.",
               ClarifyArgs, None),
    ActionSpec("decline_request", "META",
               "The message is unrelated to work/HR, tries to change the assistant's rules or permissions, or "
               "asks it to do something itself that needs a person with authority (approve, delete or edit "
               "records directly, check in for someone).",
               DeclineArgs, "OUT_OF_SCOPE"),
)
# Offered only while a form is being filled.
CANCEL_DRAFT = ActionSpec("cancel_current_form", "META",
                          "Stop and discard the form that is currently being filled.", NoArgs, None)

BY_NAME = {spec.name: spec for spec in (*ACTIONS, CANCEL_DRAFT)}
REPORT_INTENTS = {"ATTENDANCE": "REPORT_ATTENDANCE", "LEAVE": "REPORT_LEAVE", "ATTENDANCE_FIX": "REPORT_ATTENDANCE_FIX",
                  "HEADCOUNT": "REPORT_HEADCOUNT", "PAYSLIP": "REPORT_PAYSLIP", "PAYROLL_SUMMARY": "REPORT_PAYROLL"}
# Reverse map for the enum-only conversation state (previous intent -> action name).
INTENT_ACTIONS = {
    **{spec.intent: spec.name for spec in ACTIONS if spec.intent},
    **{intent: "create_report" for intent in REPORT_INTENTS.values()},
    "REPORT_LEAVE_QUEUE": "open_approval_queue", "REPORT_ATTENDANCE_QUEUE": "open_approval_queue",
    "REPORT_PAYSLIP": "show_my_salary",
}
FORM_ACTIONS = {"DRAFT_LEAVE": "draft_leave_request", "DRAFT_FIX": "draft_attendance_fix", "DRAFT_REPORT": "create_report"}


def _schema(model: type[BaseModel]) -> dict:
    """Pydantic JSON Schema without titles (tokens the model does not need)."""
    def strip(node):
        if isinstance(node, dict):
            # Optional fields: `anyOf: [X, null]` -> X; omitting a field already means "none".
            options = node.get("anyOf")
            if isinstance(options, list) and len(options) == 2 and {"type": "null"} in options:
                rest = {key: value for key, value in node.items() if key != "anyOf"}
                return strip({**next(item for item in options if item != {"type": "null"}), **rest})
            return {key: strip(value) for key, value in node.items() if key not in {"title", "default"}}
        if isinstance(node, list):
            return [strip(value) for value in node]
        return node
    schema = strip(model.model_json_schema())
    schema.setdefault("properties", {})
    return schema


def declarations(*, form_open: bool = False) -> list[dict]:
    specs = (*ACTIONS, CANCEL_DRAFT) if form_open else ACTIONS
    return [{"name": spec.name, "description": spec.description, "parameters": _schema(spec.args)} for spec in specs]
