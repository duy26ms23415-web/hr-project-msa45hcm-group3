from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_roles
from app.models.organization import Department, Position
from app.schemas.organization import (
    DepartmentCreate, DepartmentUpdate, DepartmentResponse,
    PositionCreate, PositionResponse
)

router = APIRouter()


# Departments
@router.get("/departments", response_model=List[DepartmentResponse])
async def list_departments(db: AsyncSession = Depends(get_db)):
    """List all company departments"""
    result = await db.execute(select(Department).order_by(Department.department_code))
    return result.scalars().all()


@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    dept_in: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Create a new department"""
    dept = Department(**dept_in.model_dump())
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


@router.patch("/departments/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: int,
    dept_update: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Update department information or assign manager"""
    stmt = select(Department).where(Department.department_id == department_id)
    dept = (await db.execute(stmt)).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    for field, value in dept_update.model_dump(exclude_unset=True).items():
        setattr(dept, field, value)

    await db.commit()
    await db.refresh(dept)
    return dept


# Positions
@router.get("/positions", response_model=List[PositionResponse])
async def list_positions(db: AsyncSession = Depends(get_db)):
    """List all company job positions"""
    result = await db.execute(select(Position).order_by(Position.position_code))
    return result.scalars().all()


@router.post("/positions", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
async def create_position(
    pos_in: PositionCreate,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Create a new job position"""
    pos = Position(**pos_in.model_dump())
    db.add(pos)
    await db.commit()
    await db.refresh(pos)
    return pos
