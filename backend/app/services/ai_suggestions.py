"""Server-owned suggestion registry; IDs never grant a capability."""

from dataclasses import dataclass
from fastapi import HTTPException


@dataclass(frozen=True)
class SuggestionDefinition:
    prompt: str
    roles: frozenset[str]
    reference_id: str
    needs_employee: bool = False


ALL = frozenset({"EMPLOYEE", "MANAGER", "HR", "ADMIN"})
REVIEWERS = frozenset({"MANAGER", "HR", "ADMIN"})
EDITORS = frozenset({"HR", "ADMIN"})
CATALOG_VERSION = "v1"
SUGGESTIONS = {
    "leave_balance": SuggestionDefinition("Tôi còn bao nhiêu ngày phép năm?", ALL, "leave_policy", True),
    "draft_leave": SuggestionDefinition("Soạn đơn xin nghỉ phép", ALL, "leave_request", True),
    "attendance_fix": SuggestionDefinition("Tạo giải trình chấm công", ALL, "attendance_policy", True),
    "my_attendance_report": SuggestionDefinition("Tạo báo cáo công của tôi tháng này", REVIEWERS, "report_export", True),
    "my_payslip": SuggestionDefinition("Tạo báo cáo phiếu lương của tôi tháng trước", REVIEWERS, "report_export", True),
    "leave_approval_queue": SuggestionDefinition("Mở các đơn nghỉ phép đang chờ tôi duyệt", REVIEWERS, "leave_request", True),
    "attendance_approval_queue": SuggestionDefinition("Mở các giải trình chấm công đang chờ tôi duyệt", REVIEWERS, "attendance_policy", True),
    "team_attendance_report": SuggestionDefinition("Tạo báo cáo công nhân viên trực tiếp tháng này", REVIEWERS, "report_security", True),
    "team_leave_report": SuggestionDefinition("Tạo báo cáo nghỉ phép nhóm tháng này", REVIEWERS, "report_security", True),
    "headcount_report": SuggestionDefinition("Mở thống kê headcount hiện tại", REVIEWERS, "report_security"),
    "company_attendance_report": SuggestionDefinition("Tạo báo cáo công toàn công ty tháng này", EDITORS, "report_security"),
    "payroll_summary": SuggestionDefinition("Tạo báo cáo tổng hợp lương tháng trước", EDITORS, "report_security"),
    "knowledge_admin": SuggestionDefinition("Mở quản lý tài liệu nội quy", EDITORS, "report_security"),
    "leave_policy": SuggestionDefinition("Quy định nghỉ phép hằng năm như thế nào?", ALL, "leave_policy"),
    "attendance_policy": SuggestionDefinition("Tôi cần làm gì để giải trình lượt chấm công?", ALL, "attendance_policy"),
    "report_security": SuggestionDefinition("Ai được xem báo cáo nhân sự?", ALL, "report_security"),
}


def resolve_suggestion(suggestion_id: str, roles: set[str], employee_id: int | None):
    definition = SUGGESTIONS.get(suggestion_id)
    if definition is None:
        raise HTTPException(422, "AI_SUGGESTION_INVALID")
    if not definition.roles & roles or definition.needs_employee and employee_id is None:
        raise HTTPException(403, "PERMISSION_DENIED")
    return definition
