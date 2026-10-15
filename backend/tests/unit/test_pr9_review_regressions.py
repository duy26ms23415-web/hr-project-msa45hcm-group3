"""Regression coverage for PR #9 review findings; no live provider or DB."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.ai.orchestrator import ChatOrchestrator
from app.core.config import settings
from app.schemas.ai import AIChatRequest, AIChatResponse
from app.schemas.reports import ReportRunCreate
from app.services.ai_service import AIService
from app.services.ai_report_draft_service import AIReportDraftService
from app.services import ai_report_draft_service as drafts
from app.services import ai_report_interpreter as interpreter
from app.services import ai_request_security as security
from app.services import report_run_service as runs


def actor(role="EMPLOYEE"):
    return NS(user_account_id=9, employee_id=7, login_email="owner@example.test",
              role_assignments=[NS(role=NS(role_code=role))])


@pytest.mark.asyncio
@pytest.mark.parametrize("command,field", [("DRAFT_LEAVE", "leave_date"), ("DRAFT_FIX", "work_date")])
async def test_reason_dates_never_fill_requested_date(monkeypatch, command, field):
    provider = AsyncMock(side_effect=AssertionError("Reason is not a date request"))
    from app.ai.parsing import dates
    monkeypatch.setattr(dates, "generate_json", provider)
    message = "Tôi muốn xin nghỉ phép vì đã làm bù ngày 10/10/2026"
    answers = await AIService._draft_answers_with_date(command, message)
    assert answers == {"reason": "đã làm bù ngày 10/10/2026"}
    answers = await AIService._draft_answers_with_date(command, "Ngày 20/10/2026 vì đã làm bù ngày 10/10/2026")
    assert answers[field] == "2026-10-20"
    provider.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("message", ["Nguyễn Văn An muốn xin nghỉ ngày mai", "nguyen van an muon xin nghi ngay mai"])
async def test_name_first_request_never_drafts_for_current_employee(monkeypatch, enabled, message):
    monkeypatch.setattr(settings, "GEMINI_ENABLED", enabled)
    monkeypatch.setattr(settings, "GEMINI_SEMANTIC_ENABLED", False)
    start = AsyncMock()
    monkeypatch.setattr(AIService, "_start_draft", start)
    result = await ChatOrchestrator.process_chat(AsyncMock(), 7, AIChatRequest(message=message),
                                                {"EMPLOYEE"}, 9, actor())
    assert result.message_code == "TARGET_REQUIRED"
    start.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("message", [
    "Xin nghỉ ngày mai cho Nguyễn Văn An",
    "Tạo đơn nghỉ ngày mai cho nguyen van an",
    "Xin nghỉ ngày mai cho Minh",
    "Tôi muốn xin nghỉ cho chị Lê Thu Hà",
    "Tạo giải trình hôm qua cho nhân viên EMP002",
])
async def test_suffix_employee_target_never_drafts_for_actor(monkeypatch, enabled, message):
    from app.ai import orchestrator as route

    monkeypatch.setattr(settings, "GEMINI_ENABLED", enabled)
    monkeypatch.setattr(settings, "GEMINI_SEMANTIC_ENABLED", False)
    employee_lookup = AsyncMock(return_value=AIChatResponse(
        reply="Cần xác nhận nhân viên", status="NEEDS_INPUT", message_code="EMPLOYEE_QUERY_REQUIRED"))
    monkeypatch.setattr(route, "answer_employee_query", employee_lookup)
    start = AsyncMock(side_effect=AssertionError("A third-party request must not draft for SELF"))
    monkeypatch.setattr(AIService, "_start_draft", start)

    result = await ChatOrchestrator.process_chat(
        AsyncMock(), 7, AIChatRequest(message=message), {"EMPLOYEE"}, 9, actor())
    assert result.message_code == "EMPLOYEE_QUERY_REQUIRED"
    employee_lookup.assert_awaited_once()
    start.assert_not_awaited()


@pytest.mark.asyncio
async def test_semantic_misclassified_self_cannot_draft_for_named_employee(monkeypatch):
    from app.ai import semantic_router
    from app.ai.parsing.intent import ChatPlan

    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_SEMANTIC_ENABLED", True)
    monkeypatch.setattr(semantic_router, "interpret_chat_request", AsyncMock(
        return_value=ChatPlan(intent="DRAFT_LEAVE", target="SELF")))
    start = AsyncMock(side_effect=AssertionError("Must reject a conflicting employee"))
    monkeypatch.setattr(AIService, "_start_draft", start)

    result = await ChatOrchestrator.process_chat(
        AsyncMock(), 7, AIChatRequest(message="Tôi muốn xin nghỉ cho Nguyễn Văn An"),
        {"EMPLOYEE"}, 9, actor())
    assert result.message_code == "TARGET_CONFLICT"
    start.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["Xin nghỉ ngày mai", "Tôi muốn xin nghỉ ngày mai", "Vui lòng giúp tôi tạo giải trình hôm qua"])
async def test_self_and_bare_draft_commands_still_work(monkeypatch, message):
    monkeypatch.setattr(settings, "GEMINI_ENABLED", False)
    start = AsyncMock(return_value=AIChatResponse(reply="draft"))
    monkeypatch.setattr(AIService, "_start_draft", start)
    await ChatOrchestrator.process_chat(AsyncMock(), 7, AIChatRequest(message=message), {"EMPLOYEE"}, 9, actor())
    start.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("message,field,value", [
    ("Đổi ngày kết thúc sang 2026-10-20", "end_date", "2026-10-20"),
    ("Đổi ngày bắt đầu sang 2026-10-05", "start_date", "2026-10-05"),
])
async def test_revise_one_endpoint_preserves_other_filters(monkeypatch, message, field, value):
    provider = AsyncMock(side_effect=AssertionError("Explicit endpoint must be parsed locally"))
    monkeypatch.setattr(interpreter, "generate_json", provider)
    current = dict(start_date="2026-10-01", end_date="2026-10-08", employee_id=23)
    db = AsyncMock()
    db.scalar.return_value = NS(kind="ATTENDANCE", scope="COMPANY", status="READY",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1), filters=current)
    start = AsyncMock()
    monkeypatch.setattr(AIReportDraftService, "start", start)
    await AIReportDraftService.revise_run(db, actor("HR"), "a" * 32, message, date(2026, 10, 15))
    assert start.await_args.args[4] == {"kind": "ATTENDANCE", "scope": "COMPANY", **current, field: value}
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_switch_to_payslip_collects_month_then_completes(monkeypatch):
    db = AsyncMock()
    db.add = Mock()
    db.scalar.return_value = NS(kind="ATTENDANCE", scope="COMPANY", status="READY",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        filters=dict(start_date="2026-10-01", end_date="2026-10-08", employee_id=23, department_id=2))
    monkeypatch.setattr(drafts, "interpret_report_prompt", AsyncMock(return_value={}))
    create = AsyncMock(return_value={"run": NS(run_id="b" * 32)})
    monkeypatch.setattr(runs.ReportRunService, "create", create)
    monkeypatch.setattr(drafts.AIDraftService, "mark_ready", AsyncMock())
    result = await AIReportDraftService.revise_run(db, actor("HR"), "a" * 32, "Đổi sang phiếu lương", date(2026, 10, 15))
    draft = db.add.call_args.args[0]
    assert result.missing_fields == ["start_date", "end_date"]
    assert draft.typed_params == {"kind": "MY_PAYSLIP", "scope": "SELF"}
    create.assert_not_awaited()

    async def update(_db, _id, _owner, params, missing):
        draft.typed_params, draft.missing_fields = params, missing
        draft.revision += 1
        return draft

    monkeypatch.setattr(drafts.AIDraftService, "update_draft", update)
    result = await AIReportDraftService.continue_draft(db, actor("HR"), draft, "Tháng trước", date(2026, 10, 15))
    req = create.await_args.args[2]
    assert req.kind == "MY_PAYSLIP" and req.scope == "SELF"
    assert (req.start_date, req.end_date) == (date(2026, 9, 1), date(2026, 9, 30))
    assert result.action.data["run_id"] == "b" * 32


@pytest.mark.asyncio
async def test_chat_audit_uses_accessed_scope_and_is_request_local(monkeypatch):
    record = AsyncMock()
    monkeypatch.setattr(security, "record_event", record)
    async with security.secured_operation(None, 9, "CHAT", "CHAT", rate_limit=False) as audit:
        security.note_data_scope("COMPANY")
        security.note_data_scope("SELF")
        assert audit["scope"] == "COMPANY"
    assert record.await_args.args[4] == "COMPANY"
    async with security.secured_operation(None, 9, "CHAT", "CHAT", rate_limit=False) as audit:
        # A collecting report draft has not accessed report records.
        assert audit["scope"] == "NONE"
    assert record.await_args.args[4] == "NONE"


@pytest.mark.asyncio
@pytest.mark.parametrize("first_attempt_fails", [False, True])
async def test_cancelled_chat_waits_for_report_terminal_state_and_replays(monkeypatch, first_attempt_fails):
    req = ReportRunCreate(kind="ATTENDANCE", scope="SELF", start_date="2026-10-01", end_date="2026-10-15")
    persisted = {}
    state_db = AsyncMock()
    state_db.__aenter__.return_value = state_db
    state_db.scalar.side_effect = lambda _: persisted.get("run")
    monkeypatch.setattr(runs, "AsyncSessionLocal", lambda: state_db)
    entered, release = asyncio.Event(), asyncio.Event()
    attempts = []

    async def save(_user, _req, run_id, scope, ids, status, **values):
        run = NS(run_id=run_id, status=status, scope=scope, kind=req.kind,
                 filters=runs.ReportRunService.request_filters(req), **values)
        persisted["run"] = run
        return run

    async def generate(*args, **kwargs):
        entered.set()
        await release.wait()
        attempts.append(True)
        if first_attempt_fails and len(attempts) == 1:
            raise OSError("Transient data failure")
        return {"rows": [{"employee_id": 7}], "kind": "ATTENDANCE"}

    monkeypatch.setattr(runs.ReportRunService, "_save_state", save)
    monkeypatch.setattr(runs.ReportService, "visible_employee_ids", AsyncMock(return_value=("SELF", [7])))
    monkeypatch.setattr(runs.ReportService, "generate", generate)
    monkeypatch.setattr(runs, "build_xlsx_report", Mock(return_value=b"xlsx"))
    monkeypatch.setattr(runs, "store_report", Mock(side_effect=[("a.xlsx", "digest"), ("a.json", "digest")]))
    task = asyncio.create_task(runs.ReportRunService._create(AsyncMock(), actor(), req, source_draft_id="draft-1"))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert persisted["run"].status == ("FAILED" if first_attempt_fails else "READY")
    original_run_id = persisted["run"].run_id
    from app.services import report_access
    monkeypatch.setattr(report_access, "authorized_run", AsyncMock(return_value=persisted["run"]))
    result = await runs.ReportRunService._create(AsyncMock(), actor(), req, source_draft_id="draft-1")
    assert result["run"] is persisted["run"]
    assert result["run"].status == "READY" and result["run"].run_id == original_run_id
    assert len(attempts) == (2 if first_attempt_fails else 1)


@pytest.mark.asyncio
async def test_failed_report_retry_claim_is_exclusive(monkeypatch):
    req = ReportRunCreate(kind="ATTENDANCE", scope="SELF", start_date="2026-10-01", end_date="2026-10-15")
    run = NS(status="FAILED", error_code="DATA_SERVICE_UNAVAILABLE", storage_key=None,
             snapshot_storage_key=None, kind=req.kind, scope="SELF",
             filters=runs.ReportRunService.request_filters(req))
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.scalar.return_value = run
    monkeypatch.setattr(runs, "AsyncSessionLocal", lambda: db)
    await runs.ReportRunService._save_state(actor(), req, "a" * 32, "SELF", [7], "GENERATING")
    assert run.status == "GENERATING" and run.scope_snapshot == [7]
    with pytest.raises(HTTPException) as conflict:
        await runs.ReportRunService._save_state(actor(), req, "a" * 32, "SELF", [7], "GENERATING")
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,collecting", [("COMPANY", False), ("DIRECT_REPORTS", False), ("NONE", True)])
async def test_endpoint_does_not_infer_scope_from_response_shape(monkeypatch, scope, collecting):
    from app.api.v1.endpoints import ai
    record = AsyncMock()
    monkeypatch.setattr(security, "consume_budget", AsyncMock())
    monkeypatch.setattr(security, "record_event", record)

    async def process(*args, **kwargs):
        security.note_data_scope(scope)
        if collecting:
            return AIChatResponse(reply="Kỳ nào?", draft_id="a" * 36, missing_fields=["start_date"])
        return AIChatResponse(reply="Đã đọc dữ liệu nhân viên")

    monkeypatch.setattr(ChatOrchestrator, "process_chat", process)
    await ai.chat_with_hr_ai(AIChatRequest(message="Tra cứu"), AsyncMock(), actor("HR"), None)
    assert record.await_args.args[4] == scope
