from datetime import date, datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_roles
from app.models.auth import UserAccount
from app.models.payroll import EmployeeCompensation, PayrollPeriod, PayrollLine
from app.schemas.payroll import (
    CompensationCreate, CompensationResponse,
    PayrollPeriodCreate, PayrollPeriodResponse, PayrollLineResponse
)
from app.services.payroll_service import PayrollService

router = APIRouter()


# Employee Compensation (Gross Salaries)
@router.post("/compensations", response_model=CompensationResponse, status_code=status.HTTP_201_CREATED)
async def create_compensation(
    comp_in: CompensationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """HR sets employee contract gross salary and allowances"""
    comp = EmployeeCompensation(
        employee_id=comp_in.employee_id,
        base_monthly_salary=comp_in.base_monthly_salary,
        fixed_allowance=comp_in.fixed_allowance,
        currency_code=comp_in.currency_code,
        effective_from=comp_in.effective_from,
        effective_to=comp_in.effective_to,
        created_by_user_id=current_user.user_account_id
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


@router.get("/employees/{employee_id}/compensations", response_model=List[CompensationResponse])
async def get_employee_compensations(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """View employee compensation history"""
    stmt = (
        select(EmployeeCompensation)
        .where(EmployeeCompensation.employee_id == employee_id)
        .order_by(EmployeeCompensation.effective_from.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# Payroll Periods
@router.post("/periods", response_model=PayrollPeriodResponse, status_code=status.HTTP_201_CREATED)
async def create_payroll_period(
    period_in: PayrollPeriodCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Initialize a payroll month period (from day 01 to end of month)"""
    start_date, end_date, _ = PayrollService.get_month_dates(period_in.period_year, period_in.period_month)
    
    stmt = select(PayrollPeriod).where(
        and_(
            PayrollPeriod.period_year == period_in.period_year,
            PayrollPeriod.period_month == period_in.period_month
        )
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payroll period already exists")

    period = PayrollPeriod(
        period_year=period_in.period_year,
        period_month=period_in.period_month,
        start_date=start_date,
        end_date=end_date,
        status="DRAFT",
        created_by_user_id=current_user.user_account_id
    )
    db.add(period)
    await db.commit()
    await db.refresh(period)
    return period


@router.get("/periods", response_model=List[PayrollPeriodResponse])
async def list_payroll_periods(
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """List all payroll periods"""
    stmt = select(PayrollPeriod).order_by(PayrollPeriod.period_year.desc(), PayrollPeriod.period_month.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/periods/{period_id}/calculate", response_model=PayrollPeriodResponse)
async def calculate_payroll(
    period_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Trigger payroll calculation for all employees in the period"""
    stmt = select(PayrollPeriod).where(PayrollPeriod.payroll_period_id == period_id)
    period = (await db.execute(stmt)).scalar_one_or_none()
    if not period:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll period not found")

    updated_period = await PayrollService.calculate_period_payroll(
        db, period.period_year, period.period_month, current_user.user_account_id
    )
    await db.commit()
    await db.refresh(updated_period)
    return updated_period


@router.get("/periods/{period_id}/lines", response_model=List[PayrollLineResponse])
async def get_payroll_lines(
    period_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """HR/ADMIN preview calculated lines to review the period before release."""
    stmt = select(PayrollLine).where(PayrollLine.payroll_period_id == period_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/periods/{period_id}/close", response_model=PayrollPeriodResponse)
async def close_payroll_period(
    period_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Close and finalize payroll period (locks all data from further edits)"""
    stmt = select(PayrollPeriod).where(PayrollPeriod.payroll_period_id == period_id)
    period = (await db.execute(stmt)).scalar_one_or_none()
    if not period:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll period not found")
    if period.status == "CLOSED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Period is already closed")

    period.status = "CLOSED"
    period.approved_by_user_id = current_user.user_account_id
    period.closed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(period)
    return period


@router.get("/periods/{period_id}/export")
async def export_payroll_spreadsheet(
    period_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Download calculated payroll report as formatted Excel (.xlsx) file"""
    excel_stream = await PayrollService.export_payroll_excel(db, period_id)
    filename = f"Bang_Luong_Thang_{period_id}.xlsx"
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# Employee Self-Service Payslip
@router.get("/me/slips", response_model=List[PayrollLineResponse])
async def get_my_payslips(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Employee views their own released payslips"""
    stmt = (
        select(PayrollLine)
        .join(PayrollPeriod)
        .where(
            and_(
                PayrollLine.employee_id == current_user.employee_id,
                PayrollPeriod.status.in_(["APPROVED", "CLOSED"])
            )
        )
        .order_by(PayrollLine.calculated_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
