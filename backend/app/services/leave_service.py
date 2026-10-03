from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.organization import Employee
from app.models.leave import LeaveType, EmployeeLeaveBalance, LeaveRequest
from app.models.attendance import AttendanceDay
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
        """Get or initialize employee leave quota for a given year"""
        stmt = select(EmployeeLeaveBalance).where(
            and_(
                EmployeeLeaveBalance.employee_id == employee_id,
                EmployeeLeaveBalance.year == year
            )
        )
        balance = (await db.execute(stmt)).scalar_one_or_none()
        if not balance:
            # Default quota is 12 days per year
            balance = EmployeeLeaveBalance(
                employee_id=employee_id,
                year=year,
                total_entitled_days=Decimal("12.00"),
                used_days=Decimal("0.00"),
                remaining_days=Decimal("12.00")
            )
            db.add(balance)
            await db.flush()
        return balance

    @staticmethod
    async def create_leave_request(
        db: AsyncSession,
        employee_id: int,
        req_in: LeaveRequestCreate
    ) -> LeaveRequest:
        """Create leave request with validation on session and annual leave quota"""
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

        # Check quota if it's paid annual leave
        if l_type.is_paid:
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
            .options(
                selectinload(LeaveRequest.employee),
                selectinload(LeaveRequest.leave_type)
            )
        )
        req = (await db.execute(stmt)).scalar_one_or_none()
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
        if req.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request is already {req.status}")

        # Manager authority check
        if not is_admin and req.employee.manager_employee_id != reviewer_employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the direct manager can approve or reject this leave request"
            )

        now_utc = datetime.now(timezone.utc)
        req.status = review_in.status
        req.reviewer_employee_id = reviewer_employee_id
        req.reviewed_at = now_utc
        req.review_note = review_in.review_note

        if review_in.status == "APPROVED":
            # If paid leave, deduct balance
            if req.leave_type.is_paid:
                year = req.leave_date.year
                balance = await LeaveService.get_or_create_balance(db, req.employee_id, year)
                balance.used_days += req.leave_days
                balance.remaining_days = max(Decimal("0.00"), balance.total_entitled_days - balance.used_days)
                balance.updated_at = now_utc

            # Update day attendance
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
                    worked_minutes=int(req.leave_days * 480) if req.leave_type.is_paid else 0,
                    attendance_status="ON_LEAVE"
                )
                db.add(day_rec)
            else:
                day_rec.attendance_status = "ON_LEAVE"

        await db.flush()
        return req
