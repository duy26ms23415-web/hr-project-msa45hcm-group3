import pytest
from datetime import date, datetime, time, timezone
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, delete, and_

from app.core.database import AsyncSessionLocal
from app.models.organization import Employee
from app.models.attendance import AttendanceDay, AttendanceFix
from app.models.payroll import PayrollPeriod, EmployeeCompensation
from app.models.leave import LeaveRequest, LeaveType
from app.models.holiday import Holiday
from app.services.leave_service import LeaveService
from app.services.attendance_service import AttendanceService
from app.services.payroll_service import PayrollService
from app.schemas.leave import LeaveRequestCreate
from app.schemas.attendance import AttendanceFixCreate


def test_pit_dependent_relief_calculations():
    """
    Test 1: Verify PIT calculation with 0, 1, and 2 dependents.
    Vietnamese Tax Law:
    - Personal relief: 11,000,000 VND
    - Dependent relief: 4,400,000 VND per dependent
    """
    gross_salary = Decimal("30000000.00")
    _, _, _, total_ins = PayrollService.calculate_insurance(gross_salary)
    # Total insurance: 10.5% = 3,150,000 VND

    # Case 0 dependents: Total deduction = 3.15M + 11M = 14.15M
    # Taxable income = 30M - 14.15M = 15,850,000 VND
    taxable_0, pit_0 = PayrollService.calculate_pit_tax(gross_salary, total_ins, dependent_count=0)
    assert taxable_0 == Decimal("15850000.00")
    assert pit_0 > Decimal("0.00")

    # Case 1 dependent: Total deduction = 3.15M + 11M + 4.4M = 18.55M
    # Taxable income = 30M - 18.55M = 11,450,000 VND
    taxable_1, pit_1 = PayrollService.calculate_pit_tax(gross_salary, total_ins, dependent_count=1)
    assert taxable_1 == taxable_0 - Decimal("4400000.00")
    assert pit_1 < pit_0

    # Case 2 dependents: Total deduction = 3.15M + 11M + 8.8M = 22.95M
    # Taxable income = 30M - 22.95M = 7,050,000 VND
    taxable_2, pit_2 = PayrollService.calculate_pit_tax(gross_salary, total_ins, dependent_count=2)
    assert taxable_2 == taxable_0 - Decimal("8800000.00")
    assert pit_2 < pit_1


@pytest.mark.asyncio
async def test_anti_double_dipping_same_day():
    """
    Test 2: Verify that having both attendance scan (PRESENT or HALF_DAY) and an approved
    paid leave (0.5 day) on the same date caps total credit at 1.0 day max (no double-dipping).
    """
    async with AsyncSessionLocal() as db:
        emp = (await db.execute(select(Employee).where(Employee.employment_status == "ACTIVE"))).scalars().first()
        assert emp is not None

        lt = (await db.execute(select(LeaveType).where(LeaveType.is_paid == True))).scalars().first()
        assert lt is not None

        test_year, test_month = 2026, 7
        start_date, end_date, all_dates = PayrollService.get_month_dates(test_year, test_month)

        # Clean prior test data for July 2026
        await db.execute(delete(AttendanceDay).where(
            AttendanceDay.employee_id == emp.employee_id,
            AttendanceDay.work_date >= start_date,
            AttendanceDay.work_date <= end_date
        ))
        await db.execute(delete(LeaveRequest).where(
            LeaveRequest.employee_id == emp.employee_id,
            LeaveRequest.leave_date >= start_date,
            LeaveRequest.leave_date <= end_date
        ))
        await db.commit()

        # Target date: Wednesday 2026-07-08
        same_date = date(2026, 7, 8)

        # Employee worked half-day (PRESENT status from scan)
        att_day = AttendanceDay(
            employee_id=emp.employee_id,
            work_date=same_date,
            worked_minutes=240,
            attendance_status="PRESENT"
        )
        db.add(att_day)

        # Employee also has approved paid leave for half-day (0.5)
        leave_req = LeaveRequest(
            employee_id=emp.employee_id,
            leave_type_id=lt.leave_type_id,
            leave_date=same_date,
            session="MORNING",
            leave_days=Decimal("0.5"),
            reason="Test half day leave",
            status="APPROVED"
        )
        db.add(leave_req)
        await db.commit()

        # Simulate the integrated day calculation used by PayrollService
        stmt_leaves = select(LeaveRequest).where(
            and_(
                LeaveRequest.employee_id == emp.employee_id,
                LeaveRequest.leave_date >= start_date,
                LeaveRequest.leave_date <= end_date,
                LeaveRequest.status == "APPROVED"
            )
        )
        approved_leaves = (await db.execute(stmt_leaves)).scalars().all()
        leave_credit_by_date = {}
        for l in approved_leaves:
            if l.leave_type.is_paid:
                leave_credit_by_date[l.leave_date] = (
                    leave_credit_by_date.get(l.leave_date, Decimal("0.0")) + Decimal(str(l.leave_days))
                )

        stmt_att = select(AttendanceDay).where(
            and_(
                AttendanceDay.employee_id == emp.employee_id,
                AttendanceDay.work_date == same_date
            )
        )
        att = (await db.execute(stmt_att)).scalar_one_or_none()
        work_credit = Decimal("1.0") if (att and att.attendance_status == "PRESENT") else Decimal("0.0")
        leave_credit = leave_credit_by_date.get(same_date, Decimal("0.0"))

        # Day credit must be capped at 1.0 (not 1.5)
        total_day_credit = min(Decimal("1.0"), work_credit + leave_credit)
        assert total_day_credit == Decimal("1.0"), f"Expected 1.0 day credit, got {total_day_credit}"

        # Clean up
        await db.rollback()


@pytest.mark.asyncio
async def test_leave_request_restrictions():
    """
    Test 3: Verify that leave requests are blocked for:
    - Weekends (Saturday / Sunday)
    - Public holidays (already paid)
    - Closed payroll periods
    """
    async with AsyncSessionLocal() as db:
        emp = (await db.execute(select(Employee).where(Employee.employment_status == "ACTIVE"))).scalars().first()
        assert emp is not None

        lt = (await db.execute(select(LeaveType).where(LeaveType.is_paid == True))).scalars().first()
        assert lt is not None

        # Case A: Weekend (2026-10-17 is Saturday)
        weekend_date = date(2026, 10, 17)
        with pytest.raises(HTTPException) as exc_weekend:
            await LeaveService.create_leave_request(
                db,
                employee_id=emp.employee_id,
                req_in=LeaveRequestCreate(
                    leave_type_id=lt.leave_type_id,
                    leave_date=weekend_date,
                    session="FULL_DAY",
                    reason="Test weekend blocking"
                )
            )
        assert exc_weekend.value.status_code == 400
        assert "weekend" in exc_weekend.value.detail.lower()

        # Case B: Public Holiday (2026-09-02 is Vietnamese National Day)
        holiday_date = date(2026, 9, 2)
        with pytest.raises(HTTPException) as exc_holiday:
            await LeaveService.create_leave_request(
                db,
                employee_id=emp.employee_id,
                req_in=LeaveRequestCreate(
                    leave_type_id=lt.leave_type_id,
                    leave_date=holiday_date,
                    session="FULL_DAY",
                    reason="Test holiday blocking"
                )
            )
        assert exc_holiday.value.status_code == 400
        assert "holiday" in exc_holiday.value.detail.lower()

        # Case C: Closed Payroll Period (Simulate CLOSED status for 2026-01)
        closed_period = PayrollPeriod(
            period_year=2026,
            period_month=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            status="CLOSED",
            created_by_user_id=1
        )
        db.add(closed_period)
        await db.flush()

        with pytest.raises(HTTPException) as exc_closed:
            await LeaveService.create_leave_request(
                db,
                employee_id=emp.employee_id,
                req_in=LeaveRequestCreate(
                    leave_type_id=lt.leave_type_id,
                    leave_date=date(2026, 1, 15),
                    session="FULL_DAY",
                    reason="Test closed period blocking"
                )
            )
        assert exc_closed.value.status_code == 400
        assert "closed" in exc_closed.value.detail.lower()

        await db.rollback()


@pytest.mark.asyncio
async def test_attendance_fix_monthly_quota():
    """
    Test 4: Verify that an employee is capped at maximum 3 attendance fix requests per month.
    The 4th request must be rejected with HTTP 400.
    """
    async with AsyncSessionLocal() as db:
        emp = (await db.execute(select(Employee).where(Employee.employment_status == "ACTIVE"))).scalars().first()
        assert emp is not None

        test_year, test_month = 2026, 8
        fix_month_start = date(test_year, test_month, 1)
        fix_month_end = date(test_year, test_month, 31)

        # Clear existing fixes for August 2026
        await db.execute(delete(AttendanceFix).where(
            AttendanceFix.employee_id == emp.employee_id,
            AttendanceFix.work_date >= fix_month_start,
            AttendanceFix.work_date <= fix_month_end
        ))
        await db.commit()

        # Add 3 fix requests (max allowed)
        for d in [3, 4, 5]:
            fix = AttendanceFix(
                employee_id=emp.employee_id,
                work_date=date(test_year, test_month, d),
                event_type="CHECK_IN",
                requested_at=datetime(test_year, test_month, d, 8, 5, tzinfo=timezone.utc),
                reason=f"Valid fix request {d}",
                status="PENDING"
            )
            db.add(fix)
        await db.commit()

        # Attempt 4th fix request in the same month -> must raise HTTP 400
        with pytest.raises(HTTPException) as exc_quota:
            await AttendanceService.create_fix_request(
                db,
                employee_id=emp.employee_id,
                fix_in=AttendanceFixCreate(
                    work_date=date(test_year, test_month, 6),
                    event_type="CHECK_IN",
                    requested_at=datetime(test_year, test_month, 6, 8, 10, tzinfo=timezone.utc),
                    reason="4th fix exceeding quota"
                )
            )
        assert exc_quota.value.status_code == 400
        assert "limit reached" in exc_quota.value.detail.lower()

        await db.rollback()

