from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# QR Card Schemas
class QRCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    qr_card_id: int
    employee_id: int
    token_hash: str
    card_code: Optional[str] = None
    issued_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class QRCardCreateResponse(QRCardResponse):
    raw_token: str


# Kiosk Scan Request
class ScanRequest(BaseModel):
    qr_token: str
    event_type: str = Field("CHECK_IN", pattern="^(CHECK_IN|CHECK_OUT)$")
    device_id: str
    idempotency_key: str


class KioskScanRequest(BaseModel):
    qr_code: str
    device_id: str = "KIOSK_MAIN_OFFICE"
    scan_timestamp: Optional[datetime] = None


class ScanResponse(BaseModel):
    attendance_event_id: int
    employee_id: int
    employee_name: str
    event_type: str
    occurred_at: datetime
    status: str
    message: str
    worked_minutes: Optional[int] = 0
    event_time: Optional[datetime] = None


# Attendance Day Record
class AttendanceDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attendance_day_id: int
    employee_id: int
    work_date: date
    first_check_in_at: Optional[datetime] = None
    last_check_out_at: Optional[datetime] = None
    worked_minutes: int
    attendance_status: str
    updated_at: datetime


# Attendance Fix Schemas
class AttendanceFixCreate(BaseModel):
    work_date: date
    event_type: str = Field(..., pattern="^(CHECK_IN|CHECK_OUT)$")
    requested_at: datetime
    reason: str


class AttendanceFixReview(BaseModel):
    status: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    review_note: Optional[str] = None


class AttendanceFixResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attendance_fix_id: int
    employee_id: int
    work_date: date
    event_type: str
    requested_at: datetime
    reason: str
    status: str
    reviewer_employee_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    created_at: datetime
