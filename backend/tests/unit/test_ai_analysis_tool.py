import base64
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.ai_analysis_tool import analyze_report


def test_decimal_statistics_complete_snapshot_and_png():
    result = analyze_report({"kind": "MY_PAYSLIP", "rows": [
        {"net_salary": "0.10", "currency_code": "VND"},
        {"net_salary": "0.20", "currency_code": "VND"},
        {"net_salary": None, "currency_code": "VND"}]})
    assert result["row_count"] == 3
    assert Decimal(result["metrics"]["net_salary"]["sum"]) == Decimal("0.30")
    assert Decimal(result["metrics"]["net_salary"]["median"]) == Decimal("0.15")
    assert result["metrics"]["net_salary"]["missing"] == 1
    assert base64.b64decode(result["chart"].split(",", 1)[1]).startswith(b"\x89PNG\r\n\x1a\n")


def test_empty_report_and_identifier_columns():
    assert analyze_report({"kind": "ATTENDANCE", "rows": []})["chart"] is None
    result = analyze_report({"kind": "ATTENDANCE", "rows": [{"employee_id": 5, "department_id": 2}]})
    assert result["metrics"] == {}


def test_frequency_and_mixed_currency_never_combined():
    result = analyze_report({"kind": "PAYROLL_SUMMARY", "rows": [
        {"net_salary": "10", "currency_code": "VND"},
        {"net_salary": "20", "currency_code": "USD"}]})
    assert "net_salary" not in result["metrics"]
    assert result["frequencies"]["currency_code"] == {"VND": 1, "USD": 1}


def test_analysis_is_bounded():
    with pytest.raises(HTTPException) as exc:
        analyze_report({"kind": "ATTENDANCE", "rows": [{}] * 10001})
    assert exc.value.status_code == 422


def test_headcount_charts_departments_and_counts_people_not_group_rows():
    result = analyze_report({"kind": "HEADCOUNT", "rows": [
        {"department_name": "Kỹ thuật", "employment_status": "ACTIVE", "employee_count": 2},
        {"department_name": "Nhân sự", "employment_status": "ACTIVE", "employee_count": 1},
        {"department_name": "Kỹ thuật", "employment_status": "TERMINATED", "employee_count": 1},
    ]})
    chart = result["chart_data"]
    assert chart["title"] == "Cơ cấu nhân sự theo phòng ban"
    assert chart["labels"] == ["Kỹ thuật", "Nhân sự"]
    assert chart["stacked"] is True
    assert chart["series"] == [
        {"name": "Đang làm việc", "values": ["2", "1"]},
        {"name": "Đã nghỉ việc", "values": ["1", "0"]}]
    assert result["frequencies"]["employment_status"] == {"ACTIVE": 3, "TERMINATED": 1}


def test_many_departments_chart_preserves_totals_in_other_group():
    result = analyze_report({"kind": "HEADCOUNT", "rows": [
        {"department_name": f"Phòng {index}", "employee_count": index + 1}
        for index in range(25)]})
    chart = result["chart_data"]
    assert len(chart["labels"]) == 20
    assert chart["labels"][-1] == "Các phòng ban còn lại (6)"
    assert sum(Decimal(value) for value in chart["series"][0]["values"]) == 325


def test_attendance_chart_compares_days_not_minutes_or_distribution_statistics():
    result = analyze_report({"kind": "ATTENDANCE", "rows": [
        {"present_days": 20, "absent_days": 1, "incomplete_days": 2, "worked_minutes": 9600},
        {"present_days": 18, "absent_days": 3, "incomplete_days": 2, "worked_minutes": 8640}]})
    assert result["chart_data"]["unit"] == "Ngày công"
    assert result["chart_data"]["labels"] == ["Có mặt", "Thiếu lượt công", "Vắng"]
    assert result["chart_data"]["series"][0]["values"] == ["38", "4", "4"]


def test_payroll_chart_preserves_decimal_and_never_combines_currencies():
    rows = [{"department_name": "HR", "employee_count": 1, "gross_salary": "0.20", "net_salary": "0.10", "currency_code": "VND"},
            {"department_name": "HR", "employee_count": 1, "gross_salary": "0.40", "net_salary": "0.20", "currency_code": "VND"}]
    chart = analyze_report({"kind": "PAYROLL_SUMMARY", "rows": rows})["chart_data"]
    assert chart["unit"] == "VND"
    assert chart["series"][1]["values"] == ["0.30"]
    rows[1]["currency_code"] = "USD"
    chart = analyze_report({"kind": "PAYROLL_SUMMARY", "rows": rows})["chart_data"]
    assert chart["unit"] == "Nhân viên"
    assert chart["series"] == [{"name": "Số nhân viên", "values": ["2"]}]
