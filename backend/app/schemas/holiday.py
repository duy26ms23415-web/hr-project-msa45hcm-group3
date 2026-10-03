from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class HolidayBase(BaseModel):
    holiday_date: date
    holiday_name: str
    is_paid: bool = True


class HolidayCreate(HolidayBase):
    pass


class HolidayUpdate(BaseModel):
    holiday_name: Optional[str] = None
    is_paid: Optional[bool] = None


class HolidayResponse(HolidayBase):
    model_config = ConfigDict(from_attributes=True)

    holiday_id: int
    created_by_user_id: int
    created_at: datetime
