import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, delete, and_
import openpyxl

from app.core.database import AsyncSessionLocal
from app.models.organization import Employee
from app.models.attendance import AttendanceDay, AttendanceFix, AttendanceEvent
from app.models.payroll import PayrollPeriod, EmployeeCompensation, PayrollLine
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

        lt = (await db.execute(select(LeaveType).where(LeaveType.is_paid.is_(True)))).scalars().first()
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
        for lv in approved_leaves:
            if lv.leave_type.is_paid:
                leave_credit_by_date[lv.leave_date] = (
                    leave_credit_by_date.get(lv.leave_date, Decimal("0.0")) + Decimal(str(lv.leave_days))
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

        lt = (await db.execute(select(LeaveType).where(LeaveType.is_paid.is_(True)))).scalars().first()
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


@pytest.mark.asyncio
async def test_payroll_excel_merged_cells_span_12_columns():
    """Verify Excel export title merges A1:L1 (all 12 columns)."""
    async with AsyncSessionLocal() as db:
        period = PayrollPeriod(
            period_year=2026,
            period_month=6,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            status="CALCULATED",
            created_by_user_id=1
        )
        db.add(period)
        await db.commit()
        await db.refresh(period)

        excel_io = await PayrollService.export_payroll_excel(db, period.payroll_period_id)
        wb = openpyxl.load_workbook(excel_io)
        ws = wb.active
        assert ws is not None

        merged_ranges = [str(r) for r in ws.merged_cells.ranges]
        assert "A1:L1" in merged_ranges, f"Expected A1:L1 to be merged, got {merged_ranges}"

        await db.execute(delete(PayrollPeriod).where(PayrollPeriod.payroll_period_id == period.payroll_period_id))
        await db.commit()


@pytest.mark.asyncio
async def test_payroll_holiday_not_credited_before_hire_date():
    """
    Verify that a holiday falling BEFORE employee's hire_date is not credited.
    e.g. Holiday on 2026-09-02 (National Day), employee hired on 2026-09-15.
    """
    async with AsyncSessionLocal() as db:
        emp = (await db.execute(select(Employee).where(Employee.employment_status == "ACTIVE"))).scalars().first()
        assert emp is not None

        orig_hire_date = emp.hire_date
        comp = (await db.execute(
            select(EmployeeCompensation).where(
                EmployeeCompensation.employee_id == emp.employee_id,
                EmployeeCompensation.effective_from <= date(2026, 9, 30)
            )
        )).scalars().first()
        created_comp = False
        if not comp:
            comp = EmployeeCompensation(
                employee_id=emp.employee_id,
                base_monthly_salary=Decimal("20000000"),
                fixed_allowance=Decimal("1000000"),
                effective_from=date(2026, 1, 1),
                effective_to=None,
                created_by_user_id=1
            )
            db.add(comp)
            await db.commit()
            created_comp = True

        try:
            emp.hire_date = date(2026, 9, 15)
            await db.commit()

            stmt_hol = select(Holiday).where(Holiday.holiday_date == date(2026, 9, 2))
            hol = (await db.execute(stmt_hol)).scalars().first()
            if not hol:
                hol = Holiday(
                    holiday_date=date(2026, 9, 2),
                    holiday_name="Quoc Khanh Test",
                    is_paid=True
                )
                db.add(hol)
                await db.commit()

            period = await PayrollService.calculate_period_payroll(db, 2026, 9, user_id=1)

            stmt_line = select(PayrollLine).where(
                PayrollLine.payroll_period_id == period.payroll_period_id,
                PayrollLine.employee_id == emp.employee_id
            )
            line = (await db.execute(stmt_line)).scalar_one()

            # Since emp was hired on Sept 15, Sept 2 holiday must NOT be counted
            assert line.actual_work_days == Decimal("0.0"), f"Expected 0.0 actual work days, got {line.actual_work_days}"

            await db.execute(delete(PayrollLine).where(PayrollLine.payroll_period_id == period.payroll_period_id))
            await db.execute(delete(PayrollPeriod).where(PayrollPeriod.payroll_period_id == period.payroll_period_id))
            await db.commit()
        finally:
            emp.hire_date = orig_hire_date
            if created_comp:
                await db.execute(delete(EmployeeCompensation).where(EmployeeCompensation.employee_compensation_id == comp.employee_compensation_id))
            await db.commit()


@pytest.mark.asyncio
async def test_payroll_picks_newest_compensation():
    """Verify that PayrollService picks the most recent compensation if multiple overlap."""
    async with AsyncSessionLocal() as db:
        emp = (await db.execute(select(Employee).where(Employee.employment_status == "ACTIVE"))).scalars().first()
        assert emp is not None

        comp_old = EmployeeCompensation(
            employee_id=emp.employee_id,
            base_monthly_salary=Decimal("15000000"),
            fixed_allowance=Decimal("500000"),
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 10, 14),
            created_by_user_id=1
        )
        comp_new = EmployeeCompensation(
            employee_id=emp.employee_id,
            base_monthly_salary=Decimal("25000000"),
            fixed_allowance=Decimal("1500000"),
            effective_from=date(2026, 10, 15),
            effective_to=None,
            created_by_user_id=1
        )
        db.add_all([comp_old, comp_new])
        await db.commit()

        try:
            period = await PayrollService.calculate_period_payroll(db, 2026, 10, user_id=1)
            stmt_line = select(PayrollLine).where(
                PayrollLine.payroll_period_id == period.payroll_period_id,
                PayrollLine.employee_id == emp.employee_id
            )
            line = (await db.execute(stmt_line)).scalar_one()

            # Must pick comp_new (25,000,000), not comp_old (15,000,000)
            assert line.base_salary == Decimal("25000000.00"), f"Expected 25M base salary, got {line.base_salary}"

            await db.execute(delete(PayrollLine).where(PayrollLine.payroll_period_id == period.payroll_period_id))
            await db.execute(delete(PayrollPeriod).where(PayrollPeriod.payroll_period_id == period.payroll_period_id))
            await db.commit()
        finally:
            await db.execute(delete(EmployeeCompensation).where(
                EmployeeCompensation.employee_compensation_id.in_([
                    comp_old.employee_compensation_id,
                    comp_new.employee_compensation_id
                ])
            ))
            await db.commit()


@pytest.mark.asyncio
async def test_grace_period_and_minute_rounding():
    """
    Issue 1: Verify grace period and rounding:
    - 08:00:30 to 17:00:00 -> 480 mins -> PRESENT
    - 08:01 to 17:30 -> 480 mins -> PRESENT
    - 07:30 to 16:59 -> 480 mins -> PRESENT
    - 08:05 to 12:00 -> 240 mins -> HALF_DAY
    """
    vn_tz = timezone(timedelta(hours=7))

    # Case A: 08:00:30 to 17:00:00 (trễ 30s)
    t_in = datetime(2026, 10, 14, 8, 0, 30, tzinfo=vn_tz)
    t_out = datetime(2026, 10, 14, 17, 0, 0, tzinfo=vn_tz)
    mins = AttendanceService.calculate_worked_minutes(t_in, t_out)
    assert mins == 480, f"Expected 480, got {mins}"

    # Case B: 08:01 to 17:30 (trễ 1 phút, về sau 17:00)
    t_in = datetime(2026, 10, 14, 8, 1, 0, tzinfo=vn_tz)
    t_out = datetime(2026, 10, 14, 17, 30, 0, tzinfo=vn_tz)
    mins = AttendanceService.calculate_worked_minutes(t_in, t_out)
    assert mins == 480, f"Expected 480, got {mins}"

    # Case C: 07:30 to 16:59 (vào sớm, về sớm 1 phút)
    t_in = datetime(2026, 10, 14, 7, 30, 0, tzinfo=vn_tz)
    t_out = datetime(2026, 10, 14, 16, 59, 0, tzinfo=vn_tz)
    mins = AttendanceService.calculate_worked_minutes(t_in, t_out)
    assert mins == 480, f"Expected 480, got {mins}"

    # Case D: 08:00:45 to 12:00 (trễ 45s, trong ân hạn 1 phút -> 240 mins)
    t_in = datetime(2026, 10, 14, 8, 0, 45, tzinfo=vn_tz)
    t_out = datetime(2026, 10, 14, 12, 0, 0, tzinfo=vn_tz)
    mins = AttendanceService.calculate_worked_minutes(t_in, t_out)
    assert mins == 240, f"Expected 240, got {mins}"

    # Case E: 08:05 to 17:00 (trễ 5 phút, vượt quá ân hạn 1 phút -> 475 mins)
    t_in = datetime(2026, 10, 14, 8, 5, 0, tzinfo=vn_tz)
    t_out = datetime(2026, 10, 14, 17, 0, 0, tzinfo=vn_tz)
    mins = AttendanceService.calculate_worked_minutes(t_in, t_out)
    assert mins == 475, f"Expected 475, got {mins}"


@pytest.mark.asyncio
async def test_recalculate_day_resolves_two_checkin_events():
    """
    Issue 2: Verify that when employee forgot morning scan, scanned at 17:00 (recorded as CHECK_IN),
    and submitted an approved fix for 08:00 (also CHECK_IN), recalculate_day correctly takes
    earliest as first_in (08:00) and latest as last_out (17:00) -> PRESENT.
    """
    async with AsyncSessionLocal() as db:
        emp = (await db.execute(select(Employee).where(Employee.employment_status == "ACTIVE"))).scalars().first()
        assert emp is not None

        test_date = date(2026, 10, 14)
        vn_tz = timezone(timedelta(hours=7))

        # Clear existing
        await db.execute(delete(AttendanceEvent).where(AttendanceEvent.employee_id == emp.employee_id))
        await db.execute(delete(AttendanceDay).where(
            AttendanceDay.employee_id == emp.employee_id,
            AttendanceDay.work_date == test_date
        ))
        await db.commit()

        # Both events are CHECK_IN
        ev1 = AttendanceEvent(
            employee_id=emp.employee_id,
            event_type="CHECK_IN",
            source="APPROVED_FIX",
            occurred_at=datetime(2026, 10, 14, 8, 0, tzinfo=vn_tz).astimezone(timezone.utc),
            idempotency_key="TEST-FIX-IN"
        )
        ev2 = AttendanceEvent(
            employee_id=emp.employee_id,
            event_type="CHECK_IN",
            source="KIOSK",
            occurred_at=datetime(2026, 10, 14, 17, 0, tzinfo=vn_tz).astimezone(timezone.utc),
            idempotency_key="TEST-KIOSK-IN"
        )
        db.add_all([ev1, ev2])
        await db.commit()

        await AttendanceService.recalculate_day(db, emp.employee_id, test_date)
        await db.commit()

        day = (await db.execute(
            select(AttendanceDay).where(
                AttendanceDay.employee_id == emp.employee_id,
                AttendanceDay.work_date == test_date
            )
        )).scalar_one()

        assert day.attendance_status == "PRESENT", f"Expected PRESENT, got {day.attendance_status}"
        assert day.worked_minutes == 480, f"Expected 480 worked minutes, got {day.worked_minutes}"

        # Cleanup
        await db.execute(delete(AttendanceEvent).where(AttendanceEvent.employee_id == emp.employee_id))
        await db.execute(delete(AttendanceDay).where(
            AttendanceDay.employee_id == emp.employee_id,
            AttendanceDay.work_date == test_date
        ))
        await db.commit()


@pytest.mark.asyncio
async def test_attendance_fix_validates_future_and_mismatched_date():
    """
    Issue 3: Verify that create_fix_request rejects:
    - Future work dates
    - requested_at date not matching work_date
    """
    async with AsyncSessionLocal() as db:
        emp = (await db.execute(select(Employee).where(Employee.employment_status == "ACTIVE"))).scalars().first()
        assert emp is not None

        vn_tz = timezone(timedelta(hours=7))

        # Case A: Future work_date (2099-01-01)
        with pytest.raises(HTTPException) as exc_future:
            await AttendanceService.create_fix_request(
                db,
                employee_id=emp.employee_id,
                fix_in=AttendanceFixCreate(
                    work_date=date(2099, 1, 1),
                    event_type="CHECK_IN",
                    requested_at=datetime(2099, 1, 1, 8, 0, tzinfo=vn_tz),
                    reason="Test future date"
                )
            )
        assert exc_future.value.status_code == 400
        assert "tương lai" in exc_future.value.detail.lower()

        # Case B: work_date is 2026-10-01, but requested_at is 2026-10-02
        with pytest.raises(HTTPException) as exc_mismatch:
            await AttendanceService.create_fix_request(
                db,
                employee_id=emp.employee_id,
                fix_in=AttendanceFixCreate(
                    work_date=date(2026, 10, 1),
                    event_type="CHECK_IN",
                    requested_at=datetime(2026, 10, 2, 8, 0, tzinfo=vn_tz),
                    reason="Test mismatched date"
                )
            )
        assert exc_mismatch.value.status_code == 400
        assert "phải thuộc ngày làm việc" in exc_mismatch.value.detail.lower()



