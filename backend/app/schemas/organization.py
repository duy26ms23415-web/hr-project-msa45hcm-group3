from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator, AliasChoices, AliasPath


# Department Schemas
class DepartmentBase(BaseModel):
    department_code: str
    department_name: str
    manager_employee_id: Optional[int] = None
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    department_name: Optional[str] = None
    manager_employee_id: Optional[int] = None
    is_active: Optional[bool] = None


class DepartmentResponse(DepartmentBase):
    model_config = ConfigDict(from_attributes=True)

    department_id: int
    created_at: datetime
    updated_at: datetime


# Position Schemas
class PositionBase(BaseModel):
    position_code: str
    position_name: str
    is_active: bool = True


class PositionCreate(PositionBase):
    pass


class PositionResponse(PositionBase):
    model_config = ConfigDict(from_attributes=True)

    position_id: int
    created_at: datetime
    updated_at: datetime


# Employee Schemas
class EmployeeBase(BaseModel):
    employee_code: str
    full_name: str
    email: EmailStr
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    department_id: int
    position_id: int
    manager_employee_id: Optional[int] = None
    employment_status: str = "ACTIVE"
    hire_date: date
    termination_date: Optional[date] = None


class EmployeeCreate(EmployeeBase):
    login_password: Optional[str] = Field(default=None, min_length=8, max_length=72, repr=False)

    @field_validator("login_password")
    @classmethod
    def validate_password_bytes(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and len(value.encode("utf-8")) > 72:
            raise ValueError("Mật khẩu không được vượt quá 72 byte UTF-8")
        return value


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(default=None, max_length=20)
    date_of_birth: Optional[date] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    manager_employee_id: Optional[int] = None
    employment_status: Optional[str] = None
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None

    new_password: Optional[str] = Field(default=None, min_length=8, max_length=72, repr=False)

    @field_validator("new_password")
    @classmethod
    def validate_password_bytes(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and len(value.encode("utf-8")) > 72:
            raise ValueError("Mật khẩu không được vượt quá 72 byte UTF-8")
        return value

    @field_validator("full_name", "email", "department_id", "position_id", "employment_status", "hire_date")
    @classmethod
    def reject_null_required_fields(cls, value):
        if value is None:
            raise ValueError("Trường này không được để trống")
        return value

    @field_validator("employment_status")
    @classmethod
    def validate_employment_status(cls, value):
        if value not in {"ACTIVE", "INACTIVE", "TERMINATED"}:
            raise ValueError("Trạng thái làm việc không hợp lệ")
        return value


class EmployeeResponse(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    employee_id: int
    has_login_account: bool = Field(
        default=False,
        validation_alias=AliasChoices("has_login_account", AliasPath("user_account", "user_account_id")),
    )

    @field_validator("has_login_account", mode="before")
    @classmethod
    def account_exists(cls, value) -> bool:
        return bool(value)

    created_at: datetime
    updated_at: datetime
    department: Optional[DepartmentResponse] = None
    position: Optional[PositionResponse] = None


class EmployeePasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=72, repr=False)

    @field_validator("new_password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Mật khẩu không được vượt quá 72 byte UTF-8")
        return value
