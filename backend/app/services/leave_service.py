from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.organization import Employee
from app.models.auth import Role, UserAccount, UserRoleAssignment
from app.models.leave import LeaveType, EmployeeLeaveBalance, LeaveRequest
from app.models.attendance import AttendanceDay
from app.models.holiday import Holiday
from app.models.payroll import PayrollPeriod
from app.schemas.leave import LeaveRequestCreate, LeaveRequestReview


class LeaveService:
    @staticmethod
    def calculate_leave_days(session: str) -> Decimal:
        """Return days value based on session: MORNING=0.5, AFTERNOON=0.5, FULL_DAY=1.0"""
        if session in ("MORNING", "AFTERNOON"):
            return Decimal("0.5")
        elif session == "FULL_DAY":
            return Decimal("1.0")
        raise ValueError(f"Invalid session {session}")

    @staticmethod
    async def get_or_create_balance(db: AsyncSession, employee_id: int, year: int) -> EmployeeLeaveBalance:
        """Get or initialize employee leave quota for a given year.
        Default quota is 12 days per year, except for MANAGER role which receives 18 days per year.
        """
        stmt = select(EmployeeLeaveBalance).where(
            and_(
                EmployeeLeaveBalance.employee_id == employee_id,
                EmployeeLeaveBalance.year == year
            )
        )
        balance = (await db.execute(stmt)).scalar_one_or_none()

        # Check if employee has MANAGER role
        stmt_roles = (
            select(Role.role_code)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.role_id)
            .join(UserAccount, UserAccount.user_account_id == UserRoleAssignment.user_account_id)
            .where(UserAccount.employee_id == employee_id)
        )
        roles = (await db.execute(stmt_roles)).scalars().all()
        is_manager = "MANAGER" in roles
        standard_quota = Decimal("18.00") if is_manager else Decimal("12.00")

        if not balance:
            balance = EmployeeLeaveBalance(
                employee_id=employee_id,
                year=year,
                total_entitled_days=standard_quota,
                used_days=Decimal("0.00"),
                remaining_days=standard_quota
            )
            db.add(balance)
            await db.flush()
        else:
            # If employee has MANAGER role and their balance record has the old 12.00 default, upgrade to 18.00
            if is_manager and balance.total_entitled_days == Decimal("12.00"):
                diff = Decimal("18.00") - balance.total_entitled_days
                balance.total_entitled_days = Decimal("18.00")
                balance.remaining_days = balance.remaining_days + diff
                await db.flush()

        return balance

    @staticmethod
    async def create_leave_request(
        db: AsyncSession,
        employee_id: int,
        req_in: LeaveRequestCreate
    ) -> LeaveRequest:
        """Create leave request with validation on session and annual leave quota"""
        # [FIX #2] Reject leave requests on weekends (Sat/Sun)
        if req_in.leave_date.weekday() >= 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot request leave on a weekend ({req_in.leave_date}). "
                       f"Leave is only valid on working days (Mon-Fri)."
            )

        # [FIX #2] Reject leave requests on public holidays (already paid, no leave needed)
        stmt_holiday = select(Holiday).where(Holiday.holiday_date == req_in.leave_date)
        holiday = (await db.execute(stmt_holiday)).scalar_one_or_none()
        if holiday:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot request leave on a public holiday: "
                       f"{holiday.holiday_name} ({req_in.leave_date}). "
                       f"Holidays are already paid days off."
            )

        # [FIX #3] Block leave request when payroll period is already CLOSED
        stmt_period = select(PayrollPeriod).where(
            and_(
                PayrollPeriod.period_year == req_in.leave_date.year,
                PayrollPeriod.period_month == req_in.leave_date.month,
                PayrollPeriod.status == "CLOSED"
            )
        )
        closed_period = (await db.execute(stmt_period)).scalar_one_or_none()
        if closed_period:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payroll period for this month is already CLOSED. "
                       "Leave requests can no longer be submitted."
            )

        # Validate leave type
        stmt_type = select(LeaveType).where(LeaveType.leave_type_id == req_in.leave_type_id)
        l_type = (await db.execute(stmt_type)).scalar_one_or_none()
        if not l_type or not l_type.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or inactive leave type")

        leave_days = LeaveService.calculate_leave_days(req_in.session)

        # Check existing non-cancelled request on same date & session
        stmt_exist = select(LeaveRequest).where(
            and_(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.leave_date == req_in.leave_date,
                LeaveRequest.status.in_(["PENDING", "APPROVED"])
            )
        )
        existing_requests = (await db.execute(stmt_exist)).scalars().all()
        for r in existing_requests:
            if r.session == req_in.session or r.session == "FULL_DAY" or req_in.session == "FULL_DAY":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"An active leave request already exists for {req_in.leave_date} ({r.session})"
                )

        # Check quota if it's paid annual leave (REMOTE and other paid types do not consume annual leave quota)
        if l_type.leave_code == "ANNUAL":
            year = req_in.leave_date.year
            balance = await LeaveService.get_or_create_balance(db, employee_id, year)
            if balance.remaining_days < leave_days:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Insufficient paid leave balance! Remaining: {balance.remaining_days} days. "
                        f"Requested: {leave_days} days. You must request UNPAID leave."
                    )
                )

        leave_req = LeaveRequest(
            employee_id=employee_id,
            leave_type_id=req_in.leave_type_id,
            leave_date=req_in.leave_date,
            session=req_in.session,
            leave_days=leave_days,
            reason=req_in.reason,
            status="PENDING"
        )
        db.add(leave_req)
        await db.flush()
        return leave_req

    @staticmethod
    async def review_leave_request(
        db: AsyncSession,
        leave_request_id: int,
        reviewer_employee_id: int,
        review_in: LeaveRequestReview,
        is_admin: bool = False
    ) -> LeaveRequest:
        """Manager approves or rejects leave request and updates leave balance if approved"""
        stmt = (
            select(LeaveRequest)
            .where(LeaveRequest.leave_request_id == leave_request_id)
            # Serialize reviews before reading status; refresh any cached ORM instance.
            .with_for_update()
            .execution_options(populate_existing=True)
            .options(
                selectinload(LeaveRequest.employee).selectinload(Employee.department),
                selectinload(LeaveRequest.leave_type)
            )
        )
        req = (await db.execute(stmt)).scalar_one_or_none()
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
        if req.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request is already {req.status}")

        # Lock the employee row so reassignment cannot race the authorization check and commit.
        employee = (await db.execute(
            select(Employee).where(Employee.employee_id == req.employee_id).options(selectinload(Employee.department)).with_for_update()
        )).scalar_one_or_none()
        if not employee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        is_direct_manager = (
            employee.manager_employee_id == reviewer_employee_id
            or (getattr(employee, "department", None) and employee.department.manager_employee_id == reviewer_employee_id)
        )
        if req.employee_id == reviewer_employee_id or (not is_admin and not is_direct_manager):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the direct manager can approve or reject this leave request"
            )

        # [FIX #3] Block approval when payroll period is already CLOSED
        leave_date = getattr(req, "leave_date", None)
        if leave_date:
            stmt_period = select(PayrollPeriod).where(
                and_(
                    PayrollPeriod.period_year == leave_date.year,
                    PayrollPeriod.period_month == leave_date.month,
                    PayrollPeriod.status == "CLOSED"
                )
            )
            closed_period = (await db.execute(stmt_period)).scalar_one_or_none()
            if closed_period:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot review leave request. Payroll period for this month is already CLOSED."
                )

        now_utc = datetime.now(timezone.utc)
        req.status = review_in.status
        req.reviewer_employee_id = reviewer_employee_id
        req.reviewed_at = now_utc
        req.review_note = review_in.review_note

        if review_in.status == "APPROVED":
            # If annual leave, deduct balance (Remote does not consume annual leave quota)
            if req.leave_type.leave_code == "ANNUAL":
                year = req.leave_date.year
                balance = await LeaveService.get_or_create_balance(db, req.employee_id, year)
                balance.used_days += req.leave_days
                balance.remaining_days = max(Decimal("0.00"), balance.total_entitled_days - balance.used_days)
                balance.updated_at = now_utc

            # [FIX #5] Update day attendance with race condition protection.
            # For half-day leave, preserve existing scan data (PRESENT status) for the other half
            # instead of blindly overwriting the entire record.
            att_status = "REMOTE" if req.leave_type.leave_code == "REMOTE" else "ON_LEAVE"
            leave_mins = int(req.leave_days * 480) if req.leave_type.is_paid else 0
            is_half_day = req.leave_days == Decimal("0.5")

            stmt_day = select(AttendanceDay).where(
                and_(
                    AttendanceDay.employee_id == req.employee_id,
                    AttendanceDay.work_date == req.leave_date
                )
            )
            day_rec = (await db.execute(stmt_day)).scalar_one_or_none()
            if not day_rec:
                day_rec = AttendanceDay(
                    employee_id=req.employee_id,
                    work_date=req.leave_date,
                    worked_minutes=leave_mins,
                    attendance_status=att_status
                )
                db.add(day_rec)
            else:
                has_real_scan = day_rec.first_check_in_at is not None
                if is_half_day and has_real_scan:
                    # Half-day leave + employee has real scan data for the other half:
                    # Keep PRESENT status so payroll correctly integrates both halves
                    if req.leave_type.is_paid:
                        day_rec.worked_minutes = max(day_rec.worked_minutes or 0, leave_mins)
                else:
                    # Full-day leave or no existing scan: safe to set leave status
                    day_rec.attendance_status = att_status
                    if req.leave_type.is_paid:
                        day_rec.worked_minutes = max(day_rec.worked_minutes or 0, leave_mins)

        await db.flush()
        return req
