import calendar
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import io
from typing import List, Dict, Any, Tuple
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.organization import Employee
from app.models.holiday import Holiday
from app.models.attendance import AttendanceDay
from app.models.leave import LeaveRequest
from app.models.payroll import EmployeeCompensation, PayrollPeriod, PayrollLine


class PayrollService:
    @staticmethod
    def get_month_dates(year: int, month: int) -> Tuple[date, date, List[date]]:
        """Return start_date, end_date, and list of all dates in the month"""
        _, last_day = calendar.monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)
        all_dates = [date(year, month, d) for d in range(1, last_day + 1)]
        return start_date, end_date, all_dates

    @staticmethod
    def calculate_insurance(gross_salary: Decimal) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        """
        Calculate mandatory insurance in Vietnam:
        BHXH: 8%, BHYT: 1.5%, BHTN: 1%
        Returns (bhxh, bhyt, bhtn, total_insurance)
        """
        # Statutory cap is 20 * base salary (46,800,000 VND)
        capped_salary = min(gross_salary, Decimal("46800000.00"))
        
        bhxh = (capped_salary * Decimal("0.08")).quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)
        bhyt = (capped_salary * Decimal("0.015")).quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)
        bhtn = (gross_salary * Decimal("0.01")).quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)
        total_insurance = bhxh + bhyt + bhtn
        return bhxh, bhyt, bhtn, total_insurance

    @staticmethod
    def calculate_pit_tax(gross_salary: Decimal, total_insurance: Decimal, dependent_count: int = 0) -> Tuple[Decimal, Decimal]:
        """
        Calculate Personal Income Tax (PIT) under Vietnamese Progressive Tax Law:
        Personal deduction: 11,000,000 VND. Dependent deduction: 4,400,000 VND per dependent.
        Returns (taxable_income, pit_tax)
        """
        personal_relief = Decimal("11000000.00")
        dependent_relief = Decimal("4400000.00") * dependent_count
        total_deduction = total_insurance + personal_relief + dependent_relief

        taxable_income = max(Decimal("0.00"), gross_salary - total_deduction)
        if taxable_income == Decimal("0.00"):
            return Decimal("0.00"), Decimal("0.00")

        # Progressive brackets
        ti = taxable_income
        pit = Decimal("0.00")
        if ti <= Decimal("5000000.00"):
            pit = ti * Decimal("0.05")
        elif ti <= Decimal("10000000.00"):
            pit = ti * Decimal("0.10") - Decimal("250000.00")
        elif ti <= Decimal("18000000.00"):
            pit = ti * Decimal("0.15") - Decimal("750000.00")
        elif ti <= Decimal("32000000.00"):
            pit = ti * Decimal("0.20") - Decimal("1650000.00")
        elif ti <= Decimal("52000000.00"):
            pit = ti * Decimal("0.25") - Decimal("3250000.00")
        elif ti <= Decimal("80000000.00"):
            pit = ti * Decimal("0.30") - Decimal("5850000.00")
        else:
            pit = ti * Decimal("0.35") - Decimal("9850000.00")

        return taxable_income, pit.quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)

    @staticmethod
    async def calculate_period_payroll(
        db: AsyncSession,
        period_year: int,
        period_month: int,
        user_id: int
    ) -> PayrollPeriod:
        """Calculate complete monthly payroll for all active employees"""
        start_date, end_date, all_dates = PayrollService.get_month_dates(period_year, period_month)

        # Find or create period
        stmt_period = select(PayrollPeriod).where(
            and_(
                PayrollPeriod.period_year == period_year,
                PayrollPeriod.period_month == period_month
            )
        ).options(selectinload(PayrollPeriod.lines))
        period = (await db.execute(stmt_period)).scalar_one_or_none()

        if period and period.status == "CLOSED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payroll period is already CLOSED")

        if not period:
            period = PayrollPeriod(
                period_year=period_year,
                period_month=period_month,
                start_date=start_date,
                end_date=end_date,
                status="DRAFT",
                created_by_user_id=user_id
            )
            db.add(period)
            await db.flush()

        # Query holidays in this month
        stmt_holidays = select(Holiday).where(
            and_(
                Holiday.holiday_date >= start_date,
                Holiday.holiday_date <= end_date,
                Holiday.is_paid == True
            )
        )
        holidays = (await db.execute(stmt_holidays)).scalars().all()
        holiday_dates = {h.holiday_date for h in holidays}

        # Calculate standard work days (Mon-Fri)
        standard_work_days_count = 0
        for d in all_dates:
            if d.weekday() < 5:  # Monday=0, Friday=4
                standard_work_days_count += 1
        standard_days_dec = Decimal(str(standard_work_days_count))

        # Query all active employees with active compensation
        stmt_emp = select(Employee).where(
            Employee.employment_status == "ACTIVE"
        ).options(
            selectinload(Employee.compensations),
            selectinload(Employee.department),
            selectinload(Employee.position)
        )
        employees = (await db.execute(stmt_emp)).scalars().all()

        # Explicitly delete existing lines before recalculating to respect unique constraint
        from sqlalchemy import delete
        await db.execute(delete(PayrollLine).where(PayrollLine.payroll_period_id == period.payroll_period_id))
        await db.flush()

        for emp in employees:
            # Get valid compensation profile
            active_comp = next(
                (c for c in emp.compensations if c.effective_from <= end_date and (c.effective_to is None or c.effective_to >= start_date)),
                None
            )
            if not active_comp:
                continue

            base_salary = active_comp.base_monthly_salary
            allowance = active_comp.fixed_allowance

            # Query attendance days
            stmt_att = select(AttendanceDay).where(
                and_(
                    AttendanceDay.employee_id == emp.employee_id,
                    AttendanceDay.work_date >= start_date,
                    AttendanceDay.work_date <= end_date
                )
            )
            att_days = {a.work_date: a for a in (await db.execute(stmt_att)).scalars().all()}

            # Query approved paid leaves
            stmt_leaves = select(LeaveRequest).where(
                and_(
                    LeaveRequest.employee_id == emp.employee_id,
                    LeaveRequest.leave_date >= start_date,
                    LeaveRequest.leave_date <= end_date,
                    LeaveRequest.status == "APPROVED"
                )
            ).options(selectinload(LeaveRequest.leave_type))
            approved_leaves = (await db.execute(stmt_leaves)).scalars().all()
            paid_leave_days = sum(l.leave_days for l in approved_leaves if l.leave_type.is_paid)

            # Calculate actual paid days
            actual_paid_days = Decimal("0.0")
            for d in all_dates:
                if d.weekday() >= 5:
                    continue  # Weekend
                
                # Check holiday
                if d in holiday_dates:
                    actual_paid_days += Decimal("1.0")
                    continue

                att = att_days.get(d)
                if att and att.attendance_status == "PRESENT":
                    actual_paid_days += Decimal("1.0")
                elif att and att.attendance_status == "ON_LEAVE":
                    # Leave count will be added from paid leaves sum
                    pass

            actual_paid_days += Decimal(str(paid_leave_days))
            actual_paid_days = min(actual_paid_days, standard_days_dec)

            # Pro-rated gross salary calculation
            daily_rate = base_salary / standard_days_dec if standard_days_dec > 0 else Decimal("0.00")
            earned_base = (daily_rate * actual_paid_days).quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)
            gross_salary = earned_base + allowance

            # Insurance & PIT
            bhxh, bhyt, bhtn, total_ins = PayrollService.calculate_insurance(gross_salary)
            taxable_inc, pit_tax = PayrollService.calculate_pit_tax(gross_salary, total_ins)
            net_salary = max(Decimal("0.00"), gross_salary - total_ins - pit_tax)

            calc_details = {
                "base_monthly_salary": float(base_salary),
                "fixed_allowance": float(allowance),
                "daily_rate": float(daily_rate),
                "standard_work_days": float(standard_days_dec),
                "actual_work_days": float(actual_paid_days),
                "bhxh_amount": float(bhxh),
                "bhyt_amount": float(bhyt),
                "bhtn_amount": float(bhtn),
                "total_insurance": float(total_ins),
                "taxable_income": float(taxable_inc),
                "pit_tax": float(pit_tax),
                "net_salary": float(net_salary),
            }

            line = PayrollLine(
                payroll_period_id=period.payroll_period_id,
                employee_id=emp.employee_id,
                base_salary=base_salary,
                currency_code=active_comp.currency_code,
                standard_work_days=standard_days_dec,
                actual_work_days=actual_paid_days,
                allowance_amount=allowance,
                overtime_amount=Decimal("0.00"),
                deduction_amount=Decimal("0.00"),
                gross_salary=gross_salary,
                insurance_deduction=total_ins,
                taxable_income=taxable_inc,
                personal_income_tax=pit_tax,
                other_deductions=Decimal("0.00"),
                net_salary=net_salary,
                calculation_details=calc_details,
                calculated_at=datetime.now(timezone.utc)
            )
            period.lines.append(line)

        period.status = "CALCULATED"
        await db.flush()
        return period

    @staticmethod
    async def export_payroll_excel(db: AsyncSession, period_id: int) -> io.BytesIO:
        """Generate formatted Excel report for a payroll period using openpyxl"""
        stmt = (
            select(PayrollPeriod)
            .where(PayrollPeriod.payroll_period_id == period_id)
            .options(
                selectinload(PayrollPeriod.lines).selectinload(PayrollLine.employee).selectinload(Employee.department),
                selectinload(PayrollPeriod.lines).selectinload(PayrollLine.employee).selectinload(Employee.position)
            )
        )
        period = (await db.execute(stmt)).scalar_one_or_none()
        if not period:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll period not found")
        if period.status not in {"APPROVED", "CLOSED"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll report unavailable")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Bảng Lương Tháng {period.period_month}-{period.period_year}"

        # Title formatting
        ws.merge_cells("A1:K1")
        title_cell = ws["A1"]
        title_cell.value = f"BẢNG THANH TOÁN LƯƠNG NHÂN VIÊN - THÁNG {period.period_month}/{period.period_year}"
        title_cell.font = Font(name="Arial", size=16, bold=True, color="1F4E79")
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 40

        headers = [
            "STT", "Mã NV", "Họ và Tên", "Phòng ban", "Chức vụ",
            "Lương HĐ (GROSS)", "Công Chuẩn", "Công Thực Tế",
            "Tổng Lương GROSS", "Trừ BHXH (10.5%)", "Thuế TNCN", "LƯƠNG THỰC NHẬN (NET)"
        ]

        # Header styling
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9")
        )

        ws.append(headers)
        ws.row_dimensions[2].height = 28
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=2, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        # Write data rows
        for idx, line in enumerate(period.lines, start=1):
            row = [
                idx,
                line.employee.employee_code,
                line.employee.full_name,
                line.employee.department.department_name if line.employee.department else "",
                line.employee.position.position_name if line.employee.position else "",
                float(line.base_salary),
                float(line.standard_work_days),
                float(line.actual_work_days),
                float(line.gross_salary),
                float(line.insurance_deduction),
                float(line.personal_income_tax),
                float(line.net_salary),
            ]
            ws.append(row)
            row_idx = idx + 2
            ws.row_dimensions[row_idx].height = 22
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.border = thin_border
                cell.font = Font(name="Arial", size=10)
                if col_idx in (1, 2, 7, 8):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx in (6, 9, 10, 11, 12):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = "#,##0 ₫"
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        # Auto adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output
