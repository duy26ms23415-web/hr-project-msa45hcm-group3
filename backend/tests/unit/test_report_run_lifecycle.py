from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.schemas.reports import ReportRunCreate
from app.services import report_run_service as module
from app.services.report_service import ReportService


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "storage", "empty_scope"])
async def test_run_freezes_scope_and_persists_terminal_state(monkeypatch, failure):
    events = []
    actor = SimpleNamespace(user_account_id=9, login_email="owner@example.test")
    req = ReportRunCreate(kind="ATTENDANCE", start_date=date(2026, 10, 1), end_date=date(2026, 10, 31))
    ids = [] if failure == "empty_scope" else [7]
    monkeypatch.setattr(ReportService, "visible_employee_ids", AsyncMock(return_value=("SELF", ids)))

    async def save(user, request, run_id, scope, employee_ids, status, **values):
        assert user is actor and request is req and employee_ids == ids
        events.append((status, values))
        return SimpleNamespace(status=status, scope=scope)

    async def generate(*args, **kwargs):
        assert events[0][0] == "GENERATING"
        assert kwargs["source_employee_ids"] == ids
        if failure == "empty_scope":
            raise HTTPException(403, "AI_ACCESS_DENIED")
        return {"rows": [{"employee_id": 7}], "kind": "ATTENDANCE"}

    monkeypatch.setattr(module.ReportRunService, "_save_state", save)
    monkeypatch.setattr(ReportService, "generate", generate)
    monkeypatch.setattr(module, "build_xlsx_report", Mock(return_value=b"xlsx"))
    stored = Mock(side_effect=[("workbook.xlsx", "digest"), OSError("private path")] if failure == "storage" else [("workbook.xlsx", "digest"), ("snapshot.json", "digest")])
    monkeypatch.setattr(module, "store_report", stored)
    deleted = Mock()
    monkeypatch.setattr(module, "delete_report", deleted)
    if failure:
        with pytest.raises(HTTPException) as caught:
            await module.ReportRunService._create(AsyncMock(), actor, req)
        assert caught.value.status_code == (503 if failure == "storage" else 403)
        assert [event[0] for event in events] == ["GENERATING", "FAILED"]
        assert events[-1][1]["error_code"] == ("DATA_SERVICE_UNAVAILABLE" if failure == "storage" else "REPORT_REQUEST_REJECTED")
        assert events[-1][1]["storage_key"] is None
        if failure == "storage":
            deleted.assert_any_call("workbook.xlsx")
    else:
        result = await module.ReportRunService._create(AsyncMock(), actor, req)
        assert result["run"].status == "READY"
        assert [event[0] for event in events] == ["GENERATING", "READY"]
        assert events[-1][1]["snapshot_storage_key"] == "snapshot.json"


@pytest.mark.asyncio
async def test_frozen_ids_narrow_existing_manager_query():
    from sqlalchemy.dialects import postgresql
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))
    actor = SimpleNamespace(employee_id=7, role_assignments=[SimpleNamespace(role=SimpleNamespace(role_code="MANAGER"))])
    await ReportService.generate(db, actor, "HEADCOUNT", date(2026, 10, 1), date(2026, 10, 31), None, source_employee_ids=[8])
    sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "manager_employee_id = 7" in sql and "employee_id IN (8)" in sql
