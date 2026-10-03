from datetime import date, datetime
from typing import Optional, Any, Dict
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


# Compensation Schemas
class CompensationCreate(BaseModel):
    employee_id: int
    base_monthly_salary: Decimal = Field(..., gt=0, description="Mức lương GROSS theo hợp đồng")
    fixed_allowance: Decimal = Decimal("0.00")
    currency_code: str = "VND"
    effective_from: date
    effective_to: Optional[date] = None


class CompensationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_compensation_id: int
    employee_id: int
    base_monthly_salary: Decimal
    fixed_allowance: Decimal
    currency_code: str
    effective_from: date
    effective_to: Optional[date] = None
    created_at: datetime


# Payroll Period Schemas
class PayrollPeriodCreate(BaseModel):
    period_year: int
    period_month: int = Field(..., ge=1, le=12)


class PayrollLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payroll_line_id: int
    payroll_period_id: int
    employee_id: int
    base_salary: Decimal
    standard_work_days: Decimal
    actual_work_days: Decimal
    allowance_amount: Decimal
    overtime_amount: Decimal
    deduction_amount: Decimal
    gross_salary: Decimal
    insurance_deduction: Decimal
    taxable_income: Decimal
    personal_income_tax: Decimal
    other_deductions: Decimal
    net_salary: Decimal
    calculation_details: Optional[Dict[str, Any]] = None
    calculated_at: datetime


class PayrollPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payroll_period_id: int
    period_year: int
    period_month: int
    start_date: date
    end_date: date
    status: str
    created_at: datetime
    closed_at: Optional[datetime] = None
