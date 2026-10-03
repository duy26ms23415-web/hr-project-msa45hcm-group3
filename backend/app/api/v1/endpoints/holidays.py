from datetime import date
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_roles, get_current_user
from app.models.holiday import Holiday
from app.models.auth import UserAccount
from app.schemas.holiday import HolidayCreate, HolidayUpdate, HolidayResponse

router = APIRouter()


@router.get("", response_model=List[HolidayResponse])
async def list_holidays(db: AsyncSession = Depends(get_db)):
    """List all configured public holidays"""
    result = await db.execute(select(Holiday).order_by(Holiday.holiday_date.asc()))
    return result.scalars().all()


@router.post("", response_model=HolidayResponse, status_code=status.HTTP_201_CREATED)
async def create_holiday(
    holiday_in: HolidayCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Add a new company holiday"""
    stmt = select(Holiday).where(Holiday.holiday_date == holiday_in.holiday_date)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Holiday date already exists")

    holiday = Holiday(
        holiday_date=holiday_in.holiday_date,
        holiday_name=holiday_in.holiday_name,
        is_paid=holiday_in.is_paid,
        created_by_user_id=current_user.user_account_id
    )
    db.add(holiday)
    await db.commit()
    await db.refresh(holiday)
    return holiday


@router.patch("/{holiday_id}", response_model=HolidayResponse)
async def update_holiday(
    holiday_id: int,
    holiday_update: HolidayUpdate,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Update holiday. Cannot modify if holiday date has already passed."""
    stmt = select(Holiday).where(Holiday.holiday_id == holiday_id)
    holiday = (await db.execute(stmt)).scalar_one_or_none()
    if not holiday:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")

    if holiday.holiday_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update holiday that has already passed in the past"
        )

    for field, value in holiday_update.model_dump(exclude_unset=True).items():
        setattr(holiday, field, value)

    await db.commit()
    await db.refresh(holiday)
    return holiday


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(
    holiday_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(require_roles(["HR", "ADMIN"]))
):
    """Delete holiday. Cannot delete if holiday date has already passed."""
    stmt = select(Holiday).where(Holiday.holiday_id == holiday_id)
    holiday = (await db.execute(stmt)).scalar_one_or_none()
    if not holiday:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")

    if holiday.holiday_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete holiday that has already passed in the past"
        )

    await db.delete(holiday)
    await db.commit()
    return None
