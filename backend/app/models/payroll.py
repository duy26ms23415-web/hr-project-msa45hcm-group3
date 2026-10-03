from datetime import date, datetime
from typing import Optional, Any, Dict
from decimal import Decimal
from sqlalchemy import BigInteger, String, Integer, Date, DateTime, Numeric, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base


class EmployeeCompensation(Base):
    __tablename__ = "hr_employee_compensation"

    employee_compensation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    base_monthly_salary: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)  # Lương GROSS
    fixed_allowance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="VND", nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="compensations")
    creator: Mapped["UserAccount"] = relationship("UserAccount", foreign_keys=[created_by_user_id])


class PayrollPeriod(Base):
    __tablename__ = "hr_payroll_periods"

    payroll_period_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)  # DRAFT, CALCULATED, APPROVED, CLOSED
    created_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id"), nullable=False)
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id"), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("period_year", "period_month", name="uq_hr_pay_period_year_month"),
    )

    # Relationships
    creator: Mapped["UserAccount"] = relationship("UserAccount", foreign_keys=[created_by_user_id])
    approver: Mapped[Optional["UserAccount"]] = relationship("UserAccount", foreign_keys=[approved_by_user_id])
    lines: Mapped[list["PayrollLine"]] = relationship("PayrollLine", back_populates="period", cascade="all, delete-orphan")


class PayrollLine(Base):
    __tablename__ = "hr_payroll_lines"

    payroll_line_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payroll_period_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_payroll_periods.payroll_period_id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)  # GROSS
    standard_work_days: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    actual_work_days: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    allowance_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    overtime_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    deduction_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    gross_salary: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    insurance_deduction: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    taxable_income: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    personal_income_tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    other_deductions: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    net_salary: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    calculation_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("payroll_period_id", "employee_id", name="uq_hr_pay_lines_period_employee"),
    )

    # Relationships
    period: Mapped["PayrollPeriod"] = relationship("PayrollPeriod", back_populates="lines")
    employee: Mapped["Employee"] = relationship("Employee", back_populates="payroll_lines")
