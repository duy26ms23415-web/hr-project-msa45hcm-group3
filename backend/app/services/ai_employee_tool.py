"""Read-only employee tool. Identity is supplied by authenticated chat dispatch."""
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.attendance import AttendanceDay
from app.models.leave import EmployeeLeaveBalance, LeaveType


class AIEmployeeTool:
    @staticmethod
    async def leave_preflight(db, employee_id, params, today):
        """Check authoritative balance early without guessing a leave type."""
        year = date.fromisoformat(params["leave_date"]).year if params.get("leave_date") else today.year
        balance = (await db.execute(select(EmployeeLeaveBalance).where(
            EmployeeLeaveBalance.employee_id == employee_id, EmployeeLeaveBalance.year == year))).scalar_one_or_none()
        types = (await db.execute(select(LeaveType).where(LeaveType.is_active.is_(True)))).scalars().all()
        amount = Decimal("1") if params.get("session") == "FULL_DAY" else Decimal("0.5")
        annual = next((t for t in types if t.leave_type_id == params.get("leave_type_id") and t.leave_code == "ANNUAL"), None)
        insufficient = balance is None or balance.remaining_days < amount
        blocked = insufficient and (annual is not None or "leave_type_id" not in params)
        if not blocked:
            return None
        available = [t for t in types if t.leave_code != "ANNUAL"]
        suffix = "Hãy chọn loại nghỉ phù hợp; tôi không tự đổi loại nghỉ." if available else "Vui lòng liên hệ HR để kiểm tra loại nghỉ phù hợp."
        warning = (f"Số dư phép năm {year} của bạn: {balance.remaining_days} ngày."
                   if balance else f"Chưa có dữ liệu số dư phép năm {year} của bạn.")
        return {"warning": warning + " Không đủ cho yêu cầu hiện tại. " + suffix,
                "options": [{"field": "leave_type_id", "value": t.leave_type_id, "label": t.leave_name} for t in available]}

    @staticmethod
    async def get_context(db: AsyncSession, employee_id: int, today: date, leave_year: int | None = None, attendance_start: date | None = None, attendance_end: date | None = None):
        balance = (await db.execute(select(EmployeeLeaveBalance).where(
            EmployeeLeaveBalance.employee_id == employee_id, EmployeeLeaveBalance.year == (leave_year or today.year)
        ))).scalar_one_or_none()
        records = (await db.execute(select(AttendanceDay).where(
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.work_date >= (attendance_start or today.replace(day=1)), AttendanceDay.work_date <= (attendance_end or today)
        ).order_by(AttendanceDay.work_date))).scalars().all()
        types = (await db.execute(select(LeaveType).where(LeaveType.is_active.is_(True)))).scalars().all()
        return {
            "today": today.isoformat(),
            "attendance_start": (attendance_start or today.replace(day=1)).isoformat(),
            "attendance_end": (attendance_end or today).isoformat(),
            "recorded_days": len(records),
            "absent_days": sum(r.attendance_status == "ABSENT" for r in records),
            "remaining_leave_days": str(balance.remaining_days) if balance else None,
            "present_days": sum(r.attendance_status == "PRESENT" for r in records),
            "incomplete_dates": [r.work_date.isoformat() for r in records if r.attendance_status == "INCOMPLETE"],
            "leave_types": [{"id": t.leave_type_id, "code": t.leave_code, "name": t.leave_name} for t in types],
        }
