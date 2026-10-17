"""Dispatch the understood action(s) of a message through authenticated business services.

intent -> action: `interpret_chat_request` (one Gemini function call over the
action catalog) yields a ChatPlan; this module checks subject, scope and
permissions and runs the matching service. Model output never runs anything.
"""
import re

from app.ai.parsing.intent import ChatPlan, interpret_chat_request
from app.ai.providers.gemini import ProviderFailure, record
from app.schemas.ai import AIChatResponse
from app.services.ai_conversation_state import ConversationContext, load_context, remember
from app.services.ai_employee_query import (EmployeeQuery, answer_employee_query, clarify, explicitly_requests_self,
                                           mentions_employee, names_someone_else)
from app.services.ai_knowledge_tool import AIKnowledgeTool, passage_source
from app.services.ai_service import AIService
from app.services.knowledge_retrieval import normalize

READ_ONLY_PARTS = {"POLICY_QUERY", "LEAVE_BALANCE", "ATTENDANCE_SUMMARY", "LEAVE_STATUS"}
WRITE_PARTS = {"DRAFT_LEAVE", "DRAFT_FIX"}
RECORD_FOLLOW_UPS = {"PREVIOUS_PERIOD", "PREVIOUS_EMPLOYEE", "PREVIOUS_ACTION"}
# Reports whose scope the report draft collects as a missing field (never inferred).
SCOPED_REPORTS = {"REPORT_ATTENDANCE", "REPORT_LEAVE", "REPORT_ATTENDANCE_FIX", "REPORT_HEADCOUNT",
                  "REPORT_PAYROLL", "REPORT_ANY", "ANALYZE_REPORT"}

# Server-written choices for an unclear request; the model never writes these.
CHOICE_PROMPTS = {
    "LEAVE_BALANCE": "Xem số dư phép năm của tôi",
    "ATTENDANCE_SUMMARY": "Xem chấm công của tôi tháng này",
    "DRAFT_LEAVE": "Soạn đơn xin nghỉ cho tôi",
    "DRAFT_FIX": "Soạn đơn giải trình chấm công cho tôi",
    "POLICY_QUERY": "Hỏi về quy định/chính sách liên quan",
    "REPORT_ATTENDANCE": "Tạo báo cáo chấm công",
    "REPORT_LEAVE": "Tạo báo cáo nghỉ phép",
    "REPORT_LEAVE_QUEUE": "Xem đơn nghỉ đang chờ tôi duyệt",
    "REPORT_ATTENDANCE_QUEUE": "Xem đơn giải trình đang chờ tôi duyệt",
    "REPORT_PAYSLIP": "Xem phiếu lương của tôi",
    "LEAVE_STATUS": "Xem tình trạng đơn nghỉ của tôi",
    "ANALYZE_REPORT": "Phân tích/vẽ biểu đồ báo cáo",
    "OPEN_KNOWLEDGE": "Mở quản lý tài liệu",
}


# Words a bare "same thing, other period/again" follow-up may contain. Anything
# else (e.g. a name: "còn Lan thì sao?") means the subject may have changed.
_FOLLOW_UP_WORDS = set(
    "còn thì sao nào vậy à ạ nhỉ nhé hả ơi và với của tôi mình em tui tớ xem cho lại luôn nữa được không "
    "tháng tuần năm quý kỳ kì ngày hôm bữa trước sau này nay qua kia ngoái đó ấy thế cũng như giống tiếp "
    "làm kiểm tra phép số dư chấm công lương nghỉ báo cáo bảng đi hết bao nhiêu mấy đầu cuối giữa vừa rồi "
    "ko k dc đc bn trc hqua hnay fep cc what about how last previous month week year again".split()
)
# Unaccented spellings that are also common given names stay ambiguous on their own.
_NAME_LIKE = {"nam", "mai", "ha", "lan", "an", "thu", "hoa", "binh", "minh", "thang", "tuan", "quy", "ky",
              "cong", "luong", "the", "tien", "hung", "dung", "vy", "nga"}
_PLAIN_FOLLOW_UP_WORDS = {normalize(word) for word in _FOLLOW_UP_WORDS} - _NAME_LIKE
_PERIOD_NOUNS = {"thang", "tuan", "nam", "quy", "ky"}
_PERIOD_MODIFIERS = {"truoc", "sau", "nay", "qua", "ngoai", "toi", "roi", "kia"}


def _bare_follow_up(message: str) -> bool:
    """True when a follow-up names no new subject, so the previous subject may be reused."""
    words = re.findall(r"\w+", message.lower())
    for index, word in enumerate(words):
        plain = normalize(word)
        following = normalize(words[index + 1]) if index + 1 < len(words) else ""
        if word in _FOLLOW_UP_WORDS or word.isdigit() or plain in _PLAIN_FOLLOW_UP_WORDS:
            continue
        # "thang truoc", "nam ngoai", "thang 9": a period, not a person.
        if plain in _PERIOD_NOUNS and (following in _PERIOD_MODIFIERS or following.isdigit()):
            continue
        if plain in _PERIOD_MODIFIERS and index and normalize(words[index - 1]) in _PERIOD_NOUNS:
            continue
        return False
    return bool(words)


def _with_context(plan: ChatPlan, context: ConversationContext | None) -> ChatPlan:
    """Fill a follow-up's missing action/subject from server-side state (enums only)."""
    if context is None or plan.follow_up == "NONE":
        return plan
    update = {}
    if (plan.follow_up in RECORD_FOLLOW_UPS and context.last_intent
            and (plan.confidence != "HIGH" or plan.intent in {"POLICY_QUERY", "OUT_OF_SCOPE"})):
        update["intent"] = context.last_intent
        update["confidence"] = "HIGH"
    if plan.target in {"UNSPECIFIED", "NONE"} and context.last_target and plan.follow_up != "PREVIOUS_TOPIC":
        update["target"] = context.last_target
    if plan.follow_up == "PREVIOUS_TOPIC" and plan.intent != "POLICY_QUERY" and context.last_intent == "POLICY_QUERY":
        update["intent"], update["confidence"] = "POLICY_QUERY", "HIGH"
    return plan.model_copy(update=update) if update else plan

# Explicit first-person variants, so choosing one never loops back to the same question.
SELF_PROMPTS = {
    "REPORT_ATTENDANCE": "Tạo báo cáo chấm công của tôi",
    "REPORT_LEAVE": "Tạo báo cáo nghỉ phép của tôi",
    "REPORT_ATTENDANCE_FIX": "Tạo báo cáo giải trình chấm công của tôi",
}


def _choices(*intents) -> list[str]:
    return [CHOICE_PROMPTS[intent] for intent in dict.fromkeys(intents) if intent in CHOICE_PROMPTS]


def unavailable(category: str) -> AIChatResponse:
    record("interpret_chat_request", "FALLBACK_USED", category=category)
    return AIChatResponse(
        reply="Hiện tôi chưa xử lý được yêu cầu này. Bạn vui lòng thử lại sau hoặc chọn một gợi ý có sẵn. Tôi chưa thực hiện thao tác nào.",
        status="UNAVAILABLE", message_code=f"AI_INTENT_{category}",
    )


async def process_semantic_chat(db, employee_id, req, roles, owner_id, actor, today):
    # Enum-only state (previous intent/target) lets the model see that a message
    # continues the previous request; no message text or records are sent.
    context = await load_context(db, owner_id)
    try:
        plan = await interpret_chat_request(
            req.message, today, previous_intent=context.last_intent if context else None,
            previous_target=context.last_target if context else None)
    except ProviderFailure as exc:
        return unavailable(exc.category)
    return await run_plan(db, employee_id, req, roles, owner_id, actor, today, plan, context)


async def run_plan(db, employee_id, req, roles, owner_id, actor, today, plan, context):
    """Validate and execute an understood plan (shared by new messages and mid-form questions)."""
    if plan.follow_up == "NONE":
        context = None
    plan = _with_context(plan, context)
    if plan.needs_clarification:
        options = _choices(plan.intent, plan.alternative_intent) if plan.alternative_intent else []
        response = clarify("INTENT_CONFIRMATION_REQUIRED" if len(options) >= 2 else "CLARIFICATION_REQUIRED",
                           "Tôi chưa rõ bạn muốn làm gì. Vui lòng chọn một lựa chọn bên dưới hoặc nói rõ hơn; "
                           "tôi chưa tra cứu hay tạo dữ liệu.")
        return response.model_copy(update={"clarification_options": options if len(options) >= 2 else [
            CHOICE_PROMPTS[key] for key in ("LEAVE_BALANCE", "ATTENDANCE_SUMMARY", "DRAFT_LEAVE", "POLICY_QUERY")]})
    if plan.multiple_actions:
        return clarify("MULTIPLE_ACTIONS_REQUIRED", "Yêu cầu có nhiều tác vụ hoặc nhiều nhân viên. Bạn muốn thực hiện việc nào trước? Vui lòng chọn một tác vụ và một đối tượng.")
    if plan.sub_requests:
        return await _process_parts(db, employee_id, req, roles, owner_id, actor, today, plan)
    if plan.confidence == "LOW" and plan.intent not in {"OUT_OF_SCOPE"}:
        options = _choices(plan.intent, plan.alternative_intent) if plan.alternative_intent else []
        if len(options) >= 2:
            response = clarify("INTENT_CONFIRMATION_REQUIRED", "Tôi chưa chắc bạn muốn làm việc nào. Vui lòng chọn một lựa chọn bên dưới hoặc nói rõ hơn; tôi chưa tra cứu hay tạo dữ liệu.")
            return response.model_copy(update={"clarification_options": options})
    response, resolved_code = await _dispatch_plan(db, employee_id, req, roles, owner_id, actor, today, plan, context)
    if response.status == "OK" or response.draft_id:
        await remember(db, owner_id, intent=plan.intent, target=plan.target,
                       employee_code=resolved_code, section_ids=[s.section_id for s in response.sources])
    return response


async def _process_parts(db, employee_id, req, roles, owner_id, actor, today, plan):
    """Answer independent parts in one reply; each part passes its own checks."""
    parts = plan.sub_requests
    writes = [part for part in parts if part.intent in WRITE_PARTS]
    if len(writes) > 1 or any(part.intent not in READ_ONLY_PARTS | WRITE_PARTS for part in parts):
        return clarify("MULTIPLE_ACTIONS_REQUIRED", "Yêu cầu có nhiều tác vụ. Bạn muốn thực hiện việc nào trước? Vui lòng gửi từng yêu cầu.")
    replies, sources, combined, blocked = [], [], AIChatResponse(reply=""), None
    # Read-only answers first; a single draft (if any) is prepared last so its state wins.
    for part in sorted(parts, key=lambda part: part.intent in WRITE_PARTS):
        sub_plan = plan.model_copy(update={
            "intent": part.intent, "target": part.target, "sub_requests": [], "confidence": "HIGH",
            "employee_reference": part.employee_reference, "slots": part.slots,
            "standalone_question": part.question or plan.standalone_question,
            "retrieval_queries": plan.retrieval_queries if part.intent == "POLICY_QUERY" else [],
        })
        sub_req = req.model_copy(update={"message": part.question}) if part.intent == "POLICY_QUERY" and part.question else req
        response, _ = await _dispatch_plan(db, employee_id, sub_req, roles, owner_id, actor, today, sub_plan, None)
        replies.append(response.reply)
        sources.extend(source for source in response.sources if source not in sources)
        if response.action or response.draft_id:
            combined = response
        elif blocked is None and response.status in {"NEEDS_INPUT", "DENIED", "UNAVAILABLE"}:
            blocked = response
    update = {"reply": "\n\n".join(reply for reply in replies if reply)[:4000], "sources": sources[:6]}
    if blocked is not None:
        # A part that needs input or was refused must not be reported as OK.
        if not (combined.action or combined.draft_id):
            update.update(status=blocked.status, message_code=blocked.message_code)
        if not combined.clarification_options:
            update["clarification_options"] = blocked.clarification_options
    return combined.model_copy(update=update)


async def _dispatch_plan(db, employee_id, req, roles, owner_id, actor, today, plan, context):
    if plan.intent == "OUT_OF_SCOPE":
        return await _out_of_scope(db, roles, today, req, plan), None
    if plan.intent == "POLICY_QUERY":
        options = {}
        if plan.standalone_question:
            options["standalone_question"] = plan.standalone_question
        if plan.question_kind != "FACT":
            options["question_kind"] = plan.question_kind
        if plan.follow_up == "PREVIOUS_TOPIC" and context and context.last_section_ids:
            options["boost_section_ids"] = context.last_section_ids
        return await AIService._answer_knowledge(db, roles, today, req, policy_question=True,
                                                 retrieval_queries=plan.retrieval_queries, **options), None
    if plan.target == "SELF" and mentions_employee(req.message):
        return clarify("TARGET_CONFLICT", "Yêu cầu có nhắc nhân viên khác. Vui lòng xác định rõ đối tượng; tôi chưa tra cứu dữ liệu bản thân."), None
    reads_records = plan.intent in {"LEAVE_BALANCE", "ATTENDANCE_SUMMARY", "ANALYZE_REPORT"} or plan.intent.startswith("REPORT_")
    # A bare period/action follow-up keeps the previous, already validated subject.
    # PREVIOUS_EMPLOYEE refers to someone else, so it never continues SELF.
    bare = (context is not None and plan.follow_up in {"PREVIOUS_PERIOD", "PREVIOUS_ACTION"}
            and not plan.employee_reference and _bare_follow_up(req.message))
    continued_self = bare and context.last_target == "SELF"
    # SELF is the natural reading when nobody else is mentioned. It is refused only
    # when the text points at another person the model did not resolve, so a
    # misread name can never be answered with the actor's own records.
    # A SELF carried over from the previous turn is weaker evidence than the model
    # reading this message as the speaker's own, so it needs a bare follow-up.
    inherited = plan.follow_up in RECORD_FOLLOW_UPS
    unproven_self = (plan.target == "SELF" and not continued_self and not explicitly_requests_self(req.message)
                     and (inherited or names_someone_else(req.message)))
    reuse_employee = bool(context is not None and context.last_employee_code
                          and plan.target in {"EMPLOYEE", "UNSPECIFIED"} and not plan.employee_reference
                          and (plan.follow_up == "PREVIOUS_EMPLOYEE" or (bare and context.last_target == "EMPLOYEE")))
    # An inferred-but-unproven SELF may be a misread name, so it still clarifies below.
    if plan.intent in SCOPED_REPORTS and not reuse_employee and plan.target in {"UNSPECIFIED", "NONE"}:
        # Like a leave draft's missing fields: the report draft asks for the scope
        # with server-written options, and the user's answer continues that draft.
        result = await AIService._dispatch_free_intent(db, employee_id, owner_id, roles, req,
                                                      plan.intent, actor, requested_scope=None, hints=plan.slots)
        return (result if result is not None else clarify("CLARIFICATION_REQUIRED")), None
    if unproven_self and reads_records:
        response = clarify("TARGET_REQUIRED", "Bạn muốn tra cứu bản thân hay nhân viên nào? Vui lòng nêu rõ đối tượng; tôi chưa tra cứu dữ liệu.")
        options = [SELF_PROMPTS[plan.intent]] if plan.intent in SELF_PROMPTS else _choices(plan.intent)
        return response.model_copy(update={"clarification_options": options}), None
    if plan.target == "EMPLOYEE" and not plan.employee_reference and not reuse_employee:
        # Target filled from state, but the follow-up may name someone new.
        return clarify("TARGET_REQUIRED", "Bạn muốn tra cứu nhân viên nào? Vui lòng nêu mã nhân viên hoặc họ tên; tôi chưa tra cứu dữ liệu."), None
    if plan.target == "EMPLOYEE" or reuse_employee:
        if plan.intent not in {"LEAVE_BALANCE", "ATTENDANCE_SUMMARY", "REPORT_ATTENDANCE"}:
            return clarify("EMPLOYEE_ACTION_UNSUPPORTED", "Tôi hỗ trợ xem phép và báo cáo chấm công theo nhân viên trong phạm vi được cấp quyền. Tác vụ này chưa được hỗ trợ cho nhân viên khác."), None
        reference = context.last_employee_code if reuse_employee else plan.employee_reference
        # The previous employee comes from server state, not the model; it is
        # appended so the "reference must appear in the request" rule still holds,
        # and the lookup re-applies the actor's scope.
        lookup_req = req.model_copy(update={"message": f"{req.message} ({reference})"}) if reuse_employee else req
        resolved: list[str] = []
        response = await answer_employee_query(db, actor, lookup_req, today, interpretation=EmployeeQuery(
            intent="LEAVE_BALANCE" if plan.intent == "LEAVE_BALANCE" else "REPORT_ATTENDANCE",
            employee_reference=reference,
        ), resolved=resolved)
        return response, next(iter(resolved), None)
    if plan.target == "UNSPECIFIED":
        return clarify("TARGET_REQUIRED", "Bạn muốn tra cứu bản thân, nhân viên nào hay phạm vi nhóm/công ty? Vui lòng nêu rõ đối tượng; tôi chưa tra cứu dữ liệu."), None
    intent = plan.intent
    if plan.target in {"DIRECT_REPORTS", "COMPANY"}:
        intent = {"LEAVE_BALANCE": "REPORT_LEAVE", "ATTENDANCE_SUMMARY": "REPORT_ATTENDANCE"}.get(intent, intent)
    personal_intents = {"LEAVE_BALANCE", "ATTENDANCE_SUMMARY", "DRAFT_LEAVE", "DRAFT_FIX", "REPORT_PAYSLIP", "LEAVE_STATUS"}
    if intent in personal_intents and plan.target != "SELF":
        return clarify("TARGET_REQUIRED", "Tác vụ này cần xác định rõ đối tượng. Vui lòng chọn bản thân hoặc nêu nhân viên/phạm vi muốn xem."), None
    scope = plan.target if plan.target in {"SELF", "DIRECT_REPORTS", "COMPANY"} else None
    result = await AIService._dispatch_free_intent(db, employee_id, owner_id, roles, req,
                                                  intent, actor, requested_scope=scope, hints=plan.slots)
    return (result if result is not None else clarify("CLARIFICATION_REQUIRED")), None


async def _out_of_scope(db, roles, today, req, plan):
    """Refuse; for forbidden actions, cite the governing rule when one is published."""
    if plan.question_kind != "PERMISSION":
        return AIChatResponse(reply="Tôi hỗ trợ nghiệp vụ HR và chính sách lao động trong phạm vi được cấp quyền.", answer_mode="OUT_OF_SCOPE")
    question = plan.standalone_question or req.message
    rules = await AIKnowledgeTool.search(db, roles, today, [question], limit=2,
                                         rule_types=("PROHIBITION", "OBLIGATION"))
    reply = ("Tôi không thể thực hiện thao tác này: trợ lý chỉ tra cứu và chuẩn bị bản nháp; mọi thay đổi dữ liệu "
             "phải đi qua chức năng nghiệp vụ và người có thẩm quyền.")
    if rules:
        reply += " Quy định liên quan được trích ở nguồn bên dưới."
    return AIChatResponse(reply=reply, sources=[passage_source(rule) for rule in rules],
                          answer_mode="OUT_OF_SCOPE", message_code="ACTION_NOT_PERMITTED")


# ---------------------------------------------------------------------------
# Lock-in: while a form (leave, attendance fix, report) is open, every message
# is first read as an answer to it. Short answers that deterministically fill
# the asked field skip the model; anything else is understood with the open
# form as context, so "chiều nhé", "à mà tôi còn mấy ngày phép?" and "thôi
# hủy" each go to the right place.
# ---------------------------------------------------------------------------
_CANCEL_WORDS = {"huy", "huy ban nhap", "bo qua", "dung lai"}
_REPORT_LABELS = {"ban than", "nhan vien truc tiep", "toan cong ty"}
_SCOPES = {"SELF": "SELF", "MY_TEAM": "DIRECT_REPORTS", "COMPANY": "COMPANY"}
_FAST_PATH_WORDS = 6


def keep_draft(response: AIChatResponse, draft) -> AIChatResponse:
    """A side answer never consumes or drops the open form.

    UNAVAILABLE and DENIED are kept so a provider failure or a refusal is never reported as a normal prompt."""
    status = response.status if response.status in {"UNAVAILABLE", "DENIED"} else "NEEDS_INPUT"
    return response.model_copy(update={"draft_id": draft.draft_id, "draft_revision": draft.revision,
                                       "missing_fields": draft.missing_fields, "status": status})


def _switch_required(draft) -> AIChatResponse:
    return keep_draft(AIChatResponse(
        reply="Bạn đang có một bản nháp chưa hoàn tất. Hãy tiếp tục trả lời trường còn thiếu, hoặc gửi ‘hủy’ trước khi bắt đầu tác vụ mới.",
        message_code="DRAFT_SWITCH_CONFIRMATION_REQUIRED"), draft)


def _runs_a_report(plan: ChatPlan) -> bool:
    parts = plan.sub_requests or [plan]
    return any(part.intent.startswith("REPORT_") or part.intent == "ANALYZE_REPORT"
               or part.target in {"DIRECT_REPORTS", "COMPANY"} for part in parts)


def _fills_asked_field(draft, message: str, today) -> bool:
    """A short reply that the deterministic parser maps onto the asked field."""
    from app.services.ai_report_interpreter import report_answers
    from app.services.ai_service import draft_reason_match
    if not draft.missing_fields or len(message.split()) > _FAST_PATH_WORDS:
        return False
    asked = draft.missing_fields[0]
    if draft.command == "DRAFT_REPORT":
        return (normalize(message) in _REPORT_LABELS
                or asked in report_answers(message, today, draft.typed_params, draft.missing_fields))
    if asked == "reason":
        return draft_reason_match(message) is not None
    if asked == "leave_type_id":
        return AIService._requested_leave_code(message, True) is not None
    return asked in AIService._draft_answers(draft.command, message, draft.missing_fields)


async def process_semantic_draft_turn(db, employee_id, req, roles, owner_id, actor, today):
    from app.ai.actions import FORM_ACTIONS
    from app.ai.parsing.intent import _REPORT_KINDS, _first_person, _form_slots, to_plan
    from app.ai.understanding import Understanding, understand
    from app.services.ai_draft_service import AIDraftService
    from fastapi import HTTPException

    draft = await AIDraftService.get_draft(db, req.draft_id, owner_id)
    if req.draft_revision is not None and draft.revision != req.draft_revision:
        raise HTTPException(409, "AI_DRAFT_REVISION_CONFLICT")

    async def fill(message, hints=None, inputs=req.inputs):
        return await AIService._continue_draft(db, owner_id, req.draft_id, message, employee_id, req.draft_revision,
                                               inputs, actor, today, hints=hints)

    if (req.inputs or normalize(req.message) in _CANCEL_WORDS or draft.status != "COLLECTING"
            or _fills_asked_field(draft, req.message, today)):
        return await fill(req.message)
    form_action = FORM_ACTIONS[draft.command]
    try:
        understanding = await understand(req.message, today, open_form=form_action,
                                         waiting_for=draft.missing_fields[0] if draft.missing_fields else None)
    except ProviderFailure as exc:
        return keep_draft(unavailable(exc.category), draft)
    names = understanding.names
    if "cancel_current_form" in names:
        return await fill("hủy")
    same = [call for call in understanding.calls if call.spec.name == form_action]
    others = [call for call in understanding.calls if call.spec.name not in {form_action, "cancel_current_form"}]
    if any(call.spec.kind in {"FORM", "REPORT"} for call in others):
        return _switch_required(draft)
    side = [call for call in others if call.spec.kind != "META"]
    if side:
        # A question asked mid-form is answered on its own; the form stays open.
        plan = to_plan(Understanding(side), req.message)
        if _runs_a_report(plan):
            # Team/company figures and payslips are report runs: one task at a time, so ask first
            # instead of creating a report draft or run next to the open form.
            return _switch_required(draft)
        side_req = req.model_copy(update={"draft_id": None, "draft_revision": None, "inputs": None})
        response = await run_plan(db, employee_id, side_req, roles, owner_id, actor, today, plan, None)
        if response.draft_id and response.draft_id != draft.draft_id:
            # Safety net: a lookup that still opened a draft of its own is dropped, not orphaned.
            try:
                await AIDraftService.cancel_draft(db, response.draft_id, owner_id)
            except HTTPException:
                pass  # Already not COLLECTING: nothing is left open.
            return _switch_required(draft)
        return keep_draft(response, draft)
    if not same:
        if any(call.spec.name == "decline_request" for call in others):
            return keep_draft(AIChatResponse(reply="Tôi hỗ trợ nghiệp vụ HR và chính sách lao động trong phạm vi được cấp quyền.",
                                              answer_mode="OUT_OF_SCOPE"), draft)
        return await fill(req.message)  # Unclear: the form explains what it still needs.
    call = same[0]
    if draft.command == "DRAFT_REPORT":
        inputs = dict(req.inputs or {})
        if call.args.report:
            inputs.setdefault("kind", _REPORT_KINDS.get(call.args.report, call.args.report))
        # The model's SELF needs first-person wording, as for a new report (intent._first_person).
        if call.args.subject in _SCOPES and (call.args.subject != "SELF" or _first_person(req.message)):
            inputs.setdefault("scope", _SCOPES[call.args.subject])
        return await fill(req.message, inputs=inputs or None)
    hints = _form_slots(call, req.message)
    if draft.missing_fields and draft.missing_fields[0] == "reason" and "reason" not in hints:
        # Changed other fields without a reason: the text is not the reason.
        return await fill("" if hints else req.message, hints)
    return await fill(req.message, hints)
