from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import BigInteger, String, Integer, Date, DateTime, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base


class QRCard(Base):
    __tablename__ = "hr_qr_cards"

    qr_card_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    card_code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id"), nullable=False)

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="qr_cards", foreign_keys=[employee_id])
    creator: Mapped["UserAccount"] = relationship("UserAccount", foreign_keys=[created_by_user_id])
    events: Mapped[List["AttendanceEvent"]] = relationship("AttendanceEvent", back_populates="qr_card")


class AttendanceEvent(Base):
    __tablename__ = "hr_attendance_events"

    attendance_event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    qr_card_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("hr_qr_cards.qr_card_id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # CHECK_IN, CHECK_OUT
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # QR_SCAN, APPROVED_FIX
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    attendance_fix_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("hr_attendance_fixes.attendance_fix_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_hr_att_events_employee_time", "employee_id", "occurred_at"),
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendance_events")
    qr_card: Mapped[Optional["QRCard"]] = relationship("QRCard", back_populates="events")
    attendance_fix: Mapped[Optional["AttendanceFix"]] = relationship("AttendanceFix", back_populates="events")


class AttendanceDay(Base):
    __tablename__ = "hr_attendance_days"

    attendance_day_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    first_check_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attendance_status: Mapped[str] = mapped_column(String(20), nullable=False)  # PRESENT, INCOMPLETE, ABSENT, ON_LEAVE, HOLIDAY
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_hr_att_days_employee_date"),
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendance_days")


class AttendanceFix(Base):
    __tablename__ = "hr_attendance_fixes"

    attendance_fix_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # CHECK_IN, CHECK_OUT
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)  # PENDING, APPROVED, REJECTED
    reviewer_employee_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendance_fixes", foreign_keys=[employee_id])
    reviewer: Mapped[Optional["Employee"]] = relationship("Employee", foreign_keys=[reviewer_employee_id])
    events: Mapped[List["AttendanceEvent"]] = relationship("AttendanceEvent", back_populates="attendance_fix")
