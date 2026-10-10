from datetime import date
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.api.v1.endpoints import reports
from app.core.database import get_db
from app.models.ai_security import AIRequestEvent
from app.services.ai_suggestions import resolve_suggestion
from app.services.ai_service import AIService
from app.services.ai_request_security import ACTIONS
from app.services.report_catalog import report_catalog
from app.services.report_service import ReportService
from app.services.report_access import authorized_run
from app.schemas.ai import AIChatRequest


def actor(*roles):
    return SimpleNamespace(employee_id=7, user_account_id=9,
        role_assignments=[SimpleNamespace(role=SimpleNamespace(role_code=role)) for role in roles])


@pytest.mark.parametrize("roles,scopes", [
    (("EMPLOYEE",), []), (("MANAGER",), ["SELF", "DIRECT_REPORTS"]),
    (("HR",), ["SELF", "DIRECT_REPORTS", "COMPANY"]),
    (("ADMIN",), ["SELF", "DIRECT_REPORTS", "COMPANY"]),
    (("EMPLOYEE", "HR"), ["SELF", "DIRECT_REPORTS", "COMPANY"]),
])
def test_report_catalog_role_matrix(roles, scopes):
    catalog = report_catalog(actor(*roles))["reports"]
    if not scopes:
        assert catalog == []
    else:
        attendance = next(item for item in catalog if item["kind"] == "ATTENDANCE")
        assert attendance["scopes"] == scopes
        assert any(item["kind"] == "PAYROLL_SUMMARY" for item in catalog) == bool(set(roles) & {"HR", "ADMIN"})


@pytest.mark.parametrize("suggestion", ["my_attendance_report", "my_payslip", "team_attendance_report", "team_leave_report", "headcount_report", "company_attendance_report", "payroll_summary"])
def test_employee_report_suggestions_are_denied(suggestion):
    with pytest.raises(HTTPException) as denied:
        resolve_suggestion(suggestion, {"EMPLOYEE"}, 7)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["Tạo báo cáo công của tôi tháng này", "Tạo báo cáo phiếu lương của tôi tháng trước", "phân tích báo cáo này", "vẽ biểu đồ nghỉ phép"])
async def test_employee_free_report_prompts_denied_before_db(message):
    db = AsyncMock()
    with pytest.raises(HTTPException) as denied:
        await AIService.process_chat(db, 7, AIChatRequest(message=message), {"EMPLOYEE"}, 9, actor("EMPLOYEE"))
    assert denied.value.status_code == 403
    db.execute.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["ATTENDANCE", "LEAVE", "ATTENDANCE_FIX", "APPROVAL_QUEUE", "HEADCOUNT", "MY_PAYSLIP", "PAYROLL_SUMMARY"])
async def test_employee_all_report_services_denied_before_query(kind):
    db = AsyncMock()
    for call in (
        ReportService.generate(db, actor("EMPLOYEE"), kind, date(2026, 10, 1), date(2026, 10, 31), None, "SELF"),
        ReportService.visible_employee_ids(db, actor("EMPLOYEE"), kind, "SELF", None),
    ):
        with pytest.raises(HTTPException) as denied:
            await call
        assert denied.value.status_code == 403
    db.execute.assert_not_called()
    db.scalar.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("GET", "/reports/catalog"), ("GET", "/reports/runs"),
    ("POST", "/reports/runs"), ("GET", "/reports/runs/" + "a" * 32),
    ("GET", "/reports/runs/" + "a" * 32 + "/download"),
    ("GET", "/reports/runs/" + "a" * 32 + "/file"),
    ("GET", "/reports/runs/" + "a" * 32 + "/analysis"),
    ("GET", "/reports?kind=ATTENDANCE&start_date=2026-10-01&end_date=2026-10-31&output=json"),
    ("GET", "/reports?kind=ATTENDANCE&start_date=2026-10-01&end_date=2026-10-31&output=csv"),
    ("GET", "/reports?kind=ATTENDANCE&start_date=2026-10-01&end_date=2026-10-31&output=xlsx"),
])
async def test_employee_direct_report_endpoints_denied(method, path):
    app = FastAPI()
    app.include_router(reports.router, prefix="/reports")
    db = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: actor("EMPLOYEE")
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, path, json={"kind": "ATTENDANCE", "start_date": "2026-10-01", "end_date": "2026-10-31"})
    assert response.status_code == 403
    db.execute.assert_not_called()
    db.scalar.assert_not_called()


@pytest.mark.asyncio
async def test_employee_cannot_read_preexisting_own_snapshot():
    db = AsyncMock()
    with pytest.raises(HTTPException) as denied:
        await authorized_run(db, actor("EMPLOYEE"), "a" * 32)
    assert denied.value.status_code == 403
    db.scalar.assert_not_called()


def test_audit_schema_accepts_every_service_action():
    constraint = next(item for item in AIRequestEvent.__table__.constraints if item.name == "ck_ai_request_event_action")
    assert set(re.findall(r"'([A-Z_]+)'", str(constraint.sqltext))) == set(ACTIONS)
