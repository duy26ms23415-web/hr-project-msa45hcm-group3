from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_roles, verify_kiosk_secret
from app.models.auth import UserAccount
from app.models.attendance import AttendanceDay, AttendanceFix, QRCard
from app.schemas.attendance import (
    QRCardCreateResponse, QRCardResponse,
    ScanRequest, ScanResponse,
    AttendanceDayResponse,
    AttendanceFixCreate, AttendanceFixReview, AttendanceFixResponse
)
from app.services.attendance_service import AttendanceService

router = APIRouter()


# QR Card Management
@router.post("/employees/{employee_id}/qr-cards", response_model=QRCardCreateResponse, status_code=status.HTTP_201_CREATED)
async def issue_qr_card(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Issue a new static physical QR card for employee"""
    qr_card, raw_token = await AttendanceService.issue_qr_card(db, employee_id, current_user.user_account_id)
    await db.commit()
    await db.refresh(qr_card)
    return QRCardCreateResponse(
        qr_card_id=qr_card.qr_card_id,
        employee_id=qr_card.employee_id,
        token_hash=qr_card.token_hash,
        issued_at=qr_card.issued_at,
        expires_at=qr_card.expires_at,
        revoked_at=qr_card.revoked_at,
        raw_token=raw_token
    )


@router.get("/employees/{employee_id}/qr-cards", response_model=List[QRCardResponse])
async def get_employee_qr_cards(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """List issued QR cards for employee"""
    stmt = select(QRCard).where(QRCard.employee_id == employee_id).order_by(QRCard.issued_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/qr-cards/{qr_card_id}/revoke", response_model=QRCardResponse)
async def revoke_qr_card(
    qr_card_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Revoke a QR card"""
    stmt = select(QRCard).where(QRCard.qr_card_id == qr_card_id)
    card = (await db.execute(stmt)).scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QR card not found")
    card.revoked_at = card.issued_at
    await db.commit()
    await db.refresh(card)
    return card


# Kiosk Scan Endpoint (Web Camera / Scanner)
@router.post("/scans", response_model=ScanResponse)
async def process_kiosk_scan(
    scan_in: ScanRequest,
    db: AsyncSession = Depends(get_db),
    _ = Depends(verify_kiosk_secret)
):
    """Kiosk Web scans QR code to record CHECK_IN or CHECK_OUT"""
    event = await AttendanceService.record_scan(db, scan_in)
    await db.commit()
    await db.refresh(event)
    return ScanResponse(
        attendance_event_id=event.attendance_event_id,
        employee_id=event.employee_id,
        employee_name="",
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        status="SUCCESS",
        message=f"Quét ghi nhận {event.event_type} thành công!"
    )


# Attendance Records
@router.get("/records", response_model=List[AttendanceDayResponse])
async def list_attendance_records(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    employee_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Get daily attendance records (filtered by date range and employee)"""
    user_roles = [ra.role.role_code for ra in current_user.role_assignments]
    
    # If regular employee, only allowed to see their own records
    target_emp_id = employee_id
    if "ADMIN" not in user_roles and "HR" not in user_roles and "MANAGER" not in user_roles:
        target_emp_id = current_user.employee_id
    elif not target_emp_id:
        target_emp_id = current_user.employee_id

    stmt = select(AttendanceDay).where(AttendanceDay.employee_id == target_emp_id)
    if from_date:
        stmt = stmt.where(AttendanceDay.work_date >= from_date)
    if to_date:
        stmt = stmt.where(AttendanceDay.work_date <= to_date)
    
    stmt = stmt.order_by(AttendanceDay.work_date.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


# Attendance Fixes (Giải trình chấm công)
@router.post("/fixes", response_model=AttendanceFixResponse, status_code=status.HTTP_201_CREATED)
async def create_attendance_fix(
    fix_in: AttendanceFixCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Employee submits a fix request for missing check-in or check-out"""
    fix = await AttendanceService.create_fix_request(db, current_user.employee_id, fix_in)
    await db.commit()
    await db.refresh(fix)
    return fix


@router.get("/fixes", response_model=List[AttendanceFixResponse])
async def list_attendance_fixes(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """List attendance fixes (Employee sees own, Manager sees subordinate's)"""
    user_roles = [ra.role.role_code for ra in current_user.role_assignments]
    stmt = select(AttendanceFix).order_by(AttendanceFix.created_at.desc())

    if "ADMIN" in user_roles or "HR" in user_roles:
        pass  # sees all
    elif "MANAGER" in user_roles:
        # Sees own or direct subordinates
        stmt = stmt.where(
            (AttendanceFix.employee_id == current_user.employee_id) |
            (AttendanceFix.reviewer_employee_id == current_user.employee_id)
        )
    else:
        stmt = stmt.where(AttendanceFix.employee_id == current_user.employee_id)

    if status_filter:
        stmt = stmt.where(AttendanceFix.status == status_filter)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/fixes/{fix_id}/approve", response_model=AttendanceFixResponse)
async def approve_attendance_fix(
    fix_id: int,
    review_in: AttendanceFixReview,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Direct Manager approves attendance fix and recalculates day"""
    user_roles = [ra.role.role_code for ra in current_user.role_assignments]
    is_admin = "ADMIN" in user_roles

    review_in.status = "APPROVED"
    fix = await AttendanceService.review_fix_request(
        db, fix_id, current_user.employee_id, review_in, is_admin=is_admin
    )
    await db.commit()
    await db.refresh(fix)
    return fix


@router.post("/fixes/{fix_id}/reject", response_model=AttendanceFixResponse)
async def reject_attendance_fix(
    fix_id: int,
    review_in: AttendanceFixReview,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Direct Manager rejects attendance fix"""
    user_roles = [ra.role.role_code for ra in current_user.role_assignments]
    is_admin = "ADMIN" in user_roles

    review_in.status = "REJECTED"
    fix = await AttendanceService.review_fix_request(
        db, fix_id, current_user.employee_id, review_in, is_admin=is_admin
    )
    await db.commit()
    await db.refresh(fix)
    return fix
