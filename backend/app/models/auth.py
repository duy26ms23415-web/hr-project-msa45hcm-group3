from datetime import datetime
from typing import Optional, List
from sqlalchemy import BigInteger, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Role(Base):
    __tablename__ = "hr_roles"

    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)  # ADMIN, HR, MANAGER, EMPLOYEE
    role_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    user_assignments: Mapped[List["UserRoleAssignment"]] = relationship("UserRoleAssignment", back_populates="role")


class UserAccount(Base):
    __tablename__ = "hr_user_accounts"

    user_account_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_employees.employee_id"), unique=True, nullable=False)
    login_email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="user_account")
    role_assignments: Mapped[List["UserRoleAssignment"]] = relationship("UserRoleAssignment", back_populates="user_account")


class UserRoleAssignment(Base):
    __tablename__ = "hr_user_role_assignments"

    user_role_assignment_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id"), nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_roles.role_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_account_id", "role_id", name="uq_hr_user_roles_account_role"),
    )

    # Relationships
    user_account: Mapped["UserAccount"] = relationship("UserAccount", back_populates="role_assignments")
    role: Mapped["Role"] = relationship("Role", back_populates="user_assignments")
