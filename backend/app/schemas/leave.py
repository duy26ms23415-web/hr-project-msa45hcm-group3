from datetime import date, datetime
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


class LeaveTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    leave_type_id: int
    leave_code: str
    leave_name: str
    is_paid: bool
    is_active: bool


class LeaveBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    leave_balance_id: int
    employee_id: int
    year: int
    total_entitled_days: Decimal
    used_days: Decimal
    remaining_days: Decimal
    updated_at: datetime


class LeaveRequestCreate(BaseModel):
    leave_type_id: int
    leave_date: date
    session: str = Field(..., pattern="^(MORNING|AFTERNOON|FULL_DAY)$")
    reason: Optional[str] = None


class LeaveRequestReview(BaseModel):
    status: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    review_note: Optional[str] = None


class LeaveRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    leave_request_id: int
    employee_id: int
    leave_type_id: int
    leave_date: date
    session: str
    leave_days: Decimal
    reason: Optional[str] = None
    status: str
    reviewer_employee_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    created_at: datetime
    leave_type: Optional[LeaveTypeResponse] = None
