from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import BigInteger, String, Boolean, Date, DateTime, Numeric, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base


class LeaveType(Base):
    __tablename__ = "hr_leave_types"

    leave_type_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    leave_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)  # ANNUAL, UNPAID, SICK
    leave_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    requests: Mapped[List["LeaveRequest"]] = relationship("LeaveRequest", back_populates="leave_type")


class EmployeeLeaveBalance(Base):
    __tablename__ = "hr_employee_leave_balances"

    leave_balance_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(nullable=False)
    total_entitled_days: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    used_days: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    remaining_days: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "year", name="uq_hr_leave_balance_emp_year"),
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="leave_balances")


class LeaveRequest(Base):
    __tablename__ = "hr_leave_requests"

    leave_request_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    leave_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_leave_types.leave_type_id"), nullable=False)
    leave_date: Mapped[date] = mapped_column(Date, nullable=False)
    session: Mapped[str] = mapped_column(String(20), nullable=False)  # MORNING, AFTERNOON, FULL_DAY
    leave_days: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)  # 0.5 or 1.0
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)  # PENDING, APPROVED, REJECTED, CANCELLED
    reviewer_employee_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="leave_requests", foreign_keys=[employee_id])
    reviewer: Mapped[Optional["Employee"]] = relationship("Employee", foreign_keys=[reviewer_employee_id])
    leave_type: Mapped["LeaveType"] = relationship("LeaveType", back_populates="requests")
