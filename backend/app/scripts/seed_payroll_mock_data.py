import asyncio
from datetime import date, datetime, time, timezone
from decimal import Decimal
from sqlalchemy import select, delete, and_

from app.core.database import AsyncSessionLocal
from app.models.organization import Employee
from app.models.leave import LeaveType, LeaveRequest
from app.models.attendance import AttendanceDay, AttendanceFix


async def seed_payroll_mock_data():
    async with AsyncSessionLocal() as session:
        print("🌱 Đang tạo dữ liệu mẫu cho kỳ lương Tháng 10/2026...")

        # 1. Lấy danh sách nhân viên
        stmt_emps = select(Employee).order_by(Employee.employee_id.asc())
        employees = (await session.execute(stmt_emps)).scalars().all()
        if not employees:
            print("❌ Chưa có nhân viên nào trong database! Vui lòng chạy seed_data trước.")
            return

        emp1 = next((e for e in employees if e.employee_code == "EMP001"), employees[0])
        emp2 = next((e for e in employees if e.employee_code == "EMP002"), employees[1] if len(employees) > 1 else emp1)
        emp3 = next((e for e in employees if e.employee_code == "EMP003"), employees[2] if len(employees) > 2 else emp1)

        # Cập nhật số người phụ thuộc để kiểm tra giảm trừ gia cảnh (Fix #7)
        emp1.dependent_count = 0  # 0 người phụ thuộc: giảm trừ bản thân 11M
        emp2.dependent_count = 2  # 2 người phụ thuộc: giảm trừ 11M + 2 * 4.4M = 19.8M
        emp3.dependent_count = 1  # 1 người phụ thuộc: giảm trừ 11M + 1 * 4.4M = 15.4M
        await session.flush()
        print("✅ Đã cập nhật số người phụ thuộc (dependent_count):")
        print(f"   - {emp1.full_name} ({emp1.employee_code}): {emp1.dependent_count} người phụ thuộc")
        print(f"   - {emp2.full_name} ({emp2.employee_code}): {emp2.dependent_count} người phụ thuộc")
        print(f"   - {emp3.full_name} ({emp3.employee_code}): {emp3.dependent_count} người phụ thuộc")

        # 2. Lấy Leave Types
        stmt_types = select(LeaveType)
        leave_types = {lt.leave_code: lt for lt in (await session.execute(stmt_types)).scalars().all()}
        annual_type = leave_types.get("ANNUAL")
        remote_type = leave_types.get("REMOTE")

        # Xóa dữ liệu attendance_days, leave_requests, attendance_fixes của tháng 10/2026 nếu đã có
        oct_start = date(2026, 10, 1)
        oct_end = date(2026, 10, 31)

        await session.execute(
            delete(AttendanceDay).where(
                and_(AttendanceDay.work_date >= oct_start, AttendanceDay.work_date <= oct_end)
            )
        )
        await session.execute(
            delete(LeaveRequest).where(
                and_(LeaveRequest.leave_date >= oct_start, LeaveRequest.leave_date <= oct_end)
            )
        )
        await session.execute(
            delete(AttendanceFix).where(
                and_(AttendanceFix.work_date >= oct_start, AttendanceFix.work_date <= oct_end)
            )
        )
        await session.flush()

        # 3. Tạo danh sách ngày làm việc Mon-Fri của Tháng 10/2026
        all_oct_weekdays = []
        for d in range(1, 32):
            cur_date = date(2026, 10, d)
            if cur_date.weekday() < 5:  # Mon=0, Fri=4
                all_oct_weekdays.append(cur_date)

        print(f"📅 Tháng 10/2026 có {len(all_oct_weekdays)} ngày công chuẩn (Thứ 2 đến Thứ 6).")

        # 4. Tạo chấm công cho Nhân viên 1 (Admin/HR - EMP001): Đi làm đầy đủ 100%
        for d in all_oct_weekdays:
            session.add(
                AttendanceDay(
                    employee_id=emp1.employee_id,
                    work_date=d,
                    first_check_in_at=datetime.combine(d, time(8, 0), tzinfo=timezone.utc),
                    last_check_out_at=datetime.combine(d, time(17, 0), tzinfo=timezone.utc),
                    worked_minutes=480,
                    attendance_status="PRESENT"
                )
            )

        # 5. Tạo chấm công cho Nhân viên 2 (Quản lý - EMP002): Đi làm đầy đủ 100%
        for d in all_oct_weekdays:
            session.add(
                AttendanceDay(
                    employee_id=emp2.employee_id,
                    work_date=d,
                    first_check_in_at=datetime.combine(d, time(8, 0), tzinfo=timezone.utc),
                    last_check_out_at=datetime.combine(d, time(17, 0), tzinfo=timezone.utc),
                    worked_minutes=480,
                    attendance_status="PRESENT"
                )
            )

        # 6. Tạo dữ liệu đặc biệt cho Nhân viên 3 (Nhân viên - EMP003):
        # - Ngày 2026-10-06: Đi làm nửa ngày (240p) VÀ có đơn nghỉ phép nửa ngày (MORNING = 0.5)
        #   -> Test Chống trục lợi công đôi: ngày này chỉ tính 1.0 công (không phải 1.5)
        # - Ngày 2026-10-07: Làm việc từ xa (REMOTE = 1.0 ngày phép)
        # - Ngày 2026-10-08: Vắng mặt (ABSENT)
        # - Ngày 2026-10-09: Vắng mặt (ABSENT)
        # - Các ngày còn lại: Đi làm đủ (PRESENT)
        for d in all_oct_weekdays:
            if d == date(2026, 10, 6):
                # Nửa ngày làm việc (PRESENT)
                session.add(
                    AttendanceDay(
                        employee_id=emp3.employee_id,
                        work_date=d,
                        first_check_in_at=datetime.combine(d, time(13, 0), tzinfo=timezone.utc),
                        last_check_out_at=datetime.combine(d, time(17, 0), tzinfo=timezone.utc),
                        worked_minutes=240,
                        attendance_status="PRESENT"
                    )
                )
            elif d == date(2026, 10, 7):
                # Làm việc từ xa (REMOTE)
                session.add(
                    AttendanceDay(
                        employee_id=emp3.employee_id,
                        work_date=d,
                        worked_minutes=480,
                        attendance_status="REMOTE"
                    )
                )
            elif d in (date(2026, 10, 8), date(2026, 10, 9)):
                # Nghỉ không phép / Vắng mặt
                session.add(
                    AttendanceDay(
                        employee_id=emp3.employee_id,
                        work_date=d,
                        worked_minutes=0,
                        attendance_status="ABSENT"
                    )
                )
            else:
                # Ngày đi làm bình thường
                session.add(
                    AttendanceDay(
                        employee_id=emp3.employee_id,
                        work_date=d,
                        first_check_in_at=datetime.combine(d, time(8, 0), tzinfo=timezone.utc),
                        last_check_out_at=datetime.combine(d, time(17, 0), tzinfo=timezone.utc),
                        worked_minutes=480,
                        attendance_status="PRESENT"
                    )
                )

        # 7. Thêm đơn nghỉ phép đã duyệt cho EMP003:
        if annual_type:
            # Nghỉ phép nửa ngày sáng 06/10
            session.add(
                LeaveRequest(
                    employee_id=emp3.employee_id,
                    leave_type_id=annual_type.leave_type_id,
                    leave_date=date(2026, 10, 6),
                    session="MORNING",
                    leave_days=Decimal("0.5"),
                    reason="Khám sức khỏe định kỳ buổi sáng",
                    status="APPROVED",
                    reviewer_employee_id=emp2.employee_id,
                    reviewed_at=datetime.now(timezone.utc),
                    review_note="Đồng ý duyệt nghỉ khám bệnh"
                )
            )

        if remote_type:
            # Đơn Remote cả ngày 07/10
            session.add(
                LeaveRequest(
                    employee_id=emp3.employee_id,
                    leave_type_id=remote_type.leave_type_id,
                    leave_date=date(2026, 10, 7),
                    session="FULL_DAY",
                    leave_days=Decimal("1.0"),
                    reason="Làm việc từ xa xử lý tài liệu kỹ thuật",
                    status="APPROVED",
                    reviewer_employee_id=emp2.employee_id,
                    reviewed_at=datetime.now(timezone.utc),
                    review_note="Duyệt làm việc Remote"
                )
            )

        # 8. Thêm 2 đơn giải trình chấm công đã có của EMP003 trong tháng 10:
        # Giúp người dùng thử nghiệm gửi đơn thứ 3 (thành công) và đơn thứ 4 (bị chặn vượt quá hạn mức 3 đơn)
        session.add(
            AttendanceFix(
                employee_id=emp3.employee_id,
                work_date=date(2026, 10, 8),
                event_type="CHECK_IN",
                requested_at=datetime.combine(date(2026, 10, 8), time(8, 5), tzinfo=timezone.utc),
                reason="Quên mang thẻ QR vào buổi sáng",
                status="PENDING"
            )
        )
        session.add(
            AttendanceFix(
                employee_id=emp3.employee_id,
                work_date=date(2026, 10, 9),
                event_type="CHECK_OUT",
                requested_at=datetime.combine(date(2026, 10, 9), time(17, 2), tzinfo=timezone.utc),
                reason="Camera Kiosk bị mất mạng lúc ra về",
                status="APPROVED",
                reviewer_employee_id=emp2.employee_id,
                reviewed_at=datetime.now(timezone.utc),
                review_note="Xác nhận camera có sự cố kỹ thuật"
            )
        )

        await session.commit()
        print("🎉 Khởi tạo dữ liệu mẫu Tháng 10/2026 thành công!")
        print("   - EMP001 (Admin): 22/22 công chuẩn, hưởng 100% lương & phụ cấp.")
        print("   - EMP002 (Manager): 22/22 công chuẩn, 2 người phụ thuộc (giảm trừ thuế TNCN vượt trội).")
        print("   - EMP003 (Employee): 20/22 công thực tế (gồm 1 ngày nửa làm nửa phép, 1 ngày WFH, 2 ngày vắng).")
        print("   - EMP003 đã có sẵn 2 đơn giải trình chấm công (sẵn sàng test giới hạn tối đa 3 đơn).")


if __name__ == "__main__":
    asyncio.run(seed_payroll_mock_data())

