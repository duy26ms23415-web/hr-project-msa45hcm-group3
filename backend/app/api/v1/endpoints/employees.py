from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_roles
from app.models.auth import UserAccount
from app.models.organization import Employee, Department, Position
from app.schemas.organization import EmployeeCreate, EmployeeUpdate, EmployeeResponse

router = APIRouter()


@router.get("", response_model=List[EmployeeResponse])
async def list_employees(
    department_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN", "MANAGER"]))
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
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Create a new employee profile"""
    # 1. Check duplicate code or email
    stmt_check = select(Employee).where(
        (Employee.employee_code == emp_in.employee_code) | (Employee.email == emp_in.email)
    )
    existing = (await db.execute(stmt_check)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã nhân viên hoặc email đã tồn tại trong hệ thống"
        )

    # 2. Validate department exists
    dept = (await db.execute(
        select(Department).where(Department.department_id == emp_in.department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Phòng ban với ID {emp_in.department_id} không tồn tại"
        )

    # 3. Validate position exists
    pos = (await db.execute(
        select(Position).where(Position.position_id == emp_in.position_id)
    )).scalar_one_or_none()
    if not pos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chức danh với ID {emp_in.position_id} không tồn tại"
        )

    # 4. Validate manager if provided
    if emp_in.manager_employee_id:
        mgr = (await db.execute(
            select(Employee).where(Employee.employee_id == emp_in.manager_employee_id)
        )).scalar_one_or_none()
        if not mgr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Người quản lý với ID {emp_in.manager_employee_id} không tồn tại"
            )

    emp = Employee(**emp_in.model_dump())
    db.add(emp)
    await db.commit()

    # Reload with relationships
    stmt_load = select(Employee).where(Employee.employee_id == emp.employee_id).options(
        selectinload(Employee.department),
        selectinload(Employee.position)
    )
    loaded_emp = (await db.execute(stmt_load)).scalar_one()
    return loaded_emp


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN", "MANAGER"]))
):
    """Get single employee profile by ID"""
    stmt = select(Employee).where(Employee.employee_id == employee_id).options(
        selectinload(Employee.department),
        selectinload(Employee.position)
    )
    emp = (await db.execute(stmt)).scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy nhân viên"
        )
    return emp


@router.patch("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    emp_update: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Update employee details"""
    stmt = select(Employee).where(Employee.employee_id == employee_id)
    emp = (await db.execute(stmt)).scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy nhân viên"
        )

    update_data = emp_update.model_dump(exclude_unset=True)

    # Validate foreign keys if updated
    if "department_id" in update_data and update_data["department_id"] is not None:
        dept = (await db.execute(
            select(Department).where(Department.department_id == update_data["department_id"])
        )).scalar_one_or_none()
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phòng ban không tồn tại"
            )

    if "position_id" in update_data and update_data["position_id"] is not None:
        pos = (await db.execute(
            select(Position).where(Position.position_id == update_data["position_id"])
        )).scalar_one_or_none()
        if not pos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chức danh không tồn tại"
            )

    if "manager_employee_id" in update_data and update_data["manager_employee_id"] is not None:
        if update_data["manager_employee_id"] == employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nhân viên không thể tự làm quản lý trực tiếp của chính mình"
            )
        mgr = (await db.execute(
            select(Employee).where(Employee.employee_id == update_data["manager_employee_id"])
        )).scalar_one_or_none()
        if not mgr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Người quản lý không tồn tại"
            )

    for field, value in update_data.items():
        setattr(emp, field, value)

    await db.commit()

    # Reload with relationships
    stmt_load = select(Employee).where(Employee.employee_id == employee_id).options(
        selectinload(Employee.department),
        selectinload(Employee.position)
    )
    loaded_emp = (await db.execute(stmt_load)).scalar_one()
    return loaded_emp


@router.post("/{employee_id}/deactivate", response_model=EmployeeResponse)
async def deactivate_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Deactivate employee and terminate employment"""
    stmt = select(Employee).where(Employee.employee_id == employee_id)
    emp = (await db.execute(stmt)).scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy nhân viên"
        )

    emp.employment_status = "INACTIVE"
    emp.termination_date = date.today()
    await db.commit()

    # Reload with relationships
    stmt_load = select(Employee).where(Employee.employee_id == employee_id).options(
        selectinload(Employee.department),
        selectinload(Employee.position)
    )
    loaded_emp = (await db.execute(stmt_load)).scalar_one()
    return loaded_emp
