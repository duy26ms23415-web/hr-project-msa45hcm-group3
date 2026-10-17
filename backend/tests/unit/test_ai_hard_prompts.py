"""Hard prompts: teencode/typos on the rule path, and planner-driven clarification,
multi-part answers and follow-ups on the semantic path."""
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai import semantic_router as module
from app.ai.parsing import intent
from app.ai.parsing.intent import ChatPlan, SubRequest
from app.ai.parsing.lexicon import canonical
from app.core.config import settings
from app.schemas.ai import AIChatMessage, AIChatRequest, AIChatResponse, AISource
from app.services import ai_conversation_state
from app.services.ai_conversation_state import ConversationContext
from app.services.ai_employee_query import explicitly_requests_self
from app.services.ai_service import AIService


@pytest.mark.parametrize("message,expected", [
    ("mai e bận vc nhà chắc k lên cty dc", "khong len cong ty duoc"),
    ("xinnghi phep ngay mai", "xin nghi phep ngay mai"),
    ("tớ còn bn ngày fep", "toi con bao nhieu ngay phep"),
    ("quên check in sáng nay", "quen check-in"),
    ("quen checkout hom qua", "quen check-out"),
    ("cho mk xem bc chamcong thnag nay", "minh xem bao cao cham cong thang nay"),
    ("Toi muon xin off chieu mai", "xin nghi chieu mai"),
    ("ngỉ fép năm còn mấy hôm", "nghi phep nam con may ngay"),
])
def test_canonical_text_expands_teencode_merged_words_and_typos(message, expected):
    assert expected in canonical(message)


@pytest.mark.parametrize("message,kept", [
    ("quen cham cong hom qua 17:30", "quen cham cong hom qua 17:30"),
    ("ngay 10/10/2026, EMP003.", "ngay 10/10/2026, emp003."),
    ("Tạo báo cáo toàn công ty", "tao bao cao toan cong ty"),
    ("Xem số dư phép của bản thân", "xem so du phep cua ban than"),
    ("leave balance của tôi", "leave balance cua toi"),
])
def test_canonical_text_keeps_times_dates_codes_and_real_words(message, kept):
    assert canonical(message) == kept


@pytest.mark.parametrize("message,kept", [
    ("xin về sớm hôm nay", "xin ve som hom nay"),      # not a leave request
    ("xin đi trễ mai", "xin di tre mai"),
    ("tk của tôi bị khóa", "tk cua toi bi khoa"),      # "tài khoản", not "thống kê"
    ("hoa hồng", "hoa hong"),
    ("chị Thành, anh Phương", "chi thanh, anh phuong"),  # names are not typos
])
def test_canonical_text_does_not_over_rewrite(message, kept):
    assert canonical(message) == kept


@pytest.mark.parametrize("message", ["em còn mấy ngày phép", "Xem giúp mình số dư phép", "tui duoc nghi may ngay nua",
                                     "check my timesheet", "cua tớ con bn ngay phep"])
def test_first_person_chat_forms_count_as_self_evidence(message):
    assert explicitly_requests_self(message)


@pytest.mark.parametrize("message", ["Nguyễn Văn An còn bao nhiêu ngày phép?", "phép năm nay còn mấy ngày?",
                                     "Show my employee's remaining leave balance"])
def test_subjectless_or_named_requests_are_not_self_evidence(message):
    assert not explicitly_requests_self(message)


@pytest.fixture
def semantic(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_SEMANTIC_ENABLED", True)
    monkeypatch.setattr(ai_conversation_state, "remember", AsyncMock())
    monkeypatch.setattr(module, "remember", AsyncMock())


def actor(role="EMPLOYEE"):
    return SimpleNamespace(user_account_id=9, employee_id=7,
                          role_assignments=[SimpleNamespace(role=SimpleNamespace(role_code=role))])


async def chat(message, role="EMPLOYEE", db=None):
    return await AIService.process_chat(db or AsyncMock(), 7, AIChatRequest(message=message), {role}, 9, actor(role))


@pytest.mark.asyncio
async def test_low_confidence_returns_server_written_choices_without_dispatch(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="LEAVE_BALANCE", target="SELF", confidence="LOW", alternative_intent="DRAFT_LEAVE")))
    dispatch = AsyncMock(side_effect=AssertionError("Unclear requests must not run a tool"))
    monkeypatch.setattr(AIService, "_dispatch_free_intent", dispatch)
    response = await chat("phep mai")
    assert response.status == "NEEDS_INPUT" and response.message_code == "INTENT_CONFIRMATION_REQUIRED"
    assert response.clarification_options == ["Xem số dư phép năm của tôi", "Soạn đơn xin nghỉ cho tôi"]


@pytest.mark.asyncio
async def test_target_required_offers_an_explicit_self_choice(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(intent="LEAVE_BALANCE", target="SELF")))
    response = await chat("phép năm của đồng nghiệp còn mấy ngày?")
    assert response.message_code == "TARGET_REQUIRED"
    assert response.clarification_options == ["Xem số dư phép năm của tôi"]
    assert explicitly_requests_self(response.clarification_options[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["phép năm nay còn mấy ngày?", "con lai bao nhieu phep", "hôm qua mấy giờ tôi về"])
async def test_self_reading_without_any_other_person_is_answered(monkeypatch, semantic, message):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(intent="LEAVE_BALANCE", target="SELF")))
    dispatch = AsyncMock(return_value=AIChatResponse(reply="self result"))
    monkeypatch.setattr(AIService, "_dispatch_free_intent", dispatch)
    response = await chat(message)
    assert response.reply == "self result"
    assert dispatch.await_args.kwargs["requested_scope"] == "SELF"


@pytest.mark.asyncio
async def test_multi_part_message_answers_policy_and_self_lookup_together(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="LEAVE_BALANCE", target="SELF", sub_requests=[
            SubRequest(intent="POLICY_QUERY", target="NONE", question="Đi muộn bị xử lý thế nào?"),
            SubRequest(intent="LEAVE_BALANCE", target="SELF"),
        ])))
    source = AISource(document_id=1, title="Nội quy", excerpt="Đi muộn 3 lần bị nhắc nhở.")
    knowledge = AsyncMock(return_value=AIChatResponse(reply="Đi muộn 3 lần bị nhắc nhở. [1]", sources=[source]))
    monkeypatch.setattr(AIService, "_answer_knowledge", knowledge)
    dispatch = AsyncMock(return_value=AIChatResponse(reply="Số dư phép năm 2026 của bạn: 8 ngày."))
    monkeypatch.setattr(AIService, "_dispatch_free_intent", dispatch)
    response = await chat("phép của tôi còn bao nhiêu, với lại đi muộn thì sao")
    assert "nhắc nhở" in response.reply and "8 ngày" in response.reply
    assert response.sources == [source]
    assert knowledge.await_args.args[3].message == "Đi muộn bị xử lý thế nào?"
    assert dispatch.await_args.args[5] == "LEAVE_BALANCE"


@pytest.mark.asyncio
async def test_two_write_parts_still_require_choosing_one(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="DRAFT_LEAVE", target="SELF", sub_requests=[
            SubRequest(intent="DRAFT_LEAVE", target="SELF"), SubRequest(intent="DRAFT_FIX", target="SELF")])))
    monkeypatch.setattr(AIService, "_dispatch_free_intent", AsyncMock(side_effect=AssertionError("no writes")))
    response = await chat("xin nghỉ mai và giải trình hôm qua")
    assert response.message_code == "MULTIPLE_ACTIONS_REQUIRED"


@pytest.mark.asyncio
async def test_period_follow_up_reuses_previous_self_intent_from_server_state(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="POLICY_QUERY", target="UNSPECIFIED", confidence="LOW", follow_up="PREVIOUS_PERIOD")))
    monkeypatch.setattr(module, "load_context", AsyncMock(return_value=ConversationContext("ATTENDANCE_SUMMARY", "SELF")))
    dispatch = AsyncMock(return_value=AIChatResponse(reply="tháng trước"))
    monkeypatch.setattr(AIService, "_dispatch_free_intent", dispatch)
    response = await chat("còn tháng trước thì sao?")
    assert response.reply == "tháng trước"
    assert dispatch.await_args.args[5] == "ATTENDANCE_SUMMARY"
    assert dispatch.await_args.kwargs["requested_scope"] == "SELF"


@pytest.mark.asyncio
async def test_follow_up_without_state_never_defaults_to_self(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="ATTENDANCE_SUMMARY", target="UNSPECIFIED", follow_up="PREVIOUS_PERIOD")))
    monkeypatch.setattr(module, "load_context", AsyncMock(return_value=None))
    monkeypatch.setattr(AIService, "_dispatch_free_intent", AsyncMock(side_effect=AssertionError("no self fallback")))
    response = await chat("còn tháng trước thì sao?")
    assert response.message_code == "TARGET_REQUIRED"


@pytest.mark.asyncio
async def test_previous_employee_follow_up_goes_through_scoped_lookup(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="LEAVE_BALANCE", target="UNSPECIFIED", follow_up="PREVIOUS_EMPLOYEE")))
    monkeypatch.setattr(module, "load_context", AsyncMock(return_value=ConversationContext(
        "ATTENDANCE_SUMMARY", "EMPLOYEE", "EMP023")))
    lookup = AsyncMock(return_value=AIChatResponse(reply="Số dư phép năm 2026 của Nguyễn Văn An (EMP023): 8 ngày."))
    monkeypatch.setattr(module, "answer_employee_query", lookup)
    response = await chat("còn phép của bạn ấy?", role="HR")
    assert "EMP023" in response.reply
    assert lookup.await_args.kwargs["interpretation"].employee_reference == "EMP023"
    # The stored code is appended so the "reference must appear in the request" rule holds.
    assert lookup.await_args.args[2].message.endswith("(EMP023)")


@pytest.mark.asyncio
async def test_topic_follow_up_boosts_previous_sections_without_history(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="POLICY_QUERY", target="NONE", follow_up="PREVIOUS_TOPIC",
        standalone_question="Trường hợp nghỉ phép quá 5 ngày liên tục thì sao?", question_kind="CONSEQUENCE")))
    monkeypatch.setattr(module, "load_context", AsyncMock(return_value=ConversationContext("POLICY_QUERY", "NONE", None, [100, 101])))
    knowledge = AsyncMock(return_value=AIChatResponse(reply="ok"))
    monkeypatch.setattr(AIService, "_answer_knowledge", knowledge)
    await chat("trường hợp đó thì sao")
    assert knowledge.await_args.kwargs["boost_section_ids"] == [100, 101]
    assert knowledge.await_args.kwargs["question_kind"] == "CONSEQUENCE"
    assert knowledge.await_args.kwargs["standalone_question"].startswith("Trường hợp")


@pytest.mark.asyncio
async def test_forbidden_action_is_refused_and_cites_prohibition(monkeypatch, semantic):
    from app.services.ai_knowledge_tool import AIKnowledgeTool
    from app.services.knowledge_retrieval import Passage
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="OUT_OF_SCOPE", target="NONE", question_kind="PERMISSION")))
    rule = Passage(document_id=1, title="Nội quy", content="Nghiêm cấm nhờ người khác chấm công hộ.", source_url=None,
                   version_id=2, section_id=3, page_start=4, page_end=4, rule_type="PROHIBITION")
    search = AsyncMock(return_value=[rule])
    monkeypatch.setattr(AIKnowledgeTool, "search", search)
    response = await chat("chấm công giúp bạn Lan hôm nay nhé")
    assert response.message_code == "ACTION_NOT_PERMITTED" and response.action is None
    assert response.sources[0].viewer_path == "/knowledge/view/1?version=2&section=3"
    assert search.await_args.kwargs["rule_types"] == ("PROHIBITION", "OBLIGATION")


@pytest.mark.asyncio
async def test_planner_payload_never_contains_history(monkeypatch):
    from app.ai import understanding
    generate = AsyncMock(return_value=[("answer_policy_question", {"question": "Nói rõ hơn"})])
    monkeypatch.setattr(understanding, "generate_function_calls", generate)
    await intent.interpret_chat_request("nói rõ hơn", date(2026, 10, 16), previous_intent="POLICY_QUERY",
                                        previous_target="NONE")
    payload = json.loads(generate.await_args.args[1])
    # Only the current message, the date and enum metadata: never history or records.
    assert set(payload) == {"message", "today", "context"}
    assert payload["context"] == {"previous_action": "answer_policy_question"}


@pytest.mark.asyncio
async def test_rule_path_follow_up_widens_retrieval_but_provider_sees_current_question(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_SEMANTIC_ENABLED", False)
    passages = AsyncMock(return_value=([], []))
    monkeypatch.setattr(AIService, "_knowledge_passages", passages)
    monkeypatch.setattr(AIService, "_classify_free_intent", AsyncMock(return_value=None))
    request = AIChatRequest(message="nói rõ hơn", conversation_history=[AIChatMessage(role="user", content="giờ làm việc")])
    await AIService._answer_knowledge(None, {"EMPLOYEE"}, date(2026, 10, 16), request)
    queries = passages.await_args.args[3]
    assert queries == ["giờ làm việc nói rõ hơn"]
    assert passages.await_args.kwargs["embed_queries"] == ["nói rõ hơn"]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["còn Lan thì sao?", "con lan thi sao", "còn chị Hoa tháng trước?"])
async def test_follow_up_naming_someone_never_continues_self(monkeypatch, semantic, message):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="ATTENDANCE_SUMMARY", target="UNSPECIFIED", follow_up="PREVIOUS_PERIOD")))
    monkeypatch.setattr(module, "load_context", AsyncMock(return_value=ConversationContext("ATTENDANCE_SUMMARY", "SELF")))
    monkeypatch.setattr(AIService, "_dispatch_free_intent", AsyncMock(side_effect=AssertionError("no self data")))
    response = await chat(message)
    assert response.status == "NEEDS_INPUT" and response.message_code == "TARGET_REQUIRED"


@pytest.mark.asyncio
async def test_period_follow_up_after_employee_lookup_reuses_that_employee(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="LEAVE_BALANCE", target="UNSPECIFIED", follow_up="PREVIOUS_PERIOD")))
    monkeypatch.setattr(module, "load_context", AsyncMock(return_value=ConversationContext(
        "LEAVE_BALANCE", "EMPLOYEE", "EMP023")))
    lookup = AsyncMock(return_value=AIChatResponse(reply="EMP023: 8 ngày."))
    monkeypatch.setattr(module, "answer_employee_query", lookup)
    response = await chat("còn năm ngoái thì sao?", role="HR")
    assert response.reply == "EMP023: 8 ngày."
    assert lookup.await_args.kwargs["interpretation"].employee_reference == "EMP023"


@pytest.mark.asyncio
async def test_multi_part_keeps_a_part_that_needs_input(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="LEAVE_BALANCE", target="SELF", sub_requests=[
            SubRequest(intent="POLICY_QUERY", target="NONE", question="Đi muộn bị xử lý thế nào?"),
            SubRequest(intent="LEAVE_BALANCE", target="SELF"),
        ])))
    monkeypatch.setattr(AIService, "_answer_knowledge", AsyncMock(return_value=AIChatResponse(reply="Nhắc nhở.")))
    monkeypatch.setattr(AIService, "_dispatch_free_intent", AsyncMock(side_effect=AssertionError("no self data")))
    response = await chat("phép năm của đồng nghiệp còn mấy ngày, với lại đi muộn thì sao")
    assert response.status == "NEEDS_INPUT" and response.message_code == "TARGET_REQUIRED"
    assert response.clarification_options == ["Xem số dư phép năm của tôi"]
    assert "Nhắc nhở." in response.reply


@pytest.mark.asyncio
async def test_report_without_scope_continues_as_a_draft(monkeypatch, semantic):
    monkeypatch.setattr(module, "interpret_chat_request", AsyncMock(return_value=ChatPlan(
        intent="REPORT_ATTENDANCE", target="UNSPECIFIED")))
    draft = AIChatResponse(reply="Bạn muốn báo cáo trong phạm vi nào?", draft_id="d1", draft_revision=1,
                           missing_fields=["scope"], message_code="REPORT_SCOPE_REQUIRED")
    dispatch = AsyncMock(return_value=draft)
    monkeypatch.setattr(AIService, "_dispatch_free_intent", dispatch)
    response = await chat("tạo báo cáo chấm công", role="MANAGER")
    assert response.draft_id == "d1" and response.missing_fields == ["scope"]
    assert dispatch.await_args.kwargs["requested_scope"] is None


@pytest.mark.asyncio
async def test_rule_path_report_without_scope_starts_draft(monkeypatch):
    from app.ai.orchestrator import ChatOrchestrator
    from app.services.ai_report_draft_service import AIReportDraftService
    monkeypatch.setattr(settings, "GEMINI_ENABLED", False)
    start = AsyncMock(return_value=AIChatResponse(reply="phạm vi?", draft_id="d1", draft_revision=1, missing_fields=["scope"]))
    monkeypatch.setattr(AIReportDraftService, "start", start)
    response = await ChatOrchestrator.process_chat(AsyncMock(), 7, AIChatRequest(message="tạo báo cáo chấm công"),
                                                   {"MANAGER"}, 9, actor("MANAGER"))
    assert response.draft_id == "d1" and response.message_code != "TARGET_REQUIRED"
    start.assert_awaited_once()
