import calendar
import hashlib
import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
# pyrefly: ignore [missing-import]
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
        Times are normalized to Vietnam timezone (UTC+7).
        """
        if not check_in or not check_out:
            return 0

        # PostgreSQL stores UTC timestamps. Legacy naive values are treated as UTC.
        local_timezone = timezone(timedelta(hours=7))
        def to_local(value: datetime) -> datetime:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(local_timezone)

        local_in = to_local(check_in)
        local_out = to_local(check_out)
        if local_out <= local_in:
            return 0


        work_date = local_in.date()
        window_start = datetime.combine(work_date, time(8, 0), tzinfo=local_timezone)
        window_end = datetime.combine(work_date, time(17, 0), tzinfo=local_timezone)

        # 1-minute grace period for morning arrival:
        # Check-in between 08:00 and 08:01 is credited as 08:00
        if window_start <= local_in <= window_start + timedelta(minutes=1):
            effective_start = window_start
        else:
            # Drop seconds so seconds don't truncate a whole minute
            effective_start = max(local_in.replace(second=0, microsecond=0), window_start)

        # 1-minute grace period for evening departure:
        # Check-out between 16:59 and 17:00 is credited as 17:00
        if window_end - timedelta(minutes=1) <= local_out <= window_end:
            effective_end = window_end
        else:
            # Round check-out seconds to nearest minute
            rounded_out = local_out.replace(second=0, microsecond=0)
            if local_out.second >= 30:
                rounded_out += timedelta(minutes=1)
            effective_end = min(rounded_out, window_end)

        if effective_end <= effective_start:
            return 0

        lunch_start = datetime.combine(work_date, time(12, 0), tzinfo=local_timezone)
        lunch_end = datetime.combine(work_date, time(13, 0), tzinfo=local_timezone)
        lunch_overlap = max(
            0, (min(effective_end, lunch_end) - max(effective_start, lunch_start)).total_seconds()
        )
        worked_seconds = (effective_end - effective_start).total_seconds() - lunch_overlap
        return max(0, int(worked_seconds // 60))

    @staticmethod
    async def issue_qr_card(
        db: AsyncSession,
        employee_id: int,
        creator_user_id: int,
        custom_code: Optional[str] = None
    ) -> Tuple[QRCard, str]:
        """Issue a new static physical QR card for an employee"""
        stmt = select(Employee).where(Employee.employee_id == employee_id)
        emp = (await db.execute(stmt)).scalar_one_or_none()
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        # Use custom code or generate unique secure card token
        raw_token = custom_code or f"HRG3-{emp.employee_code}-{secrets.token_hex(16).upper()}"
        t_hash = hash_token(raw_token)

        # Check if a card with this exact token_hash already exists
        stmt_existing = select(QRCard).where(QRCard.token_hash == t_hash)
        existing_card = (await db.execute(stmt_existing)).scalars().first()

        if existing_card and existing_card.employee_id != employee_id:
            raise HTTPException(status_code=409, detail="Mã QR đã thuộc về nhân viên khác")

        # Revoke any prior active QR cards for this employee
        stmt_active = select(QRCard).where(
            and_(QRCard.employee_id == employee_id, QRCard.revoked_at.is_(None))
        )
        active_cards = (await db.execute(stmt_active)).scalars().all()
        for card in active_cards:
            if not existing_card or card.qr_card_id != existing_card.qr_card_id:
                card.revoked_at = datetime.now(timezone.utc)

        if existing_card:
            existing_card.revoked_at = None
            existing_card.card_code = raw_token
            existing_card.issued_at = datetime.now(timezone.utc)
            existing_card.created_by_user_id = creator_user_id
            await db.flush()
            return existing_card, raw_token

        qr_card = QRCard(
            employee_id=employee_id,
            token_hash=t_hash,
            card_code=raw_token,
            issued_at=datetime.now(timezone.utc),
            created_by_user_id=creator_user_id
        )
        db.add(qr_card)
        await db.flush()
        return qr_card, raw_token

    @staticmethod
    async def record_scan(db: AsyncSession, scan_in: ScanRequest) -> AttendanceEvent:
        """Process Kiosk Web QR scan event and update day attendance aggregate.

        [FIX #4] SECURITY TODO — Buddy Punching Risk:
        Current QR tokens are static (permanent per employee card). This allows
        an employee to share their QR code with a colleague who can scan on their behalf.
        Recommended mitigations for a future sprint:
        - TOTP-based dynamic QR: Rotate QR codes every 30-60 seconds via authenticator app
        - Device binding: Restrict scans to whitelisted kiosk device IDs or IP ranges
        - Geo-fencing: Validate scan location is within office coordinates
        - Biometric verification: Integrate face recognition or fingerprint at kiosk
        The current idempotency key (15-minute window) provides minimal protection
        but does not prevent a different person from scanning the same QR code.
        """
        t_hash = hash_token(scan_in.qr_token)
        stmt = select(QRCard).where(
            and_(
                (QRCard.token_hash == t_hash) | (QRCard.card_code == scan_in.qr_token),
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
        day_start_utc = datetime.combine(work_date, time(0, 0), tzinfo=timezone.utc) - timedelta(hours=7)
        day_end_utc = datetime.combine(work_date, time(23, 59, 59, 999999), tzinfo=timezone.utc) - timedelta(hours=7)

        stmt = select(AttendanceEvent).where(
            and_(
                AttendanceEvent.employee_id == employee_id,
                AttendanceEvent.occurred_at >= day_start_utc,
                AttendanceEvent.occurred_at <= day_end_utc
            )
        ).order_by(AttendanceEvent.occurred_at.asc())
        events = (await db.execute(stmt)).scalars().all()

        # Collect all event timestamps for the day, ordered chronologically
        event_times = sorted([e.occurred_at for e in events])

        # If there are 2 or more distinct events in the day, the earliest event is the
        # start of work (check-in) and the latest event is the end of work (check-out).
        # This handles cases where kiosk recorded the only evening scan as CHECK_IN,
        # and a subsequent approved fix adds the morning scan as CHECK_IN too.
        if len(event_times) >= 2 and event_times[0] < event_times[-1]:
            first_in = event_times[0]
            last_out = event_times[-1]
        elif len(event_times) == 1:
            ev = events[0]
            if ev.event_type == "CHECK_IN":
                first_in = ev.occurred_at
                last_out = None
            else:
                first_in = None
                last_out = ev.occurred_at
        else:
            first_in = None
            last_out = None

        worked_mins = 0
        if first_in and last_out:
            worked_mins = AttendanceService.calculate_worked_minutes(first_in, last_out)

        # Status evaluation according to standard office hours (8h/day = 480 mins):
        # - >= 480 mins (8h full day with 1m grace period): PRESENT (1.0 work credit)
        # - >= 240 mins (4h to < 8h): HALF_DAY (0.5 work credit)
        # - < 240 mins or missing check-in/out: INCOMPLETE (0.0 work credit)
        if first_in and last_out:
            if worked_mins >= 480:
                att_status = "PRESENT"
            elif worked_mins >= 240:
                att_status = "HALF_DAY"
            else:
                att_status = "INCOMPLETE"
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
            if not first_in and not last_out and day_record.attendance_status in ("ON_LEAVE", "REMOTE", "HOLIDAY"):
                pass  # Keep pre-existing leave/remote status if no scans occurred
            else:
                day_record.attendance_status = att_status

        await db.flush()

    @staticmethod
    async def create_fix_request(
        db: AsyncSession,
        employee_id: int,
        fix_in: AttendanceFixCreate
    ) -> AttendanceFix:
        """Create a pending attendance fix/justification request"""
        local_tz = timezone(timedelta(hours=7))
        req_at = fix_in.requested_at
        if req_at.tzinfo is None:
            # Naive datetime from client form is interpreted as Vietnam local time
            req_local = req_at.replace(tzinfo=local_tz)
        else:
            req_local = req_at.astimezone(local_tz)

        # 1. Validate work_date is not in the future
        today_vn = datetime.now(timezone.utc).astimezone(local_tz).date()
        if fix_in.work_date > today_vn:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không thể tạo đơn giải trình chấm công cho ngày trong tương lai."
            )

        # 2. Validate requested_at belongs to work_date
        if req_local.date() != fix_in.work_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Thời gian giải trình ({req_local.date()}) phải thuộc ngày làm việc ({fix_in.work_date})."
            )

        # [FIX #8] Enforce monthly cap on attendance fix requests.
        # Maximum 3 approved + pending fix requests per employee per month
        # to prevent abuse of the correction mechanism.
        MAX_MONTHLY_FIXES = 3
        fix_month_start = date(fix_in.work_date.year, fix_in.work_date.month, 1)
        _, last_day_num = calendar.monthrange(fix_in.work_date.year, fix_in.work_date.month)
        fix_month_end = date(fix_in.work_date.year, fix_in.work_date.month, last_day_num)

        from sqlalchemy import func as sa_func
        stmt_count = select(sa_func.count()).select_from(AttendanceFix).where(
            and_(
                AttendanceFix.employee_id == employee_id,
                AttendanceFix.work_date >= fix_month_start,
                AttendanceFix.work_date <= fix_month_end,
                AttendanceFix.status.in_(["PENDING", "APPROVED"])
            )
        )
        monthly_fix_count = (await db.execute(stmt_count)).scalar() or 0
        if monthly_fix_count >= MAX_MONTHLY_FIXES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Monthly attendance fix limit reached ({MAX_MONTHLY_FIXES} requests per month). "
                       f"Please contact HR for further adjustments."
            )

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
            selectinload(AttendanceFix.employee).selectinload(Employee.department)
        )
        fix = (await db.execute(stmt)).scalar_one_or_none()
        if not fix:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance fix request not found")
        if fix.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request is already {fix.status}")

        # Lock the employee row so reassignment cannot race the authorization check and commit.
        employee = (await db.execute(
            select(Employee).where(Employee.employee_id == fix.employee_id).options(selectinload(Employee.department)).with_for_update()
        )).scalar_one_or_none()
        if not employee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        is_direct_manager = (
            employee.manager_employee_id == reviewer_employee_id
            or (getattr(employee, "department", None) and employee.department.manager_employee_id == reviewer_employee_id)
        )
        if fix.employee_id == reviewer_employee_id or (not is_admin and not is_direct_manager):
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
            # Generate approved adjustment event (ensure UTC timestamp)
            req_at = fix.requested_at
            if req_at.tzinfo is None:
                req_at = req_at.replace(tzinfo=timezone(timedelta(hours=7))).astimezone(timezone.utc)
            else:
                req_at = req_at.astimezone(timezone.utc)

            event = AttendanceEvent(
                employee_id=fix.employee_id,
                event_type=fix.event_type,
                source="APPROVED_FIX",
                occurred_at=req_at,
                idempotency_key=f"FIX-APPROVED-{fix.attendance_fix_id}-{secrets.token_hex(6)}",
                attendance_fix_id=fix.attendance_fix_id
            )
            db.add(event)
            await db.flush()

            # Recalculate day
            await AttendanceService.recalculate_day(db, fix.employee_id, fix.work_date)

        await db.flush()
        return fix
