"""Rule-path routing of the actor's own records and evidence matching for policy answers."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.ai.parsing.lexicon import canonical
from app.ai.parsing.personal import (asks_lateness, is_attendance_query, is_leave_status_query,
                                     is_own_salary_query, is_remote_request, week_period)
from app.ai.tool_registry import attendance_period, attendance_reply
from app.services.ai_policy_answer import grounded_reply
from app.services.ai_service import AIService

TODAY = date(2026, 10, 17)  # Saturday


@pytest.mark.parametrize("message", [
    "Tháng này tôi đi muộn mấy lần?", "tháng này t đi trễ bao nhiêu buổi", "Hôm qua tôi check-in lúc mấy giờ?",
    "Tuần này tôi làm đủ công chưa?", "Tháng trước tôi có bao nhiêu ngày công?", "hôm nay tôi chấm công chưa",
])
def test_personal_attendance_questions_are_lookups(message):
    assert is_attendance_query(canonical(message))


@pytest.mark.parametrize("message", ["Đi muộn bị phạt thế nào?", "Ngày công được tính ra sao?"])
def test_attendance_policy_questions_stay_policy(message):
    assert not is_attendance_query(canonical(message))


def test_leave_status_is_own_requests_not_manager_queue():
    assert is_leave_status_query(canonical("Đơn nghỉ phép của tôi đã được duyệt chưa?"))
    assert not is_leave_status_query(canonical("Mở đơn đang chờ tôi duyệt"))


def test_own_salary_question_is_not_a_tax_policy_question():
    assert is_own_salary_query(canonical("Lương tháng này của tôi bao nhiêu?"))
    assert not is_own_salary_query(canonical("Cách tính lương làm thêm giờ?"))
    assert not is_own_salary_query(canonical("Xuất phiếu lương của tôi tháng trước"))


def test_remote_booking_vs_remote_policy_question():
    assert is_remote_request(canonical("Tôi muốn làm remote thứ hai tuần sau"))
    assert not is_remote_request(canonical("Làm việc từ xa có được tính công không?"))


def test_week_periods_are_monday_based_and_stop_at_today():
    assert week_period("tuan nay", TODAY) == (date(2026, 10, 12), TODAY)
    assert week_period("tuan truoc", TODAY) == (date(2026, 10, 5), date(2026, 10, 11))
    assert attendance_period("Hôm qua tôi check-in lúc mấy giờ?", TODAY) == (date(2026, 10, 16),) * 2
    assert attendance_period("Tháng trước tôi có bao nhiêu ngày công?", TODAY) == (date(2026, 9, 1), date(2026, 9, 30))


def test_attendance_reply_shows_times_and_never_counts_lateness():
    day = {"days": [{"date": "2026-10-16", "status": "PRESENT", "check_in": "08:05", "check_out": None}],
           "present_days": 1, "incomplete_dates": []}
    reply = attendance_reply(day, date(2026, 10, 16), date(2026, 10, 16), lateness=True)
    assert "Check-in: 08:05" in reply and "Check-out: chưa ghi nhận" in reply
    assert "chưa có quy tắc đi muộn" in reply
    empty = {"recorded_days": 0, "present_days": 0, "incomplete_dates": [], "days": []}
    assert "chưa có dữ liệu" in attendance_reply(empty, date(2026, 9, 1), date(2026, 9, 30), lateness=False)


def test_remote_draft_does_not_ask_about_time_off():
    question = AIService._draft_question("DRAFT_LEAVE", ["session", "reason"], remote=True)
    assert question.startswith("Bạn làm việc từ xa") and "nghỉ" not in question


def _answer(evidence):
    return SimpleNamespace(statements=[SimpleNamespace(source=1, text="Nghỉ ốm tính theo cờ is_paid.", evidence=evidence)])


def test_evidence_survives_pdf_line_breaks_but_must_stay_verbatim():
    passage = SimpleNamespace(content="SICK – nghỉ ốm; ngày nghỉ có được tính lương\nở kết quả payroll  hay không.")
    assert "[1]" in grounded_reply(_answer("ngày nghỉ có được tính lương ở kết quả payroll hay không."), [passage])
    with pytest.raises(ValueError):
        grounded_reply(_answer("ngày nghỉ luôn được tính lương."), [passage])


def test_team_wording_is_never_the_actors_own_records():
    from app.ai.parsing.personal import is_team_records_query
    text = canonical("Nhân viên của tôi tháng này ai thiếu công?")
    assert not is_attendance_query(text) and is_team_records_query(text)
    assert not is_own_salary_query(canonical("Lương nhân viên nhóm tôi tháng này"))


def test_a_period_makes_plain_cham_cong_a_records_question():
    assert is_attendance_query(canonical("tuần trước tôi chấm công thế nào"))
    assert not is_attendance_query(canonical("Tôi chấm công thế nào?"))


def test_weekend_leave_date_is_refused_before_the_form():
    values = {"leave_date": "2026-10-18", "session": "FULL_DAY"}
    notice = AIService._drop_weekend_leave("DRAFT_LEAVE", values)
    assert "Chủ nhật" in notice and "leave_date" not in values
    weekday = {"leave_date": "2026-10-19"}
    assert AIService._drop_weekend_leave("DRAFT_LEAVE", weekday) is None and weekday == {"leave_date": "2026-10-19"}
    assert AIService._drop_weekend_leave("DRAFT_FIX", {"leave_date": "2026-10-18"}) is None


def test_day_range_revision_keeps_the_edited_month():
    from app.services.ai_report_interpreter import report_answers
    current = {"kind": "ATTENDANCE", "scope": "SELF", "start_date": "2026-09-01", "end_date": "2026-09-30"}
    assert report_answers("chỉ lấy từ ngày 1 đến ngày 10", TODAY, current) == {"start_date": "2026-09-01", "end_date": "2026-09-10"}
    assert report_answers("từ ngày 5 đến ngày 3", TODAY, current) == {}
    assert report_answers("10 - 20 người", TODAY, current) == {}


def test_analysis_summary_uses_labels_and_skips_single_row_averages():
    from app.services.ai_analysis_tool import analysis_summary
    one = {"row_count": 1, "metrics": {"worked_minutes": {"sum": "1720", "mean": "1720"}}, "chart": None}
    text = analysis_summary(one)
    assert "Phút làm việc: tổng **1.720**" in text and "trung bình" not in text and "chưa vẽ biểu đồ" in text
    many = {"row_count": 2, "metrics": {"net_salary": {"sum": "30000000.50", "mean": "15000000.25"}}, "chart": "data:x"}
    assert "trung bình 15.000.000,25/dòng" in analysis_summary(many)


def test_bare_weekday_points_forward_for_leave_and_back_for_fixes():
    from app.ai.parsing.dates import resolve_rule_date
    assert resolve_rule_date("thứ 3", TODAY).value == "2026-10-20"
    assert resolve_rule_date("thứ 3", TODAY, "past").value == "2026-10-13"


def test_leave_range_lists_working_days_only():
    from app.ai.parsing.dates import leave_range
    assert leave_range("muốn nghỉ từ thứ 2 đến thứ 5 tuần sau", TODAY) == [date(2026, 10, 19 + i) for i in range(4)]
    assert len(leave_range("nghỉ từ 16/10 đến 20/10", TODAY)) == 3  # Fri, Mon, Tue
    assert leave_range("xin nghỉ ngày mai", TODAY) is None
