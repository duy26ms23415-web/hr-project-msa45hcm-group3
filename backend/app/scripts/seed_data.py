import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.organization import Department, Position, Employee
from app.models.auth import Role, UserAccount, UserRoleAssignment
from app.models.leave import LeaveType, EmployeeLeaveBalance
from app.models.holiday import Holiday
from app.models.payroll import EmployeeCompensation


async def seed_data():
    async with AsyncSessionLocal() as session:
        print("🌱 Bắt đầu khởi tạo dữ liệu mẫu...")

        # 1. Roles
        roles_data = [
            ("ADMIN", "Quản trị hệ thống"),
            ("HR", "Nhân sự"),
            ("MANAGER", "Quản lý trực tiếp"),
            ("EMPLOYEE", "Nhân viên"),
        ]
        roles_map = {}
        for code, name in roles_data:
            stmt = select(Role).where(Role.role_code == code)
            result = await session.execute(stmt)
            role = result.scalar_one_or_none()
            if not role:
                role = Role(role_code=code, role_name=name)
                session.add(role)
                await session.flush()
            roles_map[code] = role

        # 2. Leave Types
        leave_types_data = [
            ("ANNUAL", "Nghỉ phép năm", True),
            ("UNPAID", "Nghỉ không hưởng lương", False),
            ("SICK", "Nghỉ ốm đau", True),
        ]
        leave_types_map = {}
        for code, name, is_paid in leave_types_data:
            stmt = select(LeaveType).where(LeaveType.leave_code == code)
            result = await session.execute(stmt)
            lt = result.scalar_one_or_none()
            if not lt:
                lt = LeaveType(leave_code=code, leave_name=name, is_paid=is_paid)
                session.add(lt)
                await session.flush()
            leave_types_map[code] = lt

        # 3. Department & Position
        stmt = select(Department).where(Department.department_code == "TECH")
        tech_dept = (await session.execute(stmt)).scalar_one_or_none()
        if not tech_dept:
            tech_dept = Department(
                department_code="TECH",
                department_name="Phòng Kỹ thuật & Công nghệ",
                is_active=True
            )
            session.add(tech_dept)
            await session.flush()

        stmt = select(Department).where(Department.department_code == "HR")
        hr_dept = (await session.execute(stmt)).scalar_one_or_none()
        if not hr_dept:
            hr_dept = Department(
                department_code="HR",
                department_name="Phòng Nhân sự & Hành chính",
                is_active=True
            )
            session.add(hr_dept)
            await session.flush()

        stmt = select(Position).where(Position.position_code == "LEAD_DEV")
        pos_lead = (await session.execute(stmt)).scalar_one_or_none()
        if not pos_lead:
            pos_lead = Position(position_code="LEAD_DEV", position_name="Trưởng nhóm phát triển", is_active=True)
            session.add(pos_lead)
            await session.flush()

        stmt = select(Position).where(Position.position_code == "DEV")
        pos_dev = (await session.execute(stmt)).scalar_one_or_none()
        if not pos_dev:
            pos_dev = Position(position_code="DEV", position_name="Kỹ sư phần mềm", is_active=True)
            session.add(pos_dev)
            await session.flush()

        stmt = select(Position).where(Position.position_code == "HR_MANAGER")
        pos_hr_mgr = (await session.execute(stmt)).scalar_one_or_none()
        if not pos_hr_mgr:
            pos_hr_mgr = Position(position_code="HR_MANAGER", position_name="Trưởng phòng nhân sự", is_active=True)
            session.add(pos_hr_mgr)
            await session.flush()

        # 4. Admin / HR Manager
        stmt = select(Employee).where(Employee.employee_code == "EMP001")
        admin_emp = (await session.execute(stmt)).scalar_one_or_none()
        if not admin_emp:
            admin_emp = Employee(
                employee_code="EMP001",
                full_name="Nguyễn Văn Quản Trị",
                email="admin@hrgroup3.com",
                phone_number="0901234567",
                date_of_birth=date(1990, 1, 1),
                department_id=hr_dept.department_id,
                position_id=pos_hr_mgr.position_id,
                employment_status="ACTIVE",
                hire_date=date(2024, 1, 1),
            )
            session.add(admin_emp)
            await session.flush()

        stmt = select(UserAccount).where(UserAccount.login_email == "admin@hrgroup3.com")
        admin_acc = (await session.execute(stmt)).scalar_one_or_none()
        if not admin_acc:
            admin_acc = UserAccount(
                employee_id=admin_emp.employee_id,
                login_email="admin@hrgroup3.com",
                password_hash=get_password_hash("Password@123"),
                is_active=True
            )
            session.add(admin_acc)
            await session.flush()

            # Assign ADMIN and HR roles
            session.add(UserRoleAssignment(user_account_id=admin_acc.user_account_id, role_id=roles_map["ADMIN"].role_id))
            session.add(UserRoleAssignment(user_account_id=admin_acc.user_account_id, role_id=roles_map["HR"].role_id))
            await session.flush()

        # 5. Direct Manager Employee
        stmt = select(Employee).where(Employee.employee_code == "EMP002")
        mgr_emp = (await session.execute(stmt)).scalar_one_or_none()
        if not mgr_emp:
            mgr_emp = Employee(
                employee_code="EMP002",
                full_name="Trần Văn Quản Lý",
                email="manager@hrgroup3.com",
                phone_number="0907654321",
                date_of_birth=date(1992, 5, 10),
                department_id=tech_dept.department_id,
                position_id=pos_lead.position_id,
                employment_status="ACTIVE",
                hire_date=date(2024, 2, 1),
            )
            session.add(mgr_emp)
            await session.flush()

        stmt = select(UserAccount).where(UserAccount.login_email == "manager@hrgroup3.com")
        mgr_acc = (await session.execute(stmt)).scalar_one_or_none()
        if not mgr_acc:
            mgr_acc = UserAccount(
                employee_id=mgr_emp.employee_id,
                login_email="manager@hrgroup3.com",
                password_hash=get_password_hash("Password@123"),
                is_active=True
            )
            session.add(mgr_acc)
            await session.flush()
            session.add(UserRoleAssignment(user_account_id=mgr_acc.user_account_id, role_id=roles_map["MANAGER"].role_id))
            await session.flush()

        # Update department manager
        tech_dept.manager_employee_id = mgr_emp.employee_id
        session.add(tech_dept)

        # 6. Regular Employee
        stmt = select(Employee).where(Employee.employee_code == "EMP003")
        staff_emp = (await session.execute(stmt)).scalar_one_or_none()
        if not staff_emp:
            staff_emp = Employee(
                employee_code="EMP003",
                full_name="Lê Thị Nhân Viên",
                email="employee@hrgroup3.com",
                phone_number="0911223344",
                date_of_birth=date(1998, 8, 20),
                department_id=tech_dept.department_id,
                position_id=pos_dev.position_id,
                manager_employee_id=mgr_emp.employee_id,  # Manager is EMP002
                employment_status="ACTIVE",
                hire_date=date(2024, 3, 1),
            )
            session.add(staff_emp)
            await session.flush()

        stmt = select(UserAccount).where(UserAccount.login_email == "employee@hrgroup3.com")
        staff_acc = (await session.execute(stmt)).scalar_one_or_none()
        if not staff_acc:
            staff_acc = UserAccount(
                employee_id=staff_emp.employee_id,
                login_email="employee@hrgroup3.com",
                password_hash=get_password_hash("Password@123"),
                is_active=True
            )
            session.add(staff_acc)
            await session.flush()
            session.add(UserRoleAssignment(user_account_id=staff_acc.user_account_id, role_id=roles_map["EMPLOYEE"].role_id))
            await session.flush()

        # 7. Annual Leave Balances for 2026
        for emp in [admin_emp, mgr_emp, staff_emp]:
            stmt = select(EmployeeLeaveBalance).where(
                EmployeeLeaveBalance.employee_id == emp.employee_id,
                EmployeeLeaveBalance.year == 2026
            )
            bal = (await session.execute(stmt)).scalar_one_or_none()
            if not bal:
                bal = EmployeeLeaveBalance(
                    employee_id=emp.employee_id,
                    year=2026,
                    total_entitled_days=Decimal("12.00"),
                    used_days=Decimal("0.00"),
                    remaining_days=Decimal("12.00")
                )
                session.add(bal)

        # 8. Employee Compensation (Gross salaries)
        compensations = [
            (admin_emp.employee_id, Decimal("30000000.00"), Decimal("2000000.00")),
            (mgr_emp.employee_id, Decimal("25000000.00"), Decimal("1500000.00")),
            (staff_emp.employee_id, Decimal("18000000.00"), Decimal("1000000.00")),
        ]
        for emp_id, base_gross, allowance in compensations:
            stmt = select(EmployeeCompensation).where(EmployeeCompensation.employee_id == emp_id)
            comp = (await session.execute(stmt)).scalar_one_or_none()
            if not comp:
                comp = EmployeeCompensation(
                    employee_id=emp_id,
                    base_monthly_salary=base_gross,
                    fixed_allowance=allowance,
                    currency_code="VND",
                    effective_from=date(2026, 1, 1),
                    created_by_user_id=admin_acc.user_account_id
                )
                session.add(comp)

        # 9. Holidays in 2026
        holidays_data = [
            (date(2026, 1, 1), "Tết Dương Lịch"),
            (date(2026, 4, 30), "Ngày Giải phóng miền Nam"),
            (date(2026, 5, 1), "Ngày Quốc tế Lao động"),
            (date(2026, 9, 2), "Ngày Quốc khánh Việt Nam"),
        ]
        for h_date, h_name in holidays_data:
            stmt = select(Holiday).where(Holiday.holiday_date == h_date)
            holiday = (await session.execute(stmt)).scalar_one_or_none()
            if not holiday:
                holiday = Holiday(
                    holiday_date=h_date,
                    holiday_name=h_name,
                    is_paid=True,
                    created_by_user_id=admin_acc.user_account_id
                )
                session.add(holiday)

        # 10. Static QR Cards for Kiosk Scanning
        from app.models.attendance import QRCard
        from app.services.attendance_service import hash_token
        qr_cards_data = [
            (admin_emp.employee_id, "EMP001_QR_STATIC"),
            (mgr_emp.employee_id, "EMP002_QR_STATIC"),
            (staff_emp.employee_id, "EMP003_QR_STATIC"),
        ]
        for e_id, code in qr_cards_data:
            stmt = select(QRCard).where(QRCard.employee_id == e_id, QRCard.revoked_at.is_(None)).order_by(QRCard.issued_at.desc())
            existing_cards = (await session.execute(stmt)).scalars().all()
            if existing_cards:
                for idx, c in enumerate(existing_cards):
                    if idx == 0:
                        c.card_code = code
                        c.token_hash = hash_token(code)
                    else:
                        c.revoked_at = datetime.now(timezone.utc)
            else:
                card = QRCard(
                    employee_id=e_id,
                    token_hash=hash_token(code),
                    card_code=code,
                    issued_at=datetime.now(timezone.utc),
                    created_by_user_id=admin_acc.user_account_id
                )
                session.add(card)

        await session.commit()
        print("✅ Khởi tạo dữ liệu mẫu thành công!")
        print("   Tài khoản Admin / HR: admin@hrgroup3.com / Password@123")
        print("   Tài khoản Quản lý:    manager@hrgroup3.com / Password@123")
        print("   Tài khoản Nhân viên:  employee@hrgroup3.com / Password@123")


if __name__ == "__main__":
    asyncio.run(seed_data())
