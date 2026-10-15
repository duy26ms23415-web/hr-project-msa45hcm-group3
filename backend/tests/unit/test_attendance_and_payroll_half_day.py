import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal
from app.models.organization import Employee, Department, Position
from app.models.attendance import AttendanceDay, AttendanceEvent
from app.models.payroll import PayrollPeriod, PayrollLine, EmployeeCompensation
from app.models.leave import LeaveRequest, LeaveType
from app.services.attendance_service import AttendanceService
from app.services.payroll_service import PayrollService


@pytest.mark.asyncio
async def test_attendance_status_thresholds():
    """
    Verify Option A status rules:
    - >= 480 mins: PRESENT (1.0 công)
    - >= 240 mins and < 480 mins: HALF_DAY (0.5 công)
    - < 240 mins: INCOMPLETE (0.0 công)
    """
    async with AsyncSessionLocal() as db:
        emp = (await db.execute(select(Employee).where(Employee.employment_status == "ACTIVE"))).scalars().first()
        assert emp is not None

        test_date = date(2026, 11, 10)

        # Clear existing events & days for test_date
        await db.execute(delete(AttendanceEvent).where(AttendanceEvent.employee_id == emp.employee_id))
        await db.execute(delete(AttendanceDay).where(
            AttendanceDay.employee_id == emp.employee_id,
            AttendanceDay.work_date == test_date
        ))
        await db.commit()

        # Case 1: 08:00 to 12:00 VN (01:00 to 05:00 UTC) = 240 mins -> HALF_DAY
        ev_in_1 = AttendanceEvent(
            employee_id=emp.employee_id,
            event_type="CHECK_IN",
            source="TEST",
            occurred_at=datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc),
            idempotency_key="TEST-IN-1"
        )
        ev_out_1 = AttendanceEvent(
            employee_id=emp.employee_id,
            event_type="CHECK_OUT",
            source="TEST",
            occurred_at=datetime(2026, 11, 10, 5, 0, tzinfo=timezone.utc),
            idempotency_key="TEST-OUT-1"
        )
        db.add_all([ev_in_1, ev_out_1])
        await db.commit()

        await AttendanceService.recalculate_day(db, emp.employee_id, test_date)
        await db.commit()

        stmt = select(AttendanceDay).where(
            AttendanceDay.employee_id == emp.employee_id,
            AttendanceDay.work_date == test_date
        )
        day = (await db.execute(stmt)).scalar_one()
        assert day.worked_minutes == 240
        assert day.attendance_status == "HALF_DAY"

        # Case 2: Full day 08:00 to 17:00 VN (01:00 to 10:00 UTC) = 480 mins -> PRESENT
        ev_out_2 = AttendanceEvent(
            employee_id=emp.employee_id,
            event_type="CHECK_OUT",
            source="TEST",
            occurred_at=datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc),
            idempotency_key="TEST-OUT-2"
        )
        db.add(ev_out_2)
        await db.commit()

        await AttendanceService.recalculate_day(db, emp.employee_id, test_date)
        await db.commit()

        day = (await db.execute(stmt)).scalar_one()
        assert day.worked_minutes == 480
        assert day.attendance_status == "PRESENT"

        # Case 3: Less than 4 hours, e.g. 14:00 to 17:00 VN (07:00 to 10:00 UTC) = 180 mins -> INCOMPLETE
        await db.execute(delete(AttendanceEvent).where(AttendanceEvent.employee_id == emp.employee_id))
        ev_in_3 = AttendanceEvent(
            employee_id=emp.employee_id,
            event_type="CHECK_IN",
            source="TEST",
            occurred_at=datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc),
            idempotency_key="TEST-IN-3"
        )
        ev_out_3 = AttendanceEvent(
            employee_id=emp.employee_id,
            event_type="CHECK_OUT",
            source="TEST",
            occurred_at=datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc),
            idempotency_key="TEST-OUT-3"
        )
        db.add_all([ev_in_3, ev_out_3])
        await db.commit()

        await AttendanceService.recalculate_day(db, emp.employee_id, test_date)
        await db.commit()

        day = (await db.execute(stmt)).scalar_one()
        assert day.worked_minutes == 180
        assert day.attendance_status == "INCOMPLETE"

        # Clean up
        await db.execute(delete(AttendanceEvent).where(AttendanceEvent.employee_id == emp.employee_id))
        await db.execute(delete(AttendanceDay).where(
            AttendanceDay.employee_id == emp.employee_id,
            AttendanceDay.work_date == test_date
        ))
        await db.commit()


@pytest.mark.asyncio
async def test_payroll_calculation_half_day_and_leave_integration():
    """
    Verify PayrollService calculates actual_paid_days correctly:
    - PRESENT adds 1.0
    - HALF_DAY adds 0.5
    - HALF_DAY (0.5) + Paid Leave (0.5) adds 1.0 (capped at 1.0 per day)
    - INCOMPLETE adds 0.0
    """
    async with AsyncSessionLocal() as db:
        emp = (await db.execute(select(Employee).where(Employee.employment_status == "ACTIVE"))).scalars().first()
        assert emp is not None

        # Ensure compensation exists
        comp = (await db.execute(
            select(EmployeeCompensation).where(EmployeeCompensation.employee_id == emp.employee_id)
        )).scalars().first()
        if not comp:
            comp = EmployeeCompensation(
                employee_id=emp.employee_id,
                base_monthly_salary=Decimal("20000000"),
                fixed_allowance=Decimal("1000000"),
                effective_from=date(2026, 1, 1),
                is_active=True
            )
            db.add(comp)
            await db.commit()

        # Find or create a test payroll period for 2026-11
        period_year = 2026
        period_month = 11
        start_date = date(2026, 11, 1)
        end_date = date(2026, 11, 30)

        # Clean up any existing data for 2026-11
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

        # Set up 3 specific working days in Nov 2026:
        # Nov 2, 2026 (Monday): Full day PRESENT -> 1.0 công
        # Nov 3, 2026 (Tuesday): HALF_DAY (4 hours) -> 0.5 công
        # Nov 4, 2026 (Wednesday): HALF_DAY (4 hours) + Paid leave 0.5 -> 1.0 công
        # Nov 5, 2026 (Thursday): INCOMPLETE (< 4 hours) -> 0.0 công
        day1 = AttendanceDay(
            employee_id=emp.employee_id,
            work_date=date(2026, 11, 2),
            worked_minutes=480,
            attendance_status="PRESENT"
        )
        day2 = AttendanceDay(
            employee_id=emp.employee_id,
            work_date=date(2026, 11, 3),
            worked_minutes=240,
            attendance_status="HALF_DAY"
        )
        day3 = AttendanceDay(
            employee_id=emp.employee_id,
            work_date=date(2026, 11, 4),
            worked_minutes=240,
            attendance_status="HALF_DAY"
        )
        day4 = AttendanceDay(
            employee_id=emp.employee_id,
            work_date=date(2026, 11, 5),
            worked_minutes=180,
            attendance_status="INCOMPLETE"
        )
        db.add_all([day1, day2, day3, day4])

        # Approved paid leave on Nov 4 for 0.5 days
        paid_type = (await db.execute(select(LeaveType).where(LeaveType.is_paid == True))).scalars().first()
        leave_req = LeaveRequest(
            employee_id=emp.employee_id,
            leave_type_id=paid_type.leave_type_id,
            leave_date=date(2026, 11, 4),
            session="MORNING",
            leave_days=Decimal("0.5"),
            reason="Test morning leave",
            status="APPROVED"
        )
        db.add(leave_req)
        await db.commit()

        # Calculate payroll for period
        period = await PayrollService.calculate_period_payroll(db, period_year, period_month, user_id=1)

        # Check line for emp
        line_stmt = select(PayrollLine).where(
            PayrollLine.payroll_period_id == period.payroll_period_id,
            PayrollLine.employee_id == emp.employee_id
        )
        line = (await db.execute(line_stmt)).scalar_one()

        # Expected actual_work_days:
        # Day 1: 1.0
        # Day 2: 0.5
        # Day 3: min(1.0, 0.5 + 0.5) = 1.0
        # Day 4: 0.0
        # Total = 1.0 + 0.5 + 1.0 + 0.0 = 2.5 days!
        assert line.actual_work_days == Decimal("2.5")

        # Clean up
        await db.execute(delete(PayrollLine).where(PayrollLine.payroll_period_id == period.payroll_period_id))
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
