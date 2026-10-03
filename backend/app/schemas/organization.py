from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict


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
    pass


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    manager_employee_id: Optional[int] = None
    employment_status: Optional[str] = None
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None


class EmployeeResponse(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    employee_id: int
    created_at: datetime
    updated_at: datetime
    department: Optional[DepartmentResponse] = None
    position: Optional[PositionResponse] = None
