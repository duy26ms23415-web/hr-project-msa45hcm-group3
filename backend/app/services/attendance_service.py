import hashlib
import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.organization import Employee
from app.models.attendance import QRCard, AttendanceEvent, AttendanceDay, AttendanceFix
from app.models.payroll import PayrollPeriod
from app.schemas.attendance import ScanRequest, AttendanceFixCreate, AttendanceFixReview


def hash_token(raw_token: str) -> str:
    """Hash raw QR token using SHA-256"""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class AttendanceService:
    @staticmethod
    def calculate_worked_minutes(check_in: Optional[datetime], check_out: Optional[datetime]) -> int:
        """
        Calculate worked minutes within 08:00 - 17:00 excluding lunch break (12:00 - 13:00).
        """
        if not check_in or not check_out or check_out <= check_in:
            return 0
        
        # Localize or normalize to same date
        start_time = check_in.time()
        end_time = check_out.time()

        # Office window: 08:00 to 17:00
        w_start = time(8, 0)
        w_end = time(17, 0)
        l_start = time(12, 0)
        l_end = time(13, 0)

        eff_start = max(start_time, w_start)
        eff_end = min(end_time, w_end)

        if eff_end <= eff_start:
            return 0

        total_seconds = (datetime.combine(check_in.date(), eff_end) - datetime.combine(check_in.date(), eff_start)).total_seconds()
        total_minutes = int(total_seconds // 60)

        # Subtract lunch break overlap (between 12:00 and 13:00)
        overlap_start = max(eff_start, l_start)
        overlap_end = min(eff_end, l_end)
        if overlap_end > overlap_start:
            lunch_minutes = int((datetime.combine(check_in.date(), overlap_end) - datetime.combine(check_in.date(), overlap_start)).total_seconds() // 60)
            total_minutes -= lunch_minutes

        return max(0, total_minutes)

    @staticmethod
    async def issue_qr_card(db: AsyncSession, employee_id: int, creator_user_id: int) -> Tuple[QRCard, str]:
        """Issue a new static physical QR card for an employee"""
        stmt = select(Employee).where(Employee.employee_id == employee_id)
        emp = (await db.execute(stmt)).scalar_one_or_none()
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        # Generate unique random opaque token
        raw_token = f"HRG3-{secrets.token_hex(24)}"
        t_hash = hash_token(raw_token)

        qr_card = QRCard(
            employee_id=employee_id,
            token_hash=t_hash,
            issued_at=datetime.now(timezone.utc),
            created_by_user_id=creator_user_id
        )
        db.add(qr_card)
        await db.flush()
        return qr_card, raw_token

    @staticmethod
    async def record_scan(db: AsyncSession, scan_in: ScanRequest) -> AttendanceEvent:
        """Process Kiosk Web QR scan event and update day attendance aggregate"""
        t_hash = hash_token(scan_in.qr_token)
        stmt = select(QRCard).where(
            and_(
                QRCard.token_hash == t_hash,
                QRCard.revoked_at.is_(None)
            )
        ).options(selectinload(QRCard.employee))
        qr_card = (await db.execute(stmt)).scalar_one_or_none()

        if not qr_card:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or revoked QR card")
        if qr_card.expires_at and qr_card.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR card has expired")

        # Check idempotency key to prevent double scan
        stmt_dup = select(AttendanceEvent).where(AttendanceEvent.idempotency_key == scan_in.idempotency_key)
        existing_event = (await db.execute(stmt_dup)).scalar_one_or_none()
        if existing_event:
            return existing_event

        now_utc = datetime.now(timezone.utc)
        # In Vietnam timezone (UTC+7)
        local_date = (now_utc + timedelta(hours=7)).date()

        event = AttendanceEvent(
            employee_id=qr_card.employee_id,
            qr_card_id=qr_card.qr_card_id,
            event_type=scan_in.event_type,
            source="QR_SCAN",
            occurred_at=now_utc,
            device_id=scan_in.device_id,
            idempotency_key=scan_in.idempotency_key
        )
        db.add(event)
        await db.flush()

        # Update daily aggregate
        await AttendanceService.recalculate_day(db, qr_card.employee_id, local_date)
        return event

    @staticmethod
    async def recalculate_day(db: AsyncSession, employee_id: int, work_date: date):
        """Aggregate all valid scan/fix events for the employee on work_date"""
        # Fetch all events on this date (converted to local date UTC+7)
        day_start_utc = datetime.combine(work_date, time(0, 0)) - timedelta(hours=7)
        day_end_utc = datetime.combine(work_date, time(23, 59, 59)) - timedelta(hours=7)

        stmt = select(AttendanceEvent).where(
            and_(
                AttendanceEvent.employee_id == employee_id,
                AttendanceEvent.occurred_at >= day_start_utc,
                AttendanceEvent.occurred_at <= day_end_utc
            )
        ).order_by(AttendanceEvent.occurred_at.asc())
        events = (await db.execute(stmt)).scalars().all()

        check_ins = [e.occurred_at for e in events if e.event_type == "CHECK_IN"]
        check_outs = [e.occurred_at for e in events if e.event_type == "CHECK_OUT"]

        first_in = check_ins[0] if check_ins else None
        last_out = check_outs[-1] if check_outs else None

        worked_mins = 0
        if first_in and last_out:
            worked_mins = AttendanceService.calculate_worked_minutes(first_in, last_out)

        # Status evaluation
        if first_in and last_out:
            att_status = "PRESENT" if worked_mins >= 240 else "INCOMPLETE"
        elif first_in or last_out:
            att_status = "INCOMPLETE"
        else:
            att_status = "ABSENT"

        # Update or insert hr_attendance_days
        stmt_day = select(AttendanceDay).where(
            and_(
                AttendanceDay.employee_id == employee_id,
                AttendanceDay.work_date == work_date
            )
        )
        day_record = (await db.execute(stmt_day)).scalar_one_or_none()

        if not day_record:
            day_record = AttendanceDay(
                employee_id=employee_id,
                work_date=work_date,
                first_check_in_at=first_in,
                last_check_out_at=last_out,
                worked_minutes=worked_mins,
                attendance_status=att_status
            )
            db.add(day_record)
        else:
            day_record.first_check_in_at = first_in
            day_record.last_check_out_at = last_out
            day_record.worked_minutes = worked_mins
            day_record.attendance_status = att_status

        await db.flush()

    @staticmethod
    async def create_fix_request(
        db: AsyncSession,
        employee_id: int,
        fix_in: AttendanceFixCreate
    ) -> AttendanceFix:
        """Create a pending attendance fix/justification request"""
        # Check duplicate pending request
        stmt = select(AttendanceFix).where(
            and_(
                AttendanceFix.employee_id == employee_id,
                AttendanceFix.work_date == fix_in.work_date,
                AttendanceFix.event_type == fix_in.event_type,
                AttendanceFix.status == "PENDING"
            )
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A pending fix request for {fix_in.event_type} on {fix_in.work_date} already exists"
            )

        # Check monthly cut-off
        stmt_period = select(PayrollPeriod).where(
            and_(
                PayrollPeriod.period_year == fix_in.work_date.year,
                PayrollPeriod.period_month == fix_in.work_date.month,
                PayrollPeriod.status == "CLOSED"
            )
        )
        closed_period = (await db.execute(stmt_period)).scalar_one_or_none()
        if closed_period:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payroll period for this month is already CLOSED. Late adjustments are forfeited."
            )

        fix = AttendanceFix(
            employee_id=employee_id,
            work_date=fix_in.work_date,
            event_type=fix_in.event_type,
            requested_at=fix_in.requested_at,
            reason=fix_in.reason,
            status="PENDING"
        )
        db.add(fix)
        await db.flush()
        return fix

    @staticmethod
    async def review_fix_request(
        db: AsyncSession,
        fix_id: int,
        reviewer_employee_id: int,
        review_in: AttendanceFixReview,
        is_admin: bool = False
    ) -> AttendanceFix:
        """Review attendance fix. Must be the employee's direct manager or admin."""
        stmt = select(AttendanceFix).where(AttendanceFix.attendance_fix_id == fix_id).options(
            selectinload(AttendanceFix.employee)
        )
        fix = (await db.execute(stmt)).scalar_one_or_none()
        if not fix:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance fix request not found")
        if fix.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request is already {fix.status}")

        # Manager authority check
        if not is_admin and fix.employee.manager_employee_id != reviewer_employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the direct manager can approve or reject this attendance fix"
            )

        # Check monthly cut-off
        stmt_period = select(PayrollPeriod).where(
            and_(
                PayrollPeriod.period_year == fix.work_date.year,
                PayrollPeriod.period_month == fix.work_date.month,
                PayrollPeriod.status == "CLOSED"
            )
        )
        closed_period = (await db.execute(stmt_period)).scalar_one_or_none()
        if closed_period:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot review fix request. Payroll period for this month is already CLOSED."
            )

        now_utc = datetime.now(timezone.utc)
        fix.status = review_in.status
        fix.reviewer_employee_id = reviewer_employee_id
        fix.reviewed_at = now_utc
        fix.review_note = review_in.review_note

        if review_in.status == "APPROVED":
            # Generate approved adjustment event
            event = AttendanceEvent(
                employee_id=fix.employee_id,
                event_type=fix.event_type,
                source="APPROVED_FIX",
                occurred_at=fix.requested_at,
                idempotency_key=f"FIX-APPROVED-{fix.attendance_fix_id}-{secrets.token_hex(6)}",
                attendance_fix_id=fix.attendance_fix_id
            )
            db.add(event)
            await db.flush()

            # Recalculate day
            await AttendanceService.recalculate_day(db, fix.employee_id, fix.work_date)

        await db.flush()
        return fix
