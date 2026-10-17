"""Owner-bound report tools; Python parses common filters, Gemini supplies typed hints."""
from sqlalchemy import select
from datetime import datetime, timezone
from calendar import monthrange
from datetime import date
from uuid import uuid5, NAMESPACE_URL
from app.services.report_access import authorized_run
from app.models.knowledge import ReportRun

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.ai import AIChatAction, AIChatResponse
from app.schemas.reports import ReportRunCreate
from app.services.ai_draft_service import AIDraftService
from app.services.report_catalog import report_catalog
from app.services.report_run_service import ReportRunService
from app.services.ai_report_interpreter import report_answers, ReportPromptInterpreter, GeminiReportInterpreter

REQUIRED = ("kind", "start_date", "end_date", "scope")
QUESTIONS = {
    "kind": "Bạn muốn tạo loại báo cáo nào? Hãy chọn một loại được cấp quyền bên dưới.",
    "start_date": "Bạn muốn báo cáo kỳ nào? Có thể chọn tháng này, tháng trước hoặc nhập hai ngày YYYY-MM-DD đến YYYY-MM-DD.",
    "end_date": "Vui lòng cho biết ngày kết thúc theo YYYY-MM-DD.",
    "scope": "Bạn muốn báo cáo trong phạm vi nào? Hãy chọn phạm vi được cấp quyền bên dưới.",
}


def suggestion_report_defaults(user, message, today):
    params = report_answers(message, today)
    kind = params.get("kind")
    if kind is None:
        return {}
    definition = next((item for item in report_catalog(user)["reports"] if item["kind"] == kind), None)
    if definition is None:
        return {}
    params.setdefault("scope", definition["default_scope"])
    if kind == "HEADCOUNT":
        params.setdefault("start_date", today.isoformat())
        params.setdefault("end_date", today.isoformat())
    return params


# Replaceable adapter; report execution depends on the interface, not the provider SDK.
_REPORT_INTERPRETER: ReportPromptInterpreter = GeminiReportInterpreter()


async def interpret_report_prompt(message, today, user, current=None):
    return await _REPORT_INTERPRETER.interpret(message, today, user, current)


def revised_report_params(current, answers):
    """A stated scope replaces a selected employee, even if scope is unchanged."""
    params = {**current, **answers}
    if "employee_id" not in answers and ("scope" in answers or params.get("kind") not in {"ATTENDANCE", "LEAVE", "ATTENDANCE_FIX"}):
        params.pop("employee_id", None)
    kind = params.get("kind")
    if kind != current.get("kind") and kind in {"MY_PAYSLIP", "PAYROLL_SUMMARY"}:
        if "scope" not in answers:
            params["scope"] = "SELF" if kind == "MY_PAYSLIP" else "COMPANY"
        if kind == "MY_PAYSLIP" and "department_id" not in answers:
            params.pop("department_id", None)
        if not {"start_date", "end_date"} & answers.keys():
            try:
                start, end = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
                full_month = start.day == 1 and end == start.replace(day=monthrange(start.year, start.month)[1])
            except (KeyError, ValueError):
                full_month = False
            if not full_month:
                # Ask for a payroll month instead of silently widening the old
                # period or letting an inherited partial month fail with 422.
                params.pop("start_date", None)
                params.pop("end_date", None)
    return params


def run_params(params):
    """Draft fields that are ReportRunCreate filters (purpose only steers the reply)."""
    return {key: value for key, value in params.items() if key != "purpose"}


class AIReportDraftService:
    @staticmethod
    def validate_access(user, params):
        definitions = report_catalog(user)["reports"]
        if not definitions:
            raise HTTPException(403, "PERMISSION_DENIED")
        definition = next((item for item in definitions if item["kind"] == params.get("kind")), None)
        if params.get("kind") and definition is None:
            raise HTTPException(403, "PERMISSION_DENIED")
        scopes = definition["scopes"] if definition else {scope for item in definitions for scope in item["scopes"]}
        if params.get("scope") and params["scope"] not in scopes:
            raise HTTPException(403, "PERMISSION_DENIED")
        if definition and "scope" not in params and len(scopes) == 1:
            params["scope"] = scopes[0]
        return params

    @staticmethod
    async def start(db, user, message, today, initial=None):
        AIReportDraftService.validate_access(user, {})
        # A period already resolved from the understood request needs no second model call.
        known_period = bool(initial) and {"start_date", "end_date"} <= initial.keys()
        interpreted = {} if known_period else await interpret_report_prompt(message, today, user, initial)
        params = {**interpreted, **report_answers(message, today, initial), **(initial or {})}
        if params.get("kind") == "HEADCOUNT":
            params.setdefault("start_date", today.isoformat())
            params.setdefault("end_date", today.isoformat())
        AIDraftService._validate_command_and_params("DRAFT_REPORT", params)
        AIReportDraftService.validate_access(user, params)
        missing = [key for key in REQUIRED if key not in params]
        draft = await AIDraftService.create_draft(db, user.user_account_id, "DRAFT_REPORT", params, missing)
        if draft.status == "READY":
            # Initial POST replay after an acknowledged or lost response:
            # reuse the exact persisted run without creating a second one.
            run_id = uuid5(NAMESPACE_URL, f"hr-ai-report-draft:{draft.draft_id}").hex
            run = await authorized_run(db, user, run_id)
            req = ReportRunCreate.model_validate(run_params(draft.typed_params))
            return await AIReportDraftService.finished(db, user, draft, req, run)
        return await AIReportDraftService.finish_or_ask(db, user, draft)

    @staticmethod
    async def continue_draft(db, user, draft, message, today, inputs=None):
        if draft.status != "COLLECTING":
            raise HTTPException(409, "AI_DRAFT_NOT_COLLECTING")
        AIReportDraftService.validate_access(user, {})
        answers = {**await interpret_report_prompt(message, today, user, draft.typed_params),
                   **report_answers(message, today, draft.typed_params, draft.missing_fields)}
        if inputs:
            AIDraftService._validate_command_and_params("DRAFT_REPORT", inputs)
            answers.update(inputs)
        params = revised_report_params(draft.typed_params, answers)
        AIDraftService._validate_command_and_params("DRAFT_REPORT", params)
        AIReportDraftService.validate_access(user, params)
        missing = [key for key in REQUIRED if key not in params]
        asked = draft.missing_fields[0] if draft.missing_fields else None
        if answers or missing != draft.missing_fields:
            draft = await AIDraftService.update_draft(db, draft.draft_id, user.user_account_id, params, missing)
        # Say what was understood instead of silently repeating the same question.
        if not answers:
            prefix = "Tôi chưa nhận ra thông tin cho bước này. "
        elif asked and asked not in answers:
            noted = {"scope": "phạm vi", "kind": "loại báo cáo", "start_date": "kỳ báo cáo", "end_date": "kỳ báo cáo"}
            prefix = "Đã ghi nhận " + ", ".join(dict.fromkeys(noted.get(key, key) for key in answers)) + ". "
        else:
            prefix = ""
        return await AIReportDraftService.finish_or_ask(db, user, draft, prefix=prefix)

    @staticmethod
    async def revise_run(db, user, run_id, message, today):
        AIReportDraftService.validate_access(user, {})
        run = await db.scalar(select(ReportRun).where(
            ReportRun.run_id == run_id, ReportRun.owner_user_account_id == user.user_account_id))
        if run is None:
            raise HTTPException(404, "REPORT_NOT_FOUND")
        expires = run.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if run.status != "READY" or expires <= datetime.now(timezone.utc):
            raise HTTPException(410, "REPORT_EXPIRED")
        current = {"kind": run.kind, "scope": run.scope,
                   **{k: v for k, v in run.filters.items() if v is not None}}
        answers = {**await interpret_report_prompt(message, today, user, current),
                   **report_answers(message, today, current)}
        if not answers:
            return AIChatResponse(reply="Bạn muốn đổi kỳ, loại báo cáo hay phạm vi? Ví dụ: đổi sang tháng trước.",
                                  message_code="REPORT_CHANGE_REQUIRED")
        params = revised_report_params(current, answers)
        AIReportDraftService.validate_access(user, params)
        return await AIReportDraftService.start(db, user, "", today, params)

    @staticmethod
    async def finish_or_ask(db, user, draft, prefix=""):
        # Reject a completed draft before ReportRunService can commit a new
        # snapshot in its independent storage transaction.
        if draft.status != "COLLECTING":
            raise HTTPException(409, "AI_DRAFT_NOT_COLLECTING")
        AIReportDraftService.validate_access(user, draft.typed_params)
        if draft.missing_fields:
            field = draft.missing_fields[0]
            definitions = report_catalog(user)["reports"]
            options = []
            if field == "kind":
                options = [{"field": field, "value": item["kind"], "label": item["label"]} for item in definitions if not draft.typed_params.get("scope") or draft.typed_params["scope"] in item["scopes"]]
            elif field == "scope":
                definition = next(item for item in definitions if item["kind"] == draft.typed_params["kind"])
                labels = {"SELF": "Bản thân", "DIRECT_REPORTS": "Nhân viên trực tiếp", "COMPANY": "Toàn công ty"}
                options = [{"field": field, "value": scope, "label": labels[scope]} for scope in definition["scopes"]]
            hint = " Gửi “hủy” nếu bạn muốn dừng báo cáo này." if prefix.startswith("Tôi chưa nhận ra") else ""
            return AIChatResponse(reply=prefix + QUESTIONS[field] + hint, draft_id=draft.draft_id, draft_revision=draft.revision, missing_fields=draft.missing_fields, input_options=options, message_code=f"REPORT_{field.upper()}_REQUIRED")
        try:
            req = ReportRunCreate.model_validate(run_params(draft.typed_params))
        except ValidationError as exc:
            raise HTTPException(422, "INVALID_INPUT") from exc
        result = await ReportRunService.create(db, user, req, source_draft_id=draft.draft_id)
        await AIDraftService.mark_ready(db, draft.draft_id, user.user_account_id)
        return await AIReportDraftService.finished(db, user, draft, req, result["run"])

    @staticmethod
    async def finished(db, user, draft, req, run):
        """A chart/statistics request is answered with the analysis of the new run."""
        response = AIReportDraftService.completed_response(draft, req, run)
        if draft.typed_params.get("purpose") != "ANALYZE":
            return response
        from app.services.ai_analysis_tool import AIAnalysisTool, analysis_summary
        analysis = await AIAnalysisTool.execute(db, user, run.run_id)
        return response.model_copy(update={
            "reply": analysis_summary(analysis),
            "report_analysis": {key: analysis.get(key) for key in ("row_count", "metrics", "frequencies", "chart")},
            "message_code": "REPORT_ANALYZED",
        })

    @staticmethod
    def completed_response(draft, req, run):
        scope_label = {"SELF": "bản thân", "DIRECT_REPORTS": "nhân viên trực tiếp", "COMPANY": "toàn công ty"}[req.scope]
        if req.employee_id is not None:
            scope_label = "nhân viên đã chọn"
        return AIChatResponse(reply=f"Đã tạo báo cáo từ {req.start_date:%d/%m/%Y} đến {req.end_date:%d/%m/%Y}, phạm vi {scope_label}. Bạn có thể xem trước và tải Excel.", action=AIChatAction(action_type="OPEN_REPORT", data={"path": "/reports", **run_params(draft.typed_params), "run_id": run.run_id}))
