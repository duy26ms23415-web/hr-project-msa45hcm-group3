"""Intent -> action: the catalog, the understood calls -> validated plan, and form lock-in."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai import semantic_router as router
from app.ai import understanding as understanding_module
from app.ai.actions import ACTIONS, BY_NAME, FORM_ACTIONS, INTENT_ACTIONS, declarations
from app.ai.parsing.intent import to_plan
from app.ai.providers.gemini import ProviderFailure
from app.ai.understanding import ActionCall, Understanding, understand
from app.core.config import settings
from app.schemas.ai import AIChatRequest, AIChatResponse
from app.services.ai_draft_service import AIDraftService
from app.services.ai_service import AIService, draft_hints, parse_clock

TODAY = date(2026, 10, 15)  # Thursday
D = "00000000-0000-0000-0000-000000000001"


def call(name, **args):
    spec = BY_NAME[name]
    return ActionCall(spec, spec.args.model_validate(args))


def plan_of(*calls, message="x", previous_target=None):
    return to_plan(Understanding(list(calls)), message, previous_target)


def test_every_action_is_declared_with_a_purpose_and_an_object_schema():
    declared = declarations()
    assert [item["name"] for item in declared] == [spec.name for spec in ACTIONS]
    for item in declared:
        assert item["description"] and item["parameters"]["type"] == "object"
        assert "title" not in str(item["parameters"]) and "anyOf" not in str(item["parameters"])
    assert "cancel_current_form" in {item["name"] for item in declarations(form_open=True)}
    # Every open form can be continued through its own action.
    assert set(FORM_ACTIONS.values()) <= set(BY_NAME)
    assert all(name in BY_NAME for name in INTENT_ACTIONS.values())


@pytest.mark.asyncio
async def test_understand_keeps_only_catalog_actions_with_valid_arguments(monkeypatch):
    monkeypatch.setattr(understanding_module, "generate_function_calls", AsyncMock(return_value=[
        ("run_sql", {"query": "select 1"}),
        ("show_leave_balance", {"subject": "EVERYONE"}),
        ("cancel_current_form", {}),  # Not offered without an open form.
        ("show_attendance", {"subject": "SELF", "period": "tuần này"}),
    ]))
    result = await understand("phép với công tuần này", TODAY)
    assert result.names == ["show_attendance"]


@pytest.mark.asyncio
async def test_understand_with_nothing_valid_is_a_provider_failure_not_a_guess(monkeypatch):
    monkeypatch.setattr(understanding_module, "generate_function_calls", AsyncMock(return_value=[("run_sql", {})]))
    with pytest.raises(ProviderFailure):
        await understand("abc", TODAY)


def test_lookup_subjects_map_to_targets():
    assert plan_of(call("show_leave_balance", subject="SELF")).target == "SELF"
    named = plan_of(call("show_leave_balance", subject="EMPLOYEE", employee_reference="EMP003"))
    assert (named.target, named.employee_reference) == ("EMPLOYEE", "EMP003")
    # A named subject without a name is a clarification, never the speaker.
    assert plan_of(call("show_leave_balance", subject="EMPLOYEE")).target == "UNSPECIFIED"
    team = plan_of(call("create_report", report="LEAVE", subject="MY_TEAM", period="tháng trước"))
    assert (team.intent, team.target, team.slots) == ("REPORT_LEAVE", "DIRECT_REPORTS", {"kind": "LEAVE", "period": "tháng trước"})
    assert plan_of(call("create_report", report="HEADCOUNT")).target == "UNSPECIFIED"
    assert plan_of(call("create_report")).intent == "REPORT_ANY"


def test_same_as_before_follows_the_previous_subject_kind():
    assert plan_of(call("show_attendance", subject="SAME_AS_BEFORE"), previous_target="EMPLOYEE").follow_up == "PREVIOUS_EMPLOYEE"
    period = plan_of(call("show_attendance", subject="SAME_AS_BEFORE"), previous_target="SELF")
    assert (period.target, period.follow_up) == ("UNSPECIFIED", "PREVIOUS_PERIOD")


def test_form_slots_are_text_and_annual_leave_is_never_guessed():
    leave = plan_of(call("draft_leave_request", leave_type="ANNUAL", date="mai", session="AFTERNOON"),
                    message="cho em xin off chiều mai")
    assert leave.intent == "DRAFT_LEAVE" and leave.target == "SELF"
    assert leave.slots == {"date": "mai", "session": "AFTERNOON"}
    named = plan_of(call("draft_leave_request", leave_type="ANNUAL"), message="xin nghỉ phép năm mai")
    assert named.slots["leave_code"] == "ANNUAL"
    remote = plan_of(call("draft_leave_request", mode="REMOTE", leave_type="SICK"), message="mai wfh")
    assert remote.slots["leave_code"] == "REMOTE"
    other = plan_of(call("draft_attendance_fix", for_other_person="Nam"))
    assert (other.target, other.employee_reference) == ("EMPLOYEE", "Nam")


def test_several_requests_become_parts_and_repeated_actions_need_a_choice():
    plan = plan_of(call("answer_policy_question", question="Nghỉ ốm cần giấy tờ gì?", search_queries=["giấy tờ nghỉ ốm"]),
                   call("show_leave_balance", subject="SELF"))
    assert [part.intent for part in plan.sub_requests] == ["POLICY_QUERY", "LEAVE_BALANCE"]
    assert plan.retrieval_queries == ["giấy tờ nghỉ ốm"]
    twice = plan_of(call("show_leave_balance", subject="EMPLOYEE", employee_reference="An"),
                    call("show_leave_balance", subject="EMPLOYEE", employee_reference="Bình"))
    assert twice.multiple_actions and not twice.sub_requests
    # A refusal alongside a real request does not hide the request.
    assert plan_of(call("decline_request", reason="NOT_HR"), call("show_my_leave_requests")).intent == "LEAVE_STATUS"


def test_meta_actions():
    vague = plan_of(call("clarify_request", candidates=["show_leave_balance", "draft_leave_request"]))
    assert vague.needs_clarification and (vague.intent, vague.alternative_intent) == ("LEAVE_BALANCE", "DRAFT_LEAVE")
    refused = plan_of(call("decline_request", reason="NOT_PERMITTED"))
    assert (refused.intent, refused.question_kind) == ("OUT_OF_SCOPE", "PERMISSION")
    queue = plan_of(call("open_approval_queue", queue="ATTENDANCE_FIX"))
    assert (queue.intent, queue.target) == ("REPORT_ATTENDANCE_QUEUE", "DIRECT_REPORTS")


@pytest.mark.parametrize("text,expected", [("8h05", "08:05:00"), ("17:30", "17:30:00"), ("6pm", "18:00:00"),
                                           ("5 giờ chiều", "17:00:00"), ("25h", None), ("sáng", None)])
def test_parse_clock(text, expected):
    assert parse_clock(text) == expected


def test_draft_hints_resolve_dates_deterministically_and_drop_unresolvable_ones():
    fields, code, days = draft_hints("DRAFT_LEAVE", {"date": "thứ 2 tuần sau", "end_date": "thứ 4 tuần sau",
                                                     "session": "FULL_DAY", "leave_code": "SICK"}, TODAY)
    assert fields == {"leave_date": "2026-10-19", "session": "FULL_DAY"} and code == "SICK"
    assert [day.isoformat() for day in days] == ["2026-10-19", "2026-10-20", "2026-10-21"]
    fix, _, _ = draft_hints("DRAFT_FIX", {"date": "thứ 5", "event": "CHECK_OUT", "time": "17h30", "reason": "máy hỏng"}, date(2026, 10, 17))
    assert fix == {"work_date": "2026-10-15", "event_type": "CHECK_OUT", "requested_time": "17:30:00", "reason": "máy hỏng"}
    assert draft_hints("DRAFT_LEAVE", {"date": "hôm nào đó", "session": "EVENING"}, TODAY)[0] == {}


# --- lock-in -------------------------------------------------------------------

@pytest.fixture
def semantic(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_SEMANTIC_ENABLED", True)


def draft(command="DRAFT_LEAVE", missing=("session", "leave_type_id", "reason")):
    return SimpleNamespace(draft_id=D, revision=2, command=command, status="COLLECTING",
                           missing_fields=list(missing), typed_params={"leave_date": "2026-10-16"})


async def turn(monkeypatch, message, open_draft, calls=None):
    monkeypatch.setattr(AIDraftService, "get_draft", AsyncMock(return_value=open_draft))
    continued = AsyncMock(return_value=AIChatResponse(reply="next field", draft_id=D, draft_revision=3))
    monkeypatch.setattr(AIService, "_continue_draft", continued)
    understood = AsyncMock(return_value=Understanding(calls or []))
    monkeypatch.setattr(understanding_module, "understand", understood)
    actor = SimpleNamespace(user_account_id=9, employee_id=7,
                            role_assignments=[SimpleNamespace(role=SimpleNamespace(role_code="EMPLOYEE"))])
    response = await AIService.process_chat(AsyncMock(), 7, AIChatRequest(message=message, draft_id=D, draft_revision=2),
                                            {"EMPLOYEE"}, 9, actor)
    return response, continued, understood


@pytest.mark.asyncio
async def test_short_answer_to_the_asked_field_skips_the_model(monkeypatch, semantic):
    response, continued, understood = await turn(monkeypatch, "buổi chiều", draft())
    understood.assert_not_called()
    assert continued.await_args.args[3] == "buổi chiều" and response.reply == "next field"


@pytest.mark.asyncio
async def test_free_text_answer_is_understood_against_the_open_form(monkeypatch, semantic):
    response, continued, understood = await turn(monkeypatch, "thôi để chiều đi, ở nhà chờ thợ sửa điện", draft(),
                                                 [call("draft_leave_request", session="AFTERNOON", reason="chờ thợ sửa điện")])
    assert understood.await_args.kwargs == {"open_form": "draft_leave_request", "waiting_for": "session"}
    assert continued.await_args.kwargs["hints"] == {"session": "AFTERNOON", "reason": "chờ thợ sửa điện"}


@pytest.mark.asyncio
async def test_changing_a_field_while_the_reason_is_asked_does_not_become_the_reason(monkeypatch, semantic):
    _, continued, _ = await turn(monkeypatch, "à đổi sang buổi sáng nhé", draft(missing=("reason",)),
                                 [call("draft_leave_request", session="MORNING")])
    assert continued.await_args.args[3] == "" and continued.await_args.kwargs["hints"] == {"session": "MORNING"}


@pytest.mark.asyncio
async def test_side_question_is_answered_and_the_form_stays_open(monkeypatch, semantic):
    monkeypatch.setattr(router, "load_context", AsyncMock(return_value=None))
    dispatch = AsyncMock(return_value=AIChatResponse(reply="Còn 8 ngày."))
    monkeypatch.setattr(AIService, "_dispatch_free_intent", dispatch)
    response, continued, _ = await turn(monkeypatch, "à mà tôi còn mấy ngày phép nhỉ", draft(),
                                        [call("show_leave_balance", subject="SELF")])
    continued.assert_not_called()
    assert response.reply == "Còn 8 ngày." and response.draft_id == D and response.status == "NEEDS_INPUT"
    assert dispatch.await_args.args[4].draft_id is None  # The lookup never sees the form.


@pytest.mark.asyncio
async def test_another_write_action_asks_to_finish_or_cancel_first(monkeypatch, semantic):
    response, continued, _ = await turn(monkeypatch, "à quên, hôm qua tôi cũng quên chấm công lúc về", draft(),
                                        [call("draft_attendance_fix", date="hôm qua", event="CHECK_OUT")])
    continued.assert_not_called()
    assert response.message_code == "DRAFT_SWITCH_CONFIRMATION_REQUIRED" and response.draft_id == D


@pytest.mark.asyncio
async def test_understood_cancel_discards_the_form(monkeypatch, semantic):
    _, continued, _ = await turn(monkeypatch, "thôi khỏi làm đơn nữa", draft(), [call("cancel_current_form")])
    assert continued.await_args.args[3] == "hủy"


@pytest.mark.asyncio
async def test_provider_failure_mid_form_keeps_the_form_and_guesses_nothing(monkeypatch, semantic):
    monkeypatch.setattr(AIDraftService, "get_draft", AsyncMock(return_value=draft()))
    continued = AsyncMock()
    monkeypatch.setattr(AIService, "_continue_draft", continued)
    monkeypatch.setattr(understanding_module, "understand", AsyncMock(side_effect=ProviderFailure("QUOTA_EXCEEDED")))
    response = await AIService.process_chat(AsyncMock(), 7, AIChatRequest(message="để mình nghĩ thêm đã nhé bạn ơi", draft_id=D, draft_revision=2),
                                            {"EMPLOYEE"}, 9, SimpleNamespace(user_account_id=9))
    continued.assert_not_called()
    assert response.status == "NEEDS_INPUT" and response.message_code == "AI_INTENT_QUOTA_EXCEEDED" and response.draft_id == D


# --- chart requests ----------------------------------------------------------------

def test_report_draft_purpose_is_a_closed_value():
    AIDraftService._validate_command_and_params("DRAFT_REPORT", {"purpose": "ANALYZE"})
    with pytest.raises(Exception):
        AIDraftService._validate_command_and_params("DRAFT_REPORT", {"purpose": "DELETE"})


@pytest.mark.asyncio
async def test_finished_chart_request_answers_with_the_analysis(monkeypatch):
    from app.schemas.reports import ReportRunCreate
    from app.services import ai_analysis_tool
    from app.services.ai_report_draft_service import AIReportDraftService, run_params
    params = {"kind": "LEAVE", "scope": "DIRECT_REPORTS", "start_date": "2026-10-01", "end_date": "2026-10-15",
              "purpose": "ANALYZE"}
    analysis = {"run": {"run_id": "a" * 32}, "row_count": 3, "metrics": {}, "frequencies": {}, "chart": {"type": "bar"}}
    execute = AsyncMock(return_value=analysis)
    monkeypatch.setattr(ai_analysis_tool.AIAnalysisTool, "execute", execute)
    monkeypatch.setattr(ai_analysis_tool, "analysis_summary", lambda value: "Phân tích 3 dòng")
    open_draft = SimpleNamespace(draft_id=D, typed_params=params)
    response = await AIReportDraftService.finished(None, object(), open_draft, ReportRunCreate.model_validate(run_params(params)),
                                                   SimpleNamespace(run_id="a" * 32))
    assert response.message_code == "REPORT_ANALYZED" and response.report_analysis["chart"] == {"type": "bar"}
    assert "purpose" not in response.action.data and response.action.data["run_id"] == "a" * 32
    execute.assert_awaited_once()


@pytest.mark.parametrize("message,other", [
    ("sáng nay quẹt thẻ ko lên, làm giúp đơn bổ sung", False),  # lowercase "đơn" is not a name
    ("xin nghỉ cho con đi khám", False),
    ("phân tích chấm công quý 3", False),
    ("Xin nghỉ ngày mai cho Minh", True),
    ("nguyen van an con bao nhieu phep", True),
    ("Trần Thị Bình còn mấy ngày phép", True),
    ("phép của đồng nghiệp tôi", True),
])
def test_other_person_evidence(message, other):
    from app.services.ai_employee_query import names_someone_else
    assert names_someone_else(message) is other
