"""Chat routing across authenticated drafts and registered HR tools."""

import re
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.gemini import record
from app.services.ai_request_security import request_context
from app.ai.tool_registry import ToolContext, attendance_period, attendance_reply, execute_registered, leave_status_reply
from app.core.config import settings
from app.core.authorization import capabilities
from app.schemas.ai import AIChatAction, AIChatRequest, AIChatResponse
from app.schemas.reports import ReportRunCreate
from app.services.ai_access import require_known_role, require_reviewer_role
from app.services.ai_draft_service import AIDraftService
from app.services.ai_report_draft_service import AIReportDraftService, report_answers, suggestion_report_defaults
from app.services import ai_service as ai_service_module
from app.services.ai_service import AIService, draft_reason_match, is_leave_balance_query, requested_date
from app.services.ai_suggestions import SUGGESTIONS, resolve_suggestion
from app.services.knowledge_retrieval import normalize
from app.ai.parsing.lexicon import canonical
from app.ai.parsing.personal import asks_lateness, is_attendance_query, is_team_records_query, is_leave_status_query, is_own_salary_query, is_remote_request
from app.services.ai_employee_tool import AIEmployeeTool
from app.services.report_run_service import ReportRunService
from app.services.ai_employee_query import answer_employee_query, mentions_employee


DENIED_REPLY = "Bạn không có quyền thực hiện yêu cầu này hoặc truy cập dữ liệu được yêu cầu. Vui lòng chọn chức năng trong phạm vi quyền của bạn."


def is_approval_queue(text: str) -> bool:
    return (any(term in text for term in ("don dang cho toi duyet", "don nghi phep dang cho toi duyet", "don cho toi duyet",
                                          "mo danh sach don cho duyet", "hang doi duyet"))
            or bool(re.search(r"\bdon\b.{0,30}\b(?:cho|can) toi duyet\b", text)))


class ChatOrchestrator:
    @staticmethod
    async def _readonly_reply(db, text, employee_id, actor_caps) -> AIChatResponse | None:
        """Own leave-request status and approval queues: read/navigate only, safe mid-draft."""
        if "cho toi duyet" in text and any(term in text for term in ("giai trinh", "cham cong", "cong")):
            if "report.read_direct_reports" not in actor_caps:
                return AIChatResponse(reply=DENIED_REPLY, answer_mode="OUT_OF_SCOPE")
            return AIChatResponse(reply="Mở danh sách giải trình chấm công đang chờ quản lý trực tiếp xử lý.", action=AIChatAction(action_type="OPEN_APPROVALS", data={"path": "/attendance", "target": "attendance", "tab": "approvals"}))
        if is_approval_queue(text):
            if "report.read_direct_reports" not in actor_caps:
                return AIChatResponse(reply=DENIED_REPLY, answer_mode="OUT_OF_SCOPE")
            return AIChatResponse(reply="Mở danh sách đơn nghỉ phép đang chờ quản lý trực tiếp xử lý.", action=AIChatAction(action_type="OPEN_APPROVALS", data={"path": "/leaves", "target": "leave", "tab": "approvals"}))
        if is_leave_status_query(text):
            if employee_id is None:
                raise HTTPException(403, "PERMISSION_DENIED")
            return leave_status_reply(await AIEmployeeTool.recent_leave_requests(db, employee_id))
        return None

    @staticmethod
    async def process_chat(db: AsyncSession, employee_id: int, req: AIChatRequest, roles: set[str] | None = None, owner_user_account_id: int | None = None, authenticated_user=None) -> AIChatResponse:
        # A replay of the same authenticated client operation gets the same
        # draft ID. Never trust a key without binding it to its owner.
        if req.request_key and owner_user_account_id is not None:
            with request_context(f"chat:{owner_user_account_id}:{req.request_key}"):
                return await ChatOrchestrator._process_chat(db, employee_id, req, roles, owner_user_account_id, authenticated_user)
        return await ChatOrchestrator._process_chat(db, employee_id, req, roles, owner_user_account_id, authenticated_user)

    @staticmethod
    async def _process_chat(db: AsyncSession, employee_id: int, req: AIChatRequest, roles: set[str] | None = None, owner_user_account_id: int | None = None, authenticated_user=None) -> AIChatResponse:
        roles = roles or set()
        require_known_role(roles)
        actor_caps = capabilities(roles)
        policy_ids = {"leave_policy", "attendance_policy", "report_security"}
        policy_question = req.suggestion_id in policy_ids
        from_suggestion = bool(req.suggestion_id)
        if req.suggestion_id:
            definition = resolve_suggestion(req.suggestion_id, roles, employee_id)
            if req.inputs and req.suggestion_id not in {"draft_leave", "attendance_fix", "my_attendance_report", "my_payslip", "team_attendance_report", "team_leave_report", "headcount_report", "company_attendance_report", "payroll_summary"}:
                raise HTTPException(422, "AI_DRAFT_FIELD_INVALID")
            req = req.model_copy(update={"message": definition.prompt, "suggestion_id": None})
        today = ai_service_module.business_today()
        if settings.GEMINI_ENABLED and settings.GEMINI_SEMANTIC_ENABLED and not from_suggestion and not req.report_run_id:
            from app.ai.semantic_router import process_semantic_chat, process_semantic_draft_turn
            if not req.draft_id:
                return await process_semantic_chat(db, employee_id, req, roles, owner_user_account_id, authenticated_user, today)
            if owner_user_account_id is not None:
                # Lock-in: an open form receives every message unless it clearly asks something else.
                return await process_semantic_draft_turn(db, employee_id, req, roles, owner_user_account_id, authenticated_user, today)
        text = canonical(req.message)
        explicit_draft_reply = bool(req.draft_id and (req.inputs or draft_reason_match(req.message) is not None))
        policy_question = policy_question or any(text == canonical(SUGGESTIONS[key].prompt) for key in policy_ids)
        policy_question = policy_question or any(term in text for term in ("chinh sach", "quy dinh", "noi quy", "quy trinh", "thu tuc", "huong dan", "dieu kien")) or bool(re.search(r"\b(?:cach|lam the nao|lam sao)\b.{0,40}\b(?:nghi|phep|cham cong|giai trinh)\b", text))
        knowledge_management = any(term in text for term in ("quan ly tai lieu", "quan tri tai lieu"))
        explicit_report = any(term in text for term in ("tao bao cao", "mo bao cao", "xuat bao cao", "lap bao cao",
                                                        "xuat phieu luong", "tao phieu luong", "xem phieu luong"))
        report_request = explicit_report or (not policy_question and any(term in text for term in ("thong ke", "phan tich", "bieu do")))
        if report_request or req.report_run_id:
            require_reviewer_role(roles)
        if policy_question and not knowledge_management and not report_request and not req.draft_id and not req.report_run_id:
            return await AIService._answer_knowledge(db, roles, today, req, policy_question=True)

        # Personal lookup/drafting has no target parameter: never silently answer
        # with the actor's records when the request names somebody else.
        if not explicit_draft_reply and mentions_employee(req.message):
            if not req.draft_id and not req.report_run_id:
                return await answer_employee_query(db, authenticated_user, req, today)
            return AIChatResponse(reply="Bạn không có quyền thực hiện yêu cầu này hoặc truy cập dữ liệu được yêu cầu. Vui lòng chọn chức năng trong phạm vi quyền của bạn.", answer_mode="OUT_OF_SCOPE")
        # Resolve name-first requests before a balance/report keyword can turn
        # them into the actor's own records or an unfiltered company report.
        if (settings.GEMINI_ENABLED and authenticated_user is not None and not from_suggestion
                and not req.draft_id and not req.report_run_id):
            employee_answer = await answer_employee_query(db, authenticated_user, req, today, required=False)
            if employee_answer is not None:
                return employee_answer
        if (not from_suggestion and not req.draft_id and not req.report_run_id and not policy_question
                and is_leave_balance_query(text)
                and not re.search(r"\b(?:cua toi|cua minh|ban than|toi con|minh con|toan cong ty|nhom|nhan vien truc tiep)\b", text)):
            return AIChatResponse(reply="Vui lòng nêu rõ bản thân, mã nhân viên hoặc phạm vi nhóm/công ty cần xem. Tôi chưa tra cứu dữ liệu khi chưa rõ đối tượng.",
                                  status="NEEDS_INPUT", message_code="TARGET_REQUIRED",
                                  # One-click answer for the common case; still an explicit choice by the user.
                                  clarification_options=["Tôi còn bao nhiêu ngày phép?"])
        if employee_id is None and is_leave_balance_query(text):
            raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
        if employee_id is None and not policy_question and not report_request and not req.draft_id and any(term in text for term in ("cua toi", "xin nghi", "giai trinh", "so du phep")):
            raise HTTPException(status_code=403, detail="PERMISSION_DENIED")

        if req.report_run_id and not req.draft_id:
            if authenticated_user is None:
                raise HTTPException(403, "PERMISSION_DENIED")
            analysis_requested = any(term in text for term in ("phan tich", "bieu do", "thong ke", "analyze", "chart"))
            if not analysis_requested and not report_answers(req.message, today) and settings.GEMINI_ENABLED:
                try:
                    analysis_requested = await AIService._classify_free_intent(req.message) == "ANALYZE_REPORT"
                except HTTPException as exc:
                    record("classify_intent", "FALLBACK_USED", category=str(exc.detail))
                    # Revision still asks for explicit filter changes.
            if analysis_requested:
                from app.services.ai_analysis_tool import AIAnalysisTool, analysis_summary
                analysis = await AIAnalysisTool.execute(db, authenticated_user, req.report_run_id)
                run = analysis.get("run")
                return AIChatResponse(
                    reply=analysis_summary(analysis),
                    # The client opens this run with its analysis panel already loaded.
                    action=AIChatAction(action_type="OPEN_REPORT", data={"path": "/reports", **run}) if run else None,
                    report_analysis={key: analysis.get(key) for key in ("row_count", "metrics", "frequencies", "chart")} if run else None,
                    message_code="REPORT_ANALYZED")
            return await AIReportDraftService.revise_run(db, authenticated_user, req.report_run_id, req.message, today)

        # A new question while collecting a draft is NOT a value for the
        # remaining form field (especially the free-text "reason" field).
        if (req.draft_id and not explicit_draft_reply and owner_user_account_id is not None):
            interruption = policy_question and not knowledge_management and not report_request
            competing_action = (
                report_request or knowledge_management or
                (bool(re.search(r"\b(?:xin nghi|tao don nghi|tao giai trinh|quen check-in|quen check-out)\b", text))
                 and not (req.message.lower().startswith("lý do")))
            )
            if interruption or competing_action:
                active = await AIDraftService.get_draft(db, req.draft_id, owner_user_account_id)
                if active.revision != req.draft_revision:
                    raise HTTPException(409, "AI_DRAFT_REVISION_CONFLICT")
                if interruption:
                    response = await AIService._answer_knowledge(
                        db, roles, today, req, policy_question=True)
                    return response.model_copy(update={
                        "draft_id": active.draft_id,
                        "draft_revision": active.revision,
                        "missing_fields": active.missing_fields,
                        "status": "NEEDS_INPUT",
                    })
                # Explicitly ask for a switch instead of consuming the prompt
                # as an answer to the old draft or accidentally starting a new run.
                if (active.command == "DRAFT_REPORT" and
                    re.search(r"\b(?:xin nghi|tao don nghi|tao giai trinh)\b", text)
                   ) or (active.command != "DRAFT_REPORT" and
                         (report_request or knowledge_management)):
                    return AIChatResponse(
                        reply="Bạn đang có một bản nháp chưa hoàn tất. Hãy tiếp tục trả lời trường còn thiếu, hoặc gửi ‘hủy’ trước khi bắt đầu tác vụ mới.",
                        draft_id=active.draft_id,
                        draft_revision=active.revision,
                        missing_fields=active.missing_fields,
                        status="NEEDS_INPUT",
                        message_code="DRAFT_SWITCH_CONFIRMATION_REQUIRED",
                    )

        readonly = (None if explicit_draft_reply or policy_question
                    else await ChatOrchestrator._readonly_reply(db, text, employee_id, actor_caps))
        if req.draft_id and readonly is not None:
            # Status and queue lookups never consume the open draft; the user answers it afterwards.
            if owner_user_account_id is None:
                raise HTTPException(403, "PERMISSION_DENIED")
            draft = await AIDraftService.get_draft(db, req.draft_id, owner_user_account_id)
            if draft.revision != req.draft_revision:
                raise HTTPException(409, "AI_DRAFT_REVISION_CONFLICT")
            return readonly.model_copy(update={"draft_id": draft.draft_id, "draft_revision": draft.revision,
                                               "missing_fields": draft.missing_fields, "status": "NEEDS_INPUT"})

        personal_lookup = is_leave_balance_query(text) or is_attendance_query(text)
        if req.draft_id and personal_lookup and not explicit_draft_reply:
            if owner_user_account_id is None:
                raise HTTPException(403, "PERMISSION_DENIED")
            draft = await AIDraftService.get_draft(db, req.draft_id, owner_user_account_id)
            if draft.revision != req.draft_revision:
                raise HTTPException(409, "AI_DRAFT_REVISION_CONFLICT")
            intent = "LEAVE_BALANCE" if is_leave_balance_query(text) else "ATTENDANCE_SUMMARY"
            result = await execute_registered(intent, ToolContext(db, employee_id, owner_user_account_id,
                roles, req.model_copy(update={"draft_id": None, "draft_revision": None, "inputs": None}), today))
            assert result is not None  # Fixed registry IDs; never supplied as Python names by the model.
            return result.model_copy(update={"draft_id": draft.draft_id, "draft_revision": draft.revision,
                                             "missing_fields": draft.missing_fields, "status": "NEEDS_INPUT"})

        if req.draft_id:
            if owner_user_account_id is None:
                return AIChatResponse(reply="Bản nháp không khả dụng. Vui lòng bắt đầu lại từ gợi ý soạn đơn.", answer_mode="OUT_OF_SCOPE")
            return await AIService._continue_draft(db, owner_user_account_id, req.draft_id, req.message, employee_id, req.draft_revision, req.inputs, authenticated_user, today)

        if text in {"huy", "huy ban nhap", "bo qua", "dung lai"}:
            return AIChatResponse(reply="Hiện không có bản nháp nào đang mở để hủy. Bạn có thể bắt đầu yêu cầu mới.")

        if readonly is not None:
            return readonly

        if is_team_records_query(text) and not report_request and not policy_question and "report.read_direct_reports" in actor_caps:
            # Team records are read through scoped report runs, not free-form chat answers.
            return AIChatResponse(
                reply="Dữ liệu của nhân viên trong nhóm được tra cứu qua báo cáo theo phạm vi bạn được cấp. Chọn báo cáo bên dưới, hoặc nêu mã/họ tên một nhân viên.",
                clarification_options=["Xuất báo cáo chấm công nhóm tháng này", "Xuất báo cáo nghỉ phép nhóm tháng này"],
                status="NEEDS_INPUT", message_code="TEAM_REPORT_SUGGESTED")

        if is_own_salary_query(text) and not policy_question:
            # Salary figures come only from released payslip snapshots, via the report flow.
            return AIChatResponse(
                reply="Lương của bạn được xem qua phiếu lương cá nhân, sau khi HR chốt kỳ lương. Chọn kỳ bên dưới để tạo phiếu lương.",
                clarification_options=["Xuất phiếu lương của tôi tháng trước", "Xuất phiếu lương của tôi tháng này"],
                status="NEEDS_INPUT", message_code="PAYSLIP_PERIOD_REQUIRED")

        if any(term in text for term in ["quan ly tai lieu", "quan tri tai lieu", "tai lieu noi quy"]):
            if "knowledge.manage" not in actor_caps:
                return AIChatResponse(reply="Bạn không có quyền thực hiện yêu cầu này hoặc truy cập dữ liệu được yêu cầu. Vui lòng chọn chức năng trong phạm vi quyền của bạn.", answer_mode="OUT_OF_SCOPE")
            return AIChatResponse(reply="Mở màn hình quản lý tài liệu nội quy.", action=AIChatAction(action_type="OPEN_KNOWLEDGE", data={"path": "/knowledge"}))

        if report_request:
            if authenticated_user is not None:
                # An unstated scope is a missing draft field: the draft asks for it
                # with option buttons and the answer continues the same draft.
                initial = {}
                if from_suggestion:
                    initial = suggestion_report_defaults(authenticated_user, req.message, today)
                if req.inputs:
                    initial.update(req.inputs)
                return await AIReportDraftService.start(db, authenticated_user, req.message, today, initial)
            if "toan cong ty" in text and "report.read_company" not in actor_caps or any(term in text for term in ("nhom", "truc tiep")) and "report.read_direct_reports" not in actor_caps:
                return AIChatResponse(reply="Bạn không có quyền thực hiện yêu cầu này hoặc truy cập dữ liệu được yêu cầu. Vui lòng chọn chức năng trong phạm vi quyền của bạn.", answer_mode="OUT_OF_SCOPE")
            report_kind = "PAYROLL_SUMMARY" if "tong hop luong" in text else "MY_PAYSLIP" if "phieu luong" in text else "HEADCOUNT" if "headcount" in text or "nhan su theo phong ban" in text else "APPROVAL_QUEUE" if "cho duyet" in text else "ATTENDANCE_FIX" if "giai trinh" in text else "LEAVE" if "phep" in text or "nghi" in text else "ATTENDANCE"
            if report_kind == "PAYROLL_SUMMARY" and "report.read_company" not in actor_caps or report_kind in {"HEADCOUNT", "APPROVAL_QUEUE"} and "report.read_direct_reports" not in actor_caps:
                return AIChatResponse(reply="Bạn không có quyền thực hiện yêu cầu này hoặc truy cập dữ liệu được yêu cầu. Vui lòng chọn chức năng trong phạm vi quyền của bạn.", answer_mode="OUT_OF_SCOPE")
            if not from_suggestion and not re.search(r"\b(?:cua toi|cua minh|ban than|toan cong ty|nhom|nhan vien truc tiep)\b", text):
                return AIChatResponse(reply="Vui lòng nêu rõ nhân viên hoặc phạm vi bản thân/nhóm/công ty cần báo cáo.",
                                      status="NEEDS_INPUT", message_code="TARGET_REQUIRED")
            payroll = report_kind in {"MY_PAYSLIP", "PAYROLL_SUMMARY"}
            end = today.replace(day=1) - timedelta(days=1) if "thang truoc" in text else today
            start = end.replace(day=1)
            if payroll:
                from calendar import monthrange
                end = start.replace(day=monthrange(start.year, start.month)[1])
            start_date = start.isoformat()
            end_date = end.isoformat()
            if authenticated_user is not None and any(term in text for term in ("tao bao cao", "xuat bao cao", "lap bao cao")):
                # Explicitly stated defaults; arbitrary dates are not silently replaced.
                if any(term in text for term in ("nam truoc", "quy", "tu ngay")) or re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}\b", req.message):
                    return AIChatResponse(reply="Hãy chọn kỳ cụ thể trong màn hình báo cáo trước khi tạo.", action=AIChatAction(action_type="OPEN_REPORT", data={"path": "/reports", "kind": report_kind, "start_date": start_date, "end_date": end_date}))
                requested_scope = "COMPANY" if report_kind == "PAYROLL_SUMMARY" else "SELF" if report_kind == "MY_PAYSLIP" else "DIRECT_REPORTS" if report_kind == "APPROVAL_QUEUE" or "truc tiep" in text or "nhom" in text else "COMPANY" if "toan cong ty" in text else "SELF"
                result = await ReportRunService.create(db, authenticated_user, ReportRunCreate(kind=report_kind, start_date=start, end_date=end, scope=requested_scope))
                return AIChatResponse(reply=f"Đã tạo báo cáo Excel từ dữ liệu đã ghi nhận, kỳ {start_date} đến {end_date}. Mở báo cáo để xem dữ liệu và tải file.", action=AIChatAction(action_type="OPEN_REPORT", data={"path": "/reports", "kind": report_kind, "start_date": start_date, "end_date": end_date, "scope": requested_scope, "run_id": result["run"].run_id}))
            return AIChatResponse(reply="Đã điền sẵn báo cáo và kỳ đã chọn. Hãy kiểm tra phạm vi, bộ lọc và dữ liệu trước khi tạo.", action=AIChatAction(action_type="OPEN_REPORT", data={"path": "/reports", "kind": report_kind, "start_date": start_date, "end_date": end_date}))

        draft_leave = any(term in text for term in ["xin nghi", "nghi sang", "nghi chieu", "nghi ca ngay", "tao don nghi", "lap don nghi", "tao phep", "xin lam viec tu xa", "dang ky lam viec tu xa", "xin remote", "xin wfh", "tao don remote", "tao don wfh"]) or is_remote_request(text) or (
            # "muốn nghỉ tuần sau", "cần nghỉ từ thứ 2 đến thứ 5"; not resignation or a conditional policy question.
            bool(re.search(r"\b(?:muon|can|dang ky)\s+(?:duoc\s+)?nghi\b(?!\s+viec)", text))
            and not re.search(r"\b(?:neu|thi|giay to|can gi|the nao)\b", text))
        draft_fix = any(term in text for term in ["quen quet", "quen cham cong", "quen check-in", "quen check-out", "tao giai trinh", "don giai trinh"]) and "ngay nao" not in text
        if (draft_leave or draft_fix) and not from_suggestion:
            # Bare commands and first-person requests can draft for the actor.
            # A name/unknown subject before the command must not become SELF
            # merely because semantic routing is disabled or unavailable.
            prefix = re.split(
                r"\b(?:xin nghi|nghi sang|nghi chieu|nghi ca ngay|tao don nghi|lap don nghi|tao phep|"
                r"xin lam viec tu xa|dang ky lam viec tu xa|xin remote|xin wfh|tao don remote|tao don wfh|"
                r"quen quet|quen cham cong|quen check-in|quen check-out|tao giai trinh|don giai trinh|"
                r"(?:dang ky |lam viec |di lam |lam )?(?:remote|wfh|tu xa)|(?:muon|can|dang ky) (?:duoc )?nghi)\b",
                text, maxsplit=1,
            )[0].strip()
            prefix = re.sub(
                r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{4})?\b|"
                r"\b(?:hom qua|hom nay|ngay mai|ngay kia|sang mai|chieu mai)\b",
                "", prefix,
            ).strip()
            if not re.fullmatch(r"(?:(?:toi|minh|muon|can|cho|giup|hay|vui long|lam on)\s*)*", prefix):
                return AIChatResponse(
                    reply="Tôi chỉ hỗ trợ soạn đơn cho tài khoản đang đăng nhập. Nếu bạn muốn soạn cho bản thân, hãy nói rõ, ví dụ: Tôi muốn xin nghỉ ngày mai.",
                    status="NEEDS_INPUT", message_code="TARGET_REQUIRED",
                )
        if owner_user_account_id is not None and db is not None and (draft_leave or draft_fix):
            command = "DRAFT_LEAVE" if draft_leave else "DRAFT_FIX"
            return await AIService._start_draft(db, employee_id, owner_user_account_id, command, req)
        if draft_leave:
            target = requested_date(req.message, today)
            if not target:
                return AIChatResponse(reply="Bạn muốn nghỉ ngày nào? Vui lòng gửi lại yêu cầu kèm ngày (YYYY-MM-DD hoặc DD/MM/YYYY) và buổi nghỉ.")
            ctx = await AIService.get_employee_context(db, employee_id, leave_year=date.fromisoformat(target).year)
            session = "MORNING" if "sang" in text else "AFTERNOON" if "chieu" in text else "FULL_DAY"
            amount = Decimal("1") if session == "FULL_DAY" else Decimal("0.5")
            code = AIService._requested_leave_code(req.message) or "ANNUAL"
            if code == "ANNUAL" and ctx["remaining_leave_days"] is None:
                return AIChatResponse(reply="Chưa có số dư phép năm để kiểm tra. Vui lòng liên hệ HR hoặc chọn loại nghỉ trong form.", action=AIChatAction(action_type="NAVIGATE", data={"path": "/leaves"}))
            if code == "ANNUAL" and Decimal(ctx["remaining_leave_days"]) < amount:
                return AIChatResponse(reply="Số dư phép năm không đủ cho yêu cầu này. Bạn có thể chọn nghỉ không lương trong form; tôi không tự chuyển loại nghỉ.", action=AIChatAction(action_type="NAVIGATE", data={"path": "/leaves"}))
            leave_type = next((t for t in ctx["leave_types"] if t["code"] == code), None)
            if not leave_type:
                return AIChatResponse(reply="Loại nghỉ này chưa được cấu hình. Vui lòng liên hệ HR.")
            return AIChatResponse(reply=f"Đã chuẩn bị nháp nghỉ ngày {target}, buổi {session}, loại {leave_type['name']}. Mở form để kiểm tra ngày, buổi và tự nhập lý do trước khi gửi tới quản lý trực tiếp.", action=AIChatAction(action_type="DRAFT_LEAVE", data={"leave_date": target, "session": session, "leave_type_id": leave_type["id"]}))

        if draft_fix:
            target = requested_date(req.message, today)
            if not target:
                return AIChatResponse(reply="Vui lòng gửi lại yêu cầu kèm ngày thiếu lượt công và lượt check-in hoặc check-out.")
            if not any(term in text for term in ["check-in", "check-out", "vao", "ra ve", "luc ve", "khi ve"]):
                return AIChatResponse(reply="Vui lòng nêu rõ lượt cần bổ sung: check-in hay check-out, cùng ngày cần giải trình.")
            event = "CHECK_OUT" if any(term in text for term in ["check-out", "ra ve", "luc ve", "khi ve"]) else "CHECK_IN"
            data = {"work_date": target, "event_type": event, "reason": req.message}
            time_match = re.search(r"\b(\d{1,2})(?::|h)(\d{2})?(?::(\d{2}))?\b", text)
            if time_match:
                hour, minute, second = int(time_match[1]), int(time_match[2] or 0), int(time_match[3] or 0)
                if hour < 24 and minute < 60 and second < 60:
                    data["requested_time"] = f"{hour:02}:{minute:02}:{second:02}"
            return AIChatResponse(reply="Đã chuẩn bị nháp giải trình. Mở form và kiểm tra giờ thực tế cùng lý do trước khi gửi; tôi không suy đoán giờ chấm công.", action=AIChatAction(action_type="DRAFT_FIX", data=data))

        if is_leave_balance_query(text):
            ctx = await AIService.get_employee_context(db, employee_id)
            balance = ctx["remaining_leave_days"]
            reply = f"Số dư phép năm {today.year} của bạn: {balance} ngày." if balance is not None else "Chưa có dữ liệu số dư phép năm của bạn."
            return AIChatResponse(reply=reply, sources=await AIService._policy_sources(db, roles, today, "chính sách phép năm nghỉ phép"), action=AIChatAction(action_type="SHOW_DATA", data={"type": "LEAVE_BALANCE", "balance": balance}))
        if is_attendance_query(text):
            # Same period rules and wording as the registered semantic-path tool.
            start, end = attendance_period(req.message, today)
            ctx = await AIService.get_employee_context(db, employee_id, attendance_start=start, attendance_end=end)
            incomplete = ctx["incomplete_dates"]
            return AIChatResponse(reply=attendance_reply(ctx, start, end, asks_lateness(text)),
                                  action=AIChatAction(action_type="SHOW_DATA", data={"type": "ATTENDANCE_SUMMARY", "present_days": ctx["present_days"], "incomplete": incomplete}),
                                  sources=await AIService._policy_sources(db, roles, today, "quy định chấm công"))

        return await AIService._answer_knowledge(db, roles, today, req, employee_id=employee_id,
                                               owner_user_account_id=owner_user_account_id, authenticated_user=authenticated_user)
