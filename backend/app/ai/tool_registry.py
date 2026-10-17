"""Closed intent-to-tool mapping; model output never names Python callables or SQL."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from app.ai.parsing.personal import asks_lateness, week_period
from app.core.authorization import require_capability
from app.schemas.ai import AIChatAction, AIChatRequest, AIChatResponse
from app.services.ai_employee_tool import AIEmployeeTool
from app.services.ai_knowledge_tool import AIKnowledgeTool
from app.services.ai_report_interpreter import report_answers
from app.services.knowledge_retrieval import normalize


@dataclass(frozen=True)
class ToolContext:
    db: Any
    employee_id: int | None
    owner_user_account_id: int | None
    roles: set[str]
    request: AIChatRequest
    today: date
    # Understood slot values (text) for this action; handlers re-validate them.
    hints: dict | None = None


@dataclass(frozen=True)
class RegisteredTool:
    tool_id: str
    input_schema: type[AIChatRequest]
    capability: str
    needs_employee: bool
    handler: Callable[[ToolContext], Awaitable[AIChatResponse]]


async def _leave_balance(ctx: ToolContext) -> AIChatResponse:
    result = await AIEmployeeTool.get_context(ctx.db, ctx.employee_id, ctx.today)
    balance = result["remaining_leave_days"]
    reply = f"Số dư phép năm {ctx.today.year} của bạn: {balance} ngày." if balance is not None else "Chưa có dữ liệu số dư phép năm của bạn."
    sources = await AIKnowledgeTool.sources(ctx.db, ctx.roles, ctx.today, "chính sách phép năm nghỉ phép")
    return AIChatResponse(reply=reply, sources=sources,
                          action=AIChatAction(action_type="SHOW_DATA", data={"type": "LEAVE_BALANCE", "balance": balance}))


_DAY_STATUS = {"PRESENT": "đủ công", "HALF_DAY": "nửa công", "INCOMPLETE": "thiếu lượt chấm công", "ABSENT": "vắng",
               "ON_LEAVE": "nghỉ phép", "REMOTE": "làm việc từ xa", "HOLIDAY": "ngày lễ"}


def attendance_period(message: str, today: date) -> tuple[date, date]:
    """Single day ("hôm qua", "15/10") > week > month wording > month to date."""
    from app.ai.parsing.dates import resolve_rule_date
    text = normalize(message)
    # Attendance already happened, so a bare weekday ("thứ 5") is the latest one, not the next.
    single = (resolve_rule_date(message, today, "past")
              if not re.search(r"\b(?:thang|tuan) (?:nay|truoc)\b", text) else None)
    if single and single.status == "RESOLVED":
        start = end = date.fromisoformat(single.value)
    elif week := week_period(text, today):
        start, end = week
    else:
        period = report_answers(message, today)
        start = date.fromisoformat(period["start_date"]) if period.get("start_date") else today.replace(day=1)
        end = date.fromisoformat(period["end_date"]) if period.get("end_date") else today
    if start <= today:
        end = min(end, today)  # A future-only period ("ngày mai") stays as asked and reads as no data yet.
    if end < start or start.year != end.year:
        raise HTTPException(422, "INVALID_INPUT")
    return start, end


def attendance_reply(result: dict, start: date, end: date, lateness: bool) -> str:
    if start == end:
        day = next(iter(result.get("days") or []), None)
        if day is None:
            lines = [f"Ngày {start:%d/%m/%Y}: chưa có dữ liệu chấm công."]
        else:
            lines = [f"Ngày {start:%d/%m/%Y}: **{_DAY_STATUS.get(day['status'], day['status'])}**.",
                     f"- Check-in: {day['check_in'] or 'chưa ghi nhận'}",
                     f"- Check-out: {day['check_out'] or 'chưa ghi nhận'}"]
    else:
        counts = result.get("status_counts") or {"PRESENT": result["present_days"], "INCOMPLETE": len(result["incomplete_dates"])}
        recorded = result.get("recorded_days")
        if recorded == 0:
            return f"Từ {start:%d/%m/%Y} đến {end:%d/%m/%Y}: chưa có dữ liệu chấm công nào được ghi nhận."
        lines = [f"Chấm công từ {start:%d/%m/%Y} đến {end:%d/%m/%Y}" + (f" ({recorded} ngày có dữ liệu):" if recorded is not None else ":")]
        lines += [f"- {_DAY_STATUS[status].capitalize()}: **{counts[status]}** ngày" for status in _DAY_STATUS if counts.get(status)]
        incomplete = [date.fromisoformat(value).strftime("%d/%m") for value in result["incomplete_dates"]]
        if incomplete:
            lines.append(f"Các ngày thiếu lượt: {', '.join(incomplete)}. Bạn có thể tạo giải trình cho những ngày này.")
    if lateness:
        # Lateness rules are still undecided (PROJECT_CONTEXT §7): show recorded times only.
        lines.append("Hệ thống chưa có quy tắc đi muộn/về sớm chính thức nên tôi không tự đếm số lần đi muộn. "
                     "Giờ check-in/check-out từng ngày có trong màn hình Chấm công.")
    lines.append("Đây là dữ liệu đã ghi nhận, chưa phải kết quả chốt công.")
    return "\n".join(lines)


async def _attendance_summary(ctx: ToolContext) -> AIChatResponse:
    start, end = attendance_period(ctx.request.message, ctx.today)
    result = await AIEmployeeTool.get_context(ctx.db, ctx.employee_id, ctx.today,
                                              attendance_start=start, attendance_end=end)
    incomplete = result["incomplete_dates"]
    sources = await AIKnowledgeTool.sources(ctx.db, ctx.roles, ctx.today, "quy định chấm công")
    return AIChatResponse(
        reply=attendance_reply(result, start, end, asks_lateness(normalize(ctx.request.message))),
        action=AIChatAction(action_type="SHOW_DATA", data={"type": "ATTENDANCE_SUMMARY",
                                                       "present_days": result["present_days"], "incomplete": incomplete}), sources=sources)


async def _start_leave(ctx: ToolContext) -> AIChatResponse:
    from app.services.ai_service import AIService
    if ctx.owner_user_account_id is None or ctx.db is None:
        raise HTTPException(403, "PERMISSION_DENIED")
    return await AIService._start_draft(ctx.db, ctx.employee_id, ctx.owner_user_account_id, "DRAFT_LEAVE", ctx.request, ctx.hints)


async def _start_fix(ctx: ToolContext) -> AIChatResponse:
    from app.services.ai_service import AIService
    if ctx.owner_user_account_id is None or ctx.db is None:
        raise HTTPException(403, "PERMISSION_DENIED")
    return await AIService._start_draft(ctx.db, ctx.employee_id, ctx.owner_user_account_id, "DRAFT_FIX", ctx.request, ctx.hints)


_REQUEST_STATUS = {"PENDING": "chờ quản lý duyệt", "APPROVED": "đã duyệt", "REJECTED": "bị từ chối", "CANCELLED": "đã hủy"}
_SESSIONS = {"MORNING": "sáng", "AFTERNOON": "chiều", "FULL_DAY": "cả ngày"}


def leave_status_reply(requests: list[dict]) -> AIChatResponse:
    if not requests:
        reply = "Bạn chưa có đơn nghỉ phép nào."
    else:
        reply = "Các đơn nghỉ gần nhất của bạn:\n" + "\n".join(
            f"- {date.fromisoformat(item['leave_date']):%d/%m/%Y} ({_SESSIONS.get(item['session'], item['session'])}), "
            f"{item['leave_name']}: **{_REQUEST_STATUS.get(item['status'], item['status'])}**" for item in requests)
    return AIChatResponse(reply=reply, action=AIChatAction(action_type="NAVIGATE", data={"path": "/leaves"}))


async def _leave_status(ctx: ToolContext) -> AIChatResponse:
    return leave_status_reply(await AIEmployeeTool.recent_leave_requests(ctx.db, ctx.employee_id))


async def _open_knowledge(ctx: ToolContext) -> AIChatResponse:
    return AIChatResponse(reply="Mở màn hình quản lý tài liệu nội quy.",
                          action=AIChatAction(action_type="OPEN_KNOWLEDGE", data={"path": "/knowledge"}))


TOOLS = {
    "LEAVE_BALANCE": RegisteredTool("leave.read_self", AIChatRequest, "leave.read_self", True, _leave_balance),
    "ATTENDANCE_SUMMARY": RegisteredTool("attendance.read_self", AIChatRequest, "attendance.read_self", True, _attendance_summary),
    "DRAFT_LEAVE": RegisteredTool("leave.draft_self", AIChatRequest, "leave.draft_self", True, _start_leave),
    "DRAFT_FIX": RegisteredTool("attendance.draft_fix_self", AIChatRequest, "attendance.draft_fix_self", True, _start_fix),
    "LEAVE_STATUS": RegisteredTool("leave.read_self", AIChatRequest, "leave.read_self", True, _leave_status),
    "OPEN_KNOWLEDGE": RegisteredTool("knowledge.manage", AIChatRequest, "knowledge.manage", False, _open_knowledge),
}


async def execute_registered(intent: str, ctx: ToolContext) -> AIChatResponse | None:
    tool = TOOLS.get(intent)
    if tool is None:
        return None
    require_capability(ctx.roles, tool.capability)
    if tool.needs_employee and ctx.employee_id is None:
        raise HTTPException(403, "PERMISSION_DENIED")
    return await tool.handler(ctx)
