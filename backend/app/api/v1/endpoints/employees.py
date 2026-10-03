from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_roles
from app.models.organization import Employee
from app.schemas.organization import EmployeeCreate, EmployeeUpdate, EmployeeResponse

router = APIRouter()


@router.get("", response_model=List[EmployeeResponse])
async def list_employees(
    department_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN", "MANAGER"]))
):
    """List employees with optional department and status filtering"""
    stmt = select(Employee).options(
        selectinload(Employee.department),
        selectinload(Employee.position)
    )
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if status_filter:
        stmt = stmt.where(Employee.employment_status == status_filter)
    
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    emp_in: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Create a new employee profile"""
    stmt_check = select(Employee).where(
        (Employee.employee_code == emp_in.employee_code) | (Employee.email == emp_in.email)
    )
    existing = (await db.execute(stmt_check)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee code or email already exists")

    emp = Employee(**emp_in.model_dump())
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    return emp


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN", "MANAGER"]))
):
    """Get single employee profile by ID"""
    stmt = select(Employee).where(Employee.employee_id == employee_id).options(
        selectinload(Employee.department),
        selectinload(Employee.position)
    )
    emp = (await db.execute(stmt)).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return emp


@router.patch("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    emp_update: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Update employee details"""
    stmt = select(Employee).where(Employee.employee_id == employee_id)
    emp = (await db.execute(stmt)).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    update_data = emp_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(emp, field, value)

    await db.commit()
    await db.refresh(emp)
    return emp


@router.post("/{employee_id}/deactivate", response_model=EmployeeResponse)
async def deactivate_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Deactivate employee and terminate employment"""
    stmt = select(Employee).where(Employee.employee_id == employee_id)
    emp = (await db.execute(stmt)).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    emp.employment_status = "INACTIVE"
    await db.commit()
    await db.refresh(emp)
    return emp
