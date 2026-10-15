import pytest
from datetime import date
from decimal import Decimal
from httpx import AsyncClient, ASGITransport
import secrets

from app.main import app
from app.core.database import AsyncSessionLocal
from app.models.organization import Employee, Department, Position
from app.models.auth import Role, UserAccount, UserRoleAssignment
from app.models.leave import EmployeeLeaveBalance
from app.services.leave_service import LeaveService
from sqlalchemy import select, delete


@pytest.mark.asyncio
async def test_manager_leave_quota_18_days_vs_employee_12_days():
    """Verify MANAGER role gets 18 days leave quota and EMPLOYEE gets 12 days."""
    async with AsyncSessionLocal() as db:
        # 1. Create a dummy employee with MANAGER role
        dept = (await db.execute(select(Department))).scalars().first()
        pos = (await db.execute(select(Position))).scalars().first()
        mgr_role = (await db.execute(select(Role).where(Role.role_code == "MANAGER"))).scalar_one()
        emp_role = (await db.execute(select(Role).where(Role.role_code == "EMPLOYEE"))).scalar_one()

        code_mgr = f"TEST_MGR_{secrets.token_hex(4)}"
        code_emp = f"TEST_EMP_{secrets.token_hex(4)}"

        mgr = Employee(
            employee_code=code_mgr,
            full_name="Test Manager",
            email=f"{code_mgr.lower()}@test.com",
            department_id=dept.department_id,
            position_id=pos.position_id,
            hire_date=date(2026, 1, 1),
            employment_status="ACTIVE",
        )
        emp = Employee(
            employee_code=code_emp,
            full_name="Test Employee",
            email=f"{code_emp.lower()}@test.com",
            department_id=dept.department_id,
            position_id=pos.position_id,
            hire_date=date(2026, 1, 1),
            employment_status="ACTIVE",
        )
        db.add_all([mgr, emp])
        await db.flush()

        # Create user accounts and role assignments
        acc_mgr = UserAccount(
            employee_id=mgr.employee_id,
            login_email=mgr.email,
            password_hash="fakehash",
            is_active=True,
        )
        acc_emp = UserAccount(
            employee_id=emp.employee_id,
            login_email=emp.email,
            password_hash="fakehash",
            is_active=True,
        )
        db.add_all([acc_mgr, acc_emp])
        await db.flush()

        db.add(UserRoleAssignment(user_account_id=acc_mgr.user_account_id, role_id=mgr_role.role_id))
        db.add(UserRoleAssignment(user_account_id=acc_emp.user_account_id, role_id=emp_role.role_id))
        await db.flush()

        # Check LeaveService.get_or_create_balance
        bal_mgr = await LeaveService.get_or_create_balance(db, mgr.employee_id, 2026)
        bal_emp = await LeaveService.get_or_create_balance(db, emp.employee_id, 2026)

        assert bal_mgr.total_entitled_days == Decimal("18.00")
        assert bal_mgr.remaining_days == Decimal("18.00")

        assert bal_emp.total_entitled_days == Decimal("12.00")
        assert bal_emp.remaining_days == Decimal("12.00")

        # Clean up
        await db.rollback()


@pytest.mark.asyncio
async def test_manager_leave_quota_upgrades_existing_12_days():
    """Verify that an existing manager balance initialized at 12 days upgrades to 18 days."""
    async with AsyncSessionLocal() as db:
        dept = (await db.execute(select(Department))).scalars().first()
        pos = (await db.execute(select(Position))).scalars().first()
        mgr_role = (await db.execute(select(Role).where(Role.role_code == "MANAGER"))).scalar_one()

        code = f"TEST_UP_{secrets.token_hex(4)}"
        mgr = Employee(
            employee_code=code,
            full_name="Test Upgrade Manager",
            email=f"{code.lower()}@test.com",
            department_id=dept.department_id,
            position_id=pos.position_id,
            hire_date=date(2026, 1, 1),
            employment_status="ACTIVE",
        )
        db.add(mgr)
        await db.flush()

        acc = UserAccount(
            employee_id=mgr.employee_id,
            login_email=mgr.email,
            password_hash="fakehash",
            is_active=True,
        )
        db.add(acc)
        await db.flush()
        db.add(UserRoleAssignment(user_account_id=acc.user_account_id, role_id=mgr_role.role_id))

        # Manually create a 12-day balance
        old_bal = EmployeeLeaveBalance(
            employee_id=mgr.employee_id,
            year=2026,
            total_entitled_days=Decimal("12.00"),
            used_days=Decimal("2.00"),
            remaining_days=Decimal("10.00"),
        )
        db.add(old_bal)
        await db.flush()

        # Calling get_or_create_balance should upgrade to 18.00 with diff of 6.00 added to remaining
        bal = await LeaveService.get_or_create_balance(db, mgr.employee_id, 2026)
        assert bal.total_entitled_days == Decimal("18.00")
        assert bal.used_days == Decimal("2.00")
        assert bal.remaining_days == Decimal("16.00")

        await db.rollback()


@pytest.mark.asyncio
async def test_create_employee_with_roles_api():
    """Verify creating employees with ADMIN, HR, MANAGER, EMPLOYEE roles via API."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        auth_resp = await ac.post("/api/v1/auth/login", json={
            "login_email": "admin@hrgroup3.com",
            "password": "Password@123"
        })
        token = auth_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create MANAGER employee
        mgr_code = f"MGR_{secrets.token_hex(4).upper()}"
        mgr_payload = {
            "employee_code": mgr_code,
            "full_name": f"Manager {mgr_code}",
            "email": f"{mgr_code.lower()}@hrgroup3.com",
            "department_id": 1,
            "position_id": 1,
            "hire_date": "2026-01-01",
            "login_password": "Password@123",
            "role_code": "MANAGER"
        }
        res_mgr = await ac.post("/api/v1/employees", json=mgr_payload, headers=headers)
        assert res_mgr.status_code == 201, res_mgr.text
        data_mgr = res_mgr.json()
        assert data_mgr["roles"] == ["MANAGER"]

        # Check manager's leave balance in API
        bal_resp = await ac.get(f"/api/v1/leaves/balances/employees/{data_mgr['employee_id']}?year=2026", headers=headers)
        assert bal_resp.status_code == 200
        assert float(bal_resp.json()["total_entitled_days"]) == 18.0
        assert float(bal_resp.json()["remaining_days"]) == 18.0

        # 2. Create HR employee
        hr_code = f"HR_{secrets.token_hex(4).upper()}"
        hr_payload = {
            "employee_code": hr_code,
            "full_name": f"HR {hr_code}",
            "email": f"{hr_code.lower()}@hrgroup3.com",
            "department_id": 1,
            "position_id": 1,
            "hire_date": "2026-01-01",
            "login_password": "Password@123",
            "role_code": "HR"
        }
        res_hr = await ac.post("/api/v1/employees", json=hr_payload, headers=headers)
        assert res_hr.status_code == 201
        assert res_hr.json()["roles"] == ["HR"]

        # 3. Create EMPLOYEE
        emp_code = f"EMP_{secrets.token_hex(4).upper()}"
        emp_payload = {
            "employee_code": emp_code,
            "full_name": f"Staff {emp_code}",
            "email": f"{emp_code.lower()}@hrgroup3.com",
            "department_id": 1,
            "position_id": 1,
            "hire_date": "2026-01-01",
            "login_password": "Password@123",
            "role_code": "EMPLOYEE"
        }
        res_emp = await ac.post("/api/v1/employees", json=emp_payload, headers=headers)
        assert res_emp.status_code == 201
        assert res_emp.json()["roles"] == ["EMPLOYEE"]

        # Check employee's leave balance is 12 days
        bal_emp_resp = await ac.get(f"/api/v1/leaves/balances/employees/{res_emp.json()['employee_id']}?year=2026", headers=headers)
        assert bal_emp_resp.status_code == 200
        assert float(bal_emp_resp.json()["total_entitled_days"]) == 12.0
        assert float(bal_emp_resp.json()["remaining_days"]) == 12.0

        # 4. Reject invalid role
        invalid_code = f"INV_{secrets.token_hex(4).upper()}"
        inv_payload = {
            "employee_code": invalid_code,
            "full_name": f"Invalid {invalid_code}",
            "email": f"{invalid_code.lower()}@hrgroup3.com",
            "department_id": 1,
            "position_id": 1,
            "hire_date": "2026-01-01",
            "login_password": "Password@123",
            "role_code": "SUPERUSER"
        }
        res_inv = await ac.post("/api/v1/employees", json=inv_payload, headers=headers)
        assert res_inv.status_code == 422


def test_schema_allows_kiosk_role():
    from app.schemas.organization import EmployeeCreate, EmployeeUpdate
    from datetime import date

    payload = EmployeeCreate(
        employee_code="KIOSK01",
        full_name="Kiosk Machine",
        email="kiosk@hrgroup3.com",
        department_id=1,
        position_id=1,
        hire_date=date(2026, 1, 1),
        login_password="Password@123",
        role_code="kiosk"
    )
    assert payload.role_code == "KIOSK"

    update_payload = EmployeeUpdate(role_code="kiosk")
    assert update_payload.role_code == "KIOSK"
