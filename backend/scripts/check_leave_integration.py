"""Check legacy migrations and the built UI against a disposable PostgreSQL DB.

Run from the repository root with the established hr-backend interpreter.
Requires PostgreSQL, frontend/dist, Node and installed Edge; installs nothing.
Only the randomly named database created by this script is modified/deleted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.security import get_password_hash


def main() -> None:
    cfg = Settings(_env_file=BACKEND / ".env")
    if cfg.ENVIRONMENT not in {"development", "test"}:
        raise RuntimeError("This check requires development/test configuration")
    source = make_url(cfg.SYNC_DATABASE_URL)
    name = "hr_leave_check_" + uuid4().hex
    assert name != source.database
    output = BACKEND / "storage" / "tmp" / name
    output.mkdir(parents=True)
    maintenance = create_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
    test_engine = None
    server = None
    created = False
    original_env = os.environ.copy()
    evidence = {"legacy_backfill": False, "ui": False, "database_cleanup": False}
    try:
        with maintenance.connect() as conn:
            conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
            created = True
        test_url = source.set(database=name)
        os.environ.update(
            SYNC_DATABASE_URL=test_url.render_as_string(hide_password=False),
            DATABASE_URL=test_url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False),
            ENVIRONMENT="test", GEMINI_ENABLED="false", GEMINI_API_KEY="",
        )
        alembic_cfg = Config(str(BACKEND / "alembic.ini"))
        command.upgrade(alembic_cfg, "a1b2c3d4e5f6")
        test_engine = create_engine(test_url)
        password = secrets.token_urlsafe(24)
        password_hash = get_password_hash(password)
        timestamp = datetime(2025, 5, 6, 7, 8, tzinfo=timezone.utc)
        metadata = MetaData()
        with test_engine.begin() as conn:
            assert conn.scalar(text("SELECT current_database()")) == name

            def insert(table_name, **values):
                table = Table(table_name, metadata, autoload_with=conn, extend_existing=True)
                return conn.execute(table.insert().values(**values)).inserted_primary_key[0]

            department = insert("hr_departments", department_code="CHECK", department_name="Test department", is_active=True)
            position = insert("hr_positions", position_code="CHECK", position_name="Test position", is_active=True)
            employees, users = {}, {}
            for role, manager in [("manager", None), ("staff", "manager"), ("other", None), ("hr", None)]:
                employees[role] = insert(
                    "hr_employees", employee_code=role.upper(), full_name=f"Test {role}",
                    email=f"{role}@leave-check.example", department_id=department,
                    position_id=position, manager_employee_id=employees.get(manager),
                    employment_status="ACTIVE", hire_date=date(2025, 1, 1),
                )
                users[role] = insert(
                    "hr_user_accounts", employee_id=employees[role],
                    login_email=f"{role}@leave-check.example", password_hash=password_hash, is_active=True,
                )
                role_code = "EMPLOYEE" if role == "staff" else "HR" if role == "hr" else "MANAGER"
                role_table = Table("hr_roles", metadata, autoload_with=conn, extend_existing=True)
                role_id = conn.scalar(select(role_table.c.role_id).where(role_table.c.role_code == role_code))
                if role_id is None:
                    role_id = insert("hr_roles", role_code=role_code, role_name=role_code)
                insert("hr_user_role_assignments", user_account_id=users[role], role_id=role_id)
            for status in ["DRAFT", "PUBLISHED", "ARCHIVED", "UNKNOWN"]:
                insert(
                    "hr_ai_knowledge_documents", title=f"Legacy {status}", content=f"Legacy body {status}",
                    status=status, minimum_role="HR", updated_by_user_id=users["hr"],
                    created_at=timestamp, updated_at=timestamp,
                )
            period = insert(
                "hr_payroll_periods", period_year=2025, period_month=5,
                start_date=date(2025, 5, 1), end_date=date(2025, 5, 31),
                status="APPROVED", created_by_user_id=users["hr"], approved_by_user_id=users["hr"],
            )
            insert(
                "hr_payroll_lines", payroll_period_id=period, employee_id=employees["staff"],
                base_salary=Decimal("12345678.90"), standard_work_days=Decimal("22.0"),
                actual_work_days=Decimal("20.0"), allowance_amount=Decimal("100.00"),
                overtime_amount=Decimal("0.00"), deduction_amount=Decimal("0.00"),
                gross_salary=Decimal("11223444.45"), insurance_deduction=Decimal("100.00"),
                taxable_income=Decimal("11223344.45"), personal_income_tax=Decimal("0.00"),
                other_deductions=Decimal("0.00"), net_salary=Decimal("11223344.45"),
                calculation_details={"legacy": True}, calculated_at=timestamp,
            )
        command.upgrade(alembic_cfg, "head")
        with test_engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT d.document_id, d.document_code, d.status AS old_status, d.content,
                       d.current_version_id, v.version_id, v.version_number, v.title, v.status,
                       v.minimum_role, v.created_at, v.updated_at, v.storage_key,
                       s.section_code, s.content AS section_content, s.page_start, s.page_end, s.is_answerable
                FROM hr_ai_knowledge_documents d
                JOIN hr_ai_knowledge_document_versions v ON v.document_id=d.document_id
                JOIN hr_ai_knowledge_sections s ON s.version_id=v.version_id
                ORDER BY d.document_id
            """)).mappings().all()
            assert len(rows) == 4
            for row in rows:
                assert row["document_code"] == f'LEGACY-{row["document_id"]}'
                assert row["current_version_id"] == row["version_id"] and row["version_number"] == 1
                assert row["title"] == f'Legacy {row["old_status"]}' and row["minimum_role"] == "HR"
                assert row["status"] == (row["old_status"] if row["old_status"] != "UNKNOWN" else "DRAFT")
                assert row["created_at"] == row["updated_at"] == timestamp
                assert row["section_code"] == "LEGACY_TEXT" and row["section_content"] == row["content"]
                assert row["storage_key"] is None and row["page_start"] is None and row["page_end"] is None
                assert row["is_answerable"] == (row["old_status"] == "PUBLISHED")
            payroll = conn.execute(text("SELECT * FROM hr_payroll_lines")).mappings().one()
            assert payroll["currency_code"] is None
            assert payroll["net_salary"] == Decimal("11223344.45") and payroll["calculation_details"] == {"legacy": True}
            assert payroll["calculated_at"] == timestamp
            evidence["legacy_backfill"] = True
            leave_type = Table("hr_leave_types", MetaData(), autoload_with=conn)
            conn.execute(leave_type.insert().values(leave_code="ANNUAL", leave_name="Nghỉ phép năm", is_paid=True, is_active=True))
        command.upgrade(alembic_cfg, "head")
        print("PASS: populated legacy knowledge and payroll backfill; repeated upgrade head", flush=True)

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with (output / "backend.log").open("w", encoding="utf-8") as server_log:
            server = subprocess.Popen(
                [sys.executable, "-B", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
                cwd=BACKEND, stdout=server_log, stderr=server_log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Test backend exited; inspect backend.log")
                try:
                    if httpx.get(base + "/health", timeout=1).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Test backend readiness timeout")
            dates = [(date.today() + timedelta(days=30 + i)).isoformat() for i in range(2)]
            browser_env = os.environ.copy()
            browser_env.update(HR_LEAVE_CHECK_API=base, HR_LEAVE_CHECK_OUTPUT=str(output), HR_LEAVE_CHECK_PASSWORD=password, HR_LEAVE_CHECK_DATES=json.dumps(dates))
            subprocess.run(["node", str(REPO / "frontend/scripts/check_leave_integration.mjs")], cwd=REPO, env=browser_env, check=True, timeout=120)

            def api(role, method, path, payload=None):
                login = httpx.post(base + "/api/v1/auth/login", json={"login_email": f"{role}@leave-check.example", "password": password})
                login.raise_for_status()
                return httpx.request(method, base + "/api/v1" + path, json=payload, headers={"Authorization": "Bearer " + login.json()["access_token"]})

            with test_engine.connect() as conn:
                requests = conn.execute(text("SELECT * FROM hr_leave_requests ORDER BY leave_request_id")).mappings().all()
                assert len(requests) == 2 and [r["status"] for r in requests] == ["APPROVED", "REJECTED"]
                assert all(r["employee_id"] == employees["staff"] and r["reviewer_employee_id"] == employees["manager"] for r in requests)
                balance = conn.execute(text("SELECT * FROM hr_employee_leave_balances WHERE employee_id=:id AND year=:year"), {"id": employees["staff"], "year": int(dates[0][:4])}).mappings().one()
                assert balance["used_days"] == Decimal("1.00") and balance["remaining_days"] == Decimal("11.00")
                attendance = conn.execute(text("SELECT * FROM hr_attendance_days WHERE employee_id=:id"), {"id": employees["staff"]}).mappings().all()
                assert len(attendance) == 1 and attendance[0]["attendance_status"] == "ON_LEAVE" and attendance[0]["worked_minutes"] == 480
            request_id = requests[0]["leave_request_id"]
            assert api("manager", "POST", f"/leaves/requests/{request_id}/review", {"status": "APPROVED"}).status_code == 400
            types = api("staff", "GET", "/leaves/types").json()
            for role in ["staff", "manager"]:
                response = api(role, "POST", "/leaves/requests", {"leave_type_id": types[0]["leave_type_id"], "leave_date": (date.today() + timedelta(days=40 if role == "staff" else 41)).isoformat(), "session": "MORNING"})
                assert response.status_code == 201
                pending_id = response.json()["leave_request_id"]
                for reviewer in (["staff", "other", "hr"] if role == "staff" else ["manager"]):
                    assert api(reviewer, "POST", f"/leaves/requests/{pending_id}/review", {"status": "REJECTED"}).status_code == 403
            # REMOTE must remain available even with no annual leave left.
            remote_type = next(item for item in types if item["leave_code"] == "REMOTE")
            assert remote_type["is_paid"]
            annual_type = next(item for item in types if item["leave_code"] == "ANNUAL")
            with test_engine.begin() as conn:
                conn.execute(text("UPDATE hr_employee_leave_balances SET used_days=12, remaining_days=0 WHERE employee_id=:id"), {"id": employees["staff"]})
            remote_ids = []
            for i, (session, decision, minutes) in enumerate([
                ("FULL_DAY", "APPROVED", 480), ("MORNING", "APPROVED", 240), ("AFTERNOON", "REJECTED", 0),
            ]):
                remote_date = (date.today() + timedelta(days=50 + i)).isoformat()
                payload = {"leave_type_id": remote_type["leave_type_id"], "leave_date": remote_date, "session": session}
                response = api("staff", "POST", "/leaves/requests", payload)
                assert response.status_code == 201
                remote_id = response.json()["leave_request_id"]
                remote_ids.append(remote_id)
                assert api("other", "POST", f"/leaves/requests/{remote_id}/review", {"status": decision}).status_code == 403
                reviewed = api("manager", "POST", f"/leaves/requests/{remote_id}/review", {"status": decision})
                assert reviewed.status_code == 200 and reviewed.json()["status"] == decision
                assert api("manager", "POST", f"/leaves/requests/{remote_id}/review", {"status": decision}).status_code == 400
                with test_engine.connect() as conn:
                    attendance = conn.execute(text("SELECT attendance_status, worked_minutes FROM hr_attendance_days WHERE employee_id=:id AND work_date=:day"), {"id": employees["staff"], "day": remote_date}).mappings().all()
                    if decision == "APPROVED":
                        assert len(attendance) == 1 and attendance[0]["attendance_status"] == "REMOTE"
                        assert attendance[0]["worked_minutes"] == minutes
                    else:
                        assert not attendance
            with test_engine.connect() as conn:
                balance = conn.execute(text("SELECT used_days, remaining_days FROM hr_employee_leave_balances WHERE employee_id=:id"), {"id": employees["staff"]}).mappings().one()
                assert balance["used_days"] == Decimal("12.00") and balance["remaining_days"] == Decimal("0.00")
            blocked_annual = api("staff", "POST", "/leaves/requests", {
                "leave_type_id": annual_type["leave_type_id"], "leave_date": (date.today() + timedelta(days=55)).isoformat(), "session": "FULL_DAY",
            })
            assert blocked_annual.status_code == 400
            evidence["remote"] = "full/half day paid attendance, rejected request has no attendance; exhausted annual balance unchanged"
            print("PASS: REMOTE full/half day approval/rejection with zero annual quota; annual leave still blocked", flush=True)
            evidence["ui"] = True
            evidence["authorization"] = "employee, unrelated manager, HR and self-review denied; duplicate review denied"
            print("PASS: real UI submission/approval/rejection; committed PostgreSQL balance/attendance; authorization", flush=True)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        if test_engine is not None:
            test_engine.dispose()
        if created:
            with maintenance.connect() as conn:
                conn.exec_driver_sql(f'DROP DATABASE "{name}"')
            evidence["database_cleanup"] = True
        maintenance.dispose()
        os.environ.clear()
        os.environ.update(original_env)
        (output / "result.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Evidence:", output, flush=True)


if __name__ == "__main__":
    main()
