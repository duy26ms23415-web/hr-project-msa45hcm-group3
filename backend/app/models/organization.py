from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import BigInteger, String, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Department(Base):
    __tablename__ = "hr_departments"

    department_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    department_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    department_name: Mapped[str] = mapped_column(String(150), nullable=False)
    manager_employee_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    employees: Mapped[List["Employee"]] = relationship(
        "Employee",
        back_populates="department",
        foreign_keys="[Employee.department_id]"
    )


class Position(Base):
    __tablename__ = "hr_positions"

    position_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    position_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    position_name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    employees: Mapped[List["Employee"]] = relationship("Employee", back_populates="position")


class Employee(Base):
    __tablename__ = "hr_employees"

    employee_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    department_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_departments.department_id"), nullable=False)
    position_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_positions.position_id"), nullable=False)
    manager_employee_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), nullable=True)
    employment_status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)  # ACTIVE, INACTIVE, TERMINATED
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    department: Mapped["Department"] = relationship("Department", back_populates="employees", foreign_keys=[department_id])
    position: Mapped["Position"] = relationship("Position", back_populates="employees")
    manager: Mapped[Optional["Employee"]] = relationship("Employee", remote_side=[employee_id], foreign_keys=[manager_employee_id])
    user_account: Mapped[Optional["UserAccount"]] = relationship("UserAccount", back_populates="employee", uselist=False)
    qr_cards: Mapped[List["QRCard"]] = relationship("QRCard", back_populates="employee", foreign_keys="[QRCard.employee_id]")
    attendance_events: Mapped[List["AttendanceEvent"]] = relationship("AttendanceEvent", back_populates="employee")
    attendance_days: Mapped[List["AttendanceDay"]] = relationship("AttendanceDay", back_populates="employee")
    attendance_fixes: Mapped[List["AttendanceFix"]] = relationship("AttendanceFix", back_populates="employee", foreign_keys="[AttendanceFix.employee_id]")
    leave_balances: Mapped[List["EmployeeLeaveBalance"]] = relationship("EmployeeLeaveBalance", back_populates="employee")
    leave_requests: Mapped[List["LeaveRequest"]] = relationship("LeaveRequest", back_populates="employee", foreign_keys="[LeaveRequest.employee_id]")
    compensations: Mapped[List["EmployeeCompensation"]] = relationship("EmployeeCompensation", back_populates="employee")
    payroll_lines: Mapped[List["PayrollLine"]] = relationship("PayrollLine", back_populates="employee")
