from datetime import date
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_roles
from app.models.auth import UserAccount
from app.models.leave import LeaveType, LeaveRequest, EmployeeLeaveBalance
from app.models.organization import Employee
from app.schemas.leave import (
    LeaveTypeResponse, LeaveBalanceResponse,
    LeaveRequestCreate, LeaveRequestReview, LeaveRequestResponse
)
from app.services.leave_service import LeaveService
from app.services.ai_access import require_known_role, require_reviewer_role

router = APIRouter()


# Leave Types
@router.get("/types", response_model=List[LeaveTypeResponse])
async def list_leave_types(db: AsyncSession = Depends(get_db)):
    """List all active leave types"""
    result = await db.execute(select(LeaveType).where(LeaveType.is_active == True))
    return result.scalars().all()


# Leave Balances
@router.get("/balances/me", response_model=LeaveBalanceResponse)
async def get_my_leave_balance(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Get current user's annual leave balance for a given year"""
    target_year = year or date.today().year
    balance = await LeaveService.get_or_create_balance(db, current_user.employee_id, target_year)
    return balance


@router.get("/balances/employees/{employee_id}", response_model=LeaveBalanceResponse)
async def get_employee_leave_balance(
    employee_id: int,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN", "MANAGER"]))
):
    """HR or Manager views employee's leave balance"""
    target_year = year or date.today().year
    balance = await LeaveService.get_or_create_balance(db, employee_id, target_year)
    return balance


# Leave Requests
@router.post("/requests", response_model=LeaveRequestResponse, status_code=status.HTTP_201_CREATED)
async def submit_leave_request(
    req_in: LeaveRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Employee submits a leave request (MORNING, AFTERNOON, or FULL_DAY)"""
    leave_req = await LeaveService.create_leave_request(db, current_user.employee_id, req_in)
    await db.commit()
    
    # Reload with relations for response serialization
    stmt = (
        select(LeaveRequest)
        .where(LeaveRequest.leave_request_id == leave_req.leave_request_id)
        .options(selectinload(LeaveRequest.leave_type))
    )
    reloaded = (await db.execute(stmt)).scalar_one()
    return reloaded


@router.get("/requests", response_model=List[LeaveRequestResponse])
async def list_leave_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    view: Literal["mine", "approvals", "visible"] = "mine",
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """List leave requests (Employee views own, Manager views subordinate's)"""
    user_roles = [ra.role.role_code for ra in current_user.role_assignments]
    role_set = set(user_roles)
    require_known_role(role_set)
    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.employee)
        )
        .order_by(LeaveRequest.created_at.desc())
    )

    if view == "mine":
        stmt = stmt.where(LeaveRequest.employee_id == current_user.employee_id)
    elif view == "approvals":
        require_reviewer_role(role_set)
        if status_filter not in (None, "PENDING"):
            raise HTTPException(status_code=422, detail="Approvals view only lists pending requests")
        stmt = stmt.join(Employee, Employee.employee_id == LeaveRequest.employee_id).where(
            Employee.manager_employee_id == current_user.employee_id,
            LeaveRequest.status == "PENDING",
        )
    else:
        if not set(user_roles) & {"ADMIN", "HR", "MANAGER"}:
            raise HTTPException(status_code=403, detail="AI_ACCESS_DENIED")
        if not set(user_roles) & {"ADMIN", "HR"}:
            stmt = stmt.join(Employee, Employee.employee_id == LeaveRequest.employee_id).where(
                Employee.manager_employee_id == current_user.employee_id
            )

    if status_filter:
        stmt = stmt.where(LeaveRequest.status == status_filter)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/requests/{request_id}/approve", response_model=LeaveRequestResponse)
async def approve_leave_request(
    request_id: int,
    review_in: LeaveRequestReview,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Direct Manager approves leave request"""
    require_reviewer_role({ra.role.role_code for ra in current_user.role_assignments})
    review_in.status = "APPROVED"
    req = await LeaveService.review_leave_request(
        db, request_id, current_user.employee_id, review_in
    )
    await db.commit()
    
    stmt = select(LeaveRequest).where(LeaveRequest.leave_request_id == req.leave_request_id).options(selectinload(LeaveRequest.leave_type))
    return (await db.execute(stmt)).scalar_one()


@router.post("/requests/{request_id}/reject", response_model=LeaveRequestResponse)
async def reject_leave_request(
    request_id: int,
    review_in: LeaveRequestReview,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Direct Manager rejects leave request"""
    require_reviewer_role({ra.role.role_code for ra in current_user.role_assignments})
    review_in.status = "REJECTED"
    req = await LeaveService.review_leave_request(
        db, request_id, current_user.employee_id, review_in
    )
    await db.commit()
    
    stmt = select(LeaveRequest).where(LeaveRequest.leave_request_id == req.leave_request_id).options(selectinload(LeaveRequest.leave_type))
    return (await db.execute(stmt)).scalar_one()
