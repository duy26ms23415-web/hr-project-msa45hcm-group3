from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import google.generativeai as genai

from app.core.config import settings
from app.models.organization import Employee
from app.models.attendance import AttendanceDay
from app.models.leave import EmployeeLeaveBalance, LeaveType
from app.schemas.ai import AIChatRequest, AIChatResponse, AIChatAction

COMPANY_POLICY_KNOWLEDGE = """
BẠN LÀ TRỢ LÝ ẢO NHÂN SỰ (HR AI ASSISTANT) CỦA GROUP 3 HCM.
Bạn trả lời thân thiện, ngắn gọn, chuẩn xác theo quy chế nội bộ công ty:

1. GIỜ LÀM VIỆC & NGÀY CÔNG:
- Giờ làm việc hành chính: 08:00 - 17:00 từ Thứ Hai đến Thứ Sáu. Thứ Bảy và Chủ Nhật nghỉ.
- Thời gian nghỉ trưa: 12:00 - 13:00 (1 tiếng, không tính vào giờ làm).
- Ngày công chuẩn: 8 tiếng / ngày (tương đương 1.0 công). Không chia ca làm việc.
- Công ty chỉ có 1 văn phòng làm việc duy nhất.

2. CHẤM CÔNG & QUÊN QUẸT THẺ:
- Chấm công bằng Thẻ QR vật lý tĩnh qua màn hình Kiosk Web tại văn phòng.
- Nếu quên check-in hoặc check-out: Phải làm đơn Giải trình trên hệ thống.
- HẠN CHỐT: Giải trình phải được Quản lý trực tiếp duyệt TRƯỚC NGÀY CHỐT CÔNG CUỐI THÁNG.
- Quá hạn chốt mà chưa được duyệt sẽ bị MẤT NGÀY CÔNG và KHÔNG ĐƯỢC TÍNH LƯƠNG.

3. NGHỈ PHÉP:
- Đăng ký theo buổi: Sáng (MORNING: 08:00 - 12:00, 0.5 ngày công), Chiều (AFTERNOON: 13:00 - 17:00, 0.5 ngày công) hoặc Cả ngày (FULL_DAY: 8 tiếng, 1.0 công).
- Mỗi nhân viên có hạn mức ngày phép hưởng nguyên lương trong năm.
- Phép tồn cuối năm sẽ TỰ HẾT HẠN vào 31/12, KHÔNG chuyển sang năm sau.
- Khi hết ngày phép hưởng lương, bắt buộc phải chọn loại "Nghỉ không hưởng lương" (UNPAID_LEAVE).
- Quản lý trực tiếp duyệt đơn nghỉ phép, không cần HR duyệt.

4. NGÀY LỄ:
- Các ngày lễ được hưởng nguyên lương đầy đủ mà KHÔNG CẦN CHẤM CÔNG.
- Không thể sửa đổi hoặc xóa ngày lễ đã qua trong quá khứ.

5. TÍNH LƯƠNG & THUẾ:
- Lương tính theo mức GROSS trên hợp đồng lao động.
- Trích đóng bảo hiểm bắt buộc theo luật Việt Nam: BHXH 8%, BHYT 1.5%, BHTN 1% (Tổng 10.5%).
- Thuế Thu nhập cá nhân (TNCN) tính theo biểu thuế lũy tiến từng phần, sau khi giảm trừ gia cảnh bản thân (11 triệu đồng/tháng).
- Hỗ trợ xuất bảng lương ra file Excel sau khi chốt kỳ.
"""


class AIService:
    @staticmethod
    async def get_employee_context(db: AsyncSession, employee_id: int) -> Dict[str, Any]:
        """Fetch employee real-time data: leave balance and attendance for current month"""
        today = date.today()
        # 1. Leave balance
        stmt_bal = select(EmployeeLeaveBalance).where(
            and_(
                EmployeeLeaveBalance.employee_id == employee_id,
                EmployeeLeaveBalance.year == today.year
            )
        )
        bal = (await db.execute(stmt_bal)).scalar_one_or_none()
        remaining_leave = float(bal.remaining_days) if bal else 0.0

        # 2. Month attendance
        start_of_month = date(today.year, today.month, 1)
        stmt_att = select(AttendanceDay).where(
            and_(
                AttendanceDay.employee_id == employee_id,
                AttendanceDay.work_date >= start_of_month,
                AttendanceDay.work_date <= today
            )
        )
        records = (await db.execute(stmt_att)).scalars().all()
        present_days = sum(1 for r in records if r.attendance_status == "PRESENT")
        incomplete_days = [r.work_date.isoformat() for r in records if r.attendance_status == "INCOMPLETE"]

        # 3. Leave types
        stmt_types = select(LeaveType).where(LeaveType.is_active == True)
        leave_types = (await db.execute(stmt_types)).scalars().all()
        leave_type_options = [{"id": lt.leave_type_id, "code": lt.leave_code, "name": lt.leave_name} for lt in leave_types]

        return {
            "today": today.isoformat(),
            "remaining_leave_days": remaining_leave,
            "present_days_this_month": present_days,
            "incomplete_dates_this_month": incomplete_days,
            "leave_types": leave_type_options
        }

    @staticmethod
    async def process_chat(
        db: AsyncSession,
        employee_id: int,
        req: AIChatRequest
    ) -> AIChatResponse:
        """Process user message using Gemini with employee context or smart fallback"""
        ctx = await AIService.get_employee_context(db, employee_id)
        msg_lower = req.message.lower()

        # Check intent: Leave Balance lookup
        if any(kw in msg_lower for kw in ["phép", "ngày phép", "số dư phép", "nghỉ phép còn"]):
            if "xin nghỉ" not in msg_lower and "tạo đơn" not in msg_lower:
                return AIChatResponse(
                    reply=(
                        f"📊 Hiện tại bạn đang còn **{ctx['remaining_leave_days']} ngày phép hưởng lương** trong năm {date.today().year}.\n\n"
                        f"💡 Lưu ý: Số ngày phép này sẽ tự hết hạn vào ngày 31/12 và không được chuyển sang năm sau. "
                        f"Nếu hết ngày phép có lương, các đơn nghỉ tiếp theo sẽ chuyển sang chế độ **Nghỉ không lương**."
                    ),
                    action=AIChatAction(action_type="SHOW_DATA", data={"type": "LEAVE_BALANCE", "balance": ctx["remaining_leave_days"]})
                )

        # Check intent: Attendance lookup
        if any(kw in msg_lower for kw in ["ngày công", "chấm công", "bao nhiêu công", "đi làm"]):
            if "quên" not in msg_lower and "giải trình" not in msg_lower:
                inc_msg = ""
                if ctx["incomplete_dates_this_month"]:
                    inc_msg = f"\n⚠️ Bạn có các ngày bị thiếu lượt quét (cần giải trình): **{', '.join(ctx['incomplete_dates_this_month'])}**."
                return AIChatResponse(
                    reply=(
                        f"🗓️ Trong tháng {date.today().month}/{date.today().year}, bạn đã ghi nhận đủ công: **{ctx['present_days_this_month']} ngày công hợp lệ**.{inc_msg}\n\n"
                        f"💡 Bạn hãy nhớ giải trình các ngày thiếu lượt quét trước ngày chốt công cuối tháng để không bị trừ ngày công nhé!"
                    ),
                    action=AIChatAction(action_type="SHOW_DATA", data={"type": "ATTENDANCE_SUMMARY", "present_days": ctx["present_days_this_month"], "incomplete": ctx["incomplete_dates_this_month"]})
                )

        # Check intent: Draft Leave Request
        if any(kw in msg_lower for kw in ["xin nghỉ", "nghỉ sáng", "nghỉ chiều", "nghỉ cả ngày", "đơn nghỉ"]):
            # Determine session
            session = "FULL_DAY"
            if "sáng" in msg_lower:
                session = "MORNING"
            elif "chiều" in msg_lower:
                session = "AFTERNOON"

            target_date = (date.today() + timedelta(days=1)).isoformat()
            if "hôm nay" in msg_lower:
                target_date = date.today().isoformat()

            annual_type_id = next((lt["id"] for lt in ctx["leave_types"] if lt["code"] == "ANNUAL"), 1)

            return AIChatResponse(
                reply=(
                    f"✍️ Tôi đã hỗ trợ bạn tạo bản nháp **Đơn xin nghỉ phép**:\n"
                    f"- Ngày nghỉ dự kiến: **{target_date}**\n"
                    f"- Buổi nghỉ: **{'Buổi Sáng (4 tiếng)' if session == 'MORNING' else 'Buổi Chiều (4 tiếng)' if session == 'AFTERNOON' else 'Cả Ngày (8 tiếng)'}**\n"
                    f"- Loại nghỉ: **Nghỉ phép năm (hưởng lương)**\n\n"
                    f"Bạn hãy bấm xác nhận bên dưới để gửi đơn tới Quản lý trực tiếp phê duyệt!"
                ),
                action=AIChatAction(
                    action_type="DRAFT_LEAVE",
                    data={
                        "leave_date": target_date,
                        "session": session,
                        "leave_type_id": annual_type_id,
                        "reason": req.message
                    }
                )
            )

        # Check intent: Draft Attendance Fix
        if any(kw in msg_lower for kw in ["quên quẹt", "quên chấm công", "quên check-in", "quên check-out", "giải trình"]):
            event_type = "CHECK_OUT" if ("chiều" in msg_lower or "ra" in msg_lower or "17" in msg_lower) else "CHECK_IN"
            target_date = date.today().isoformat()
            if "hôm qua" in msg_lower:
                target_date = (date.today() - timedelta(days=1)).isoformat()

            return AIChatResponse(
                reply=(
                    f"📝 Tôi đã chuẩn bị bản nháp **Đơn giải trình chấm công** cho bạn:\n"
                    f"- Ngày công cần bổ sung: **{target_date}**\n"
                    f"- Lượt bổ sung: **{event_type}**\n"
                    f"- Thời gian đề xuất: **{'08:00:00' if event_type == 'CHECK_IN' else '17:00:00'}**\n\n"
                    f"Nhấn xác nhận để gửi giải trình tới Quản lý trực tiếp của bạn nhé!"
                ),
                action=AIChatAction(
                    action_type="DRAFT_FIX",
                    data={
                        "work_date": target_date,
                        "event_type": event_type,
                        "requested_at": f"{target_date}T{'08:00:00' if event_type == 'CHECK_IN' else '17:00:00'}",
                        "reason": req.message
                    }
                )
            )

        # If Gemini API Key is configured, use Gemini LLM for natural dialogue
        if settings.GEMINI_API_KEY:
            try:
                genai.configure(api_key=settings.GEMINI_API_KEY)
                model = genai.GenerativeModel(
                    model_name=settings.GEMINI_MODEL_NAME,
                    system_instruction=COMPANY_POLICY_KNOWLEDGE
                )
                prompt = f"Thông tin nhân viên đang hỏi:\n{ctx}\n\nTin nhắn người dùng: {req.message}"
                response = model.generate_content(prompt)
                return AIChatResponse(reply=response.text, action=None)
            except Exception:
                pass

        # Intelligent Fallback response based on knowledge
        return AIChatResponse(
            reply=(
                f"Chào bạn! Tôi là Trợ lý ảo AI nội bộ của Group 3 HCM. Bạn có thể hỏi tôi về:\n"
                f"- 🕒 **Giờ làm việc & Chấm công**: Giờ hành chính 8h-17h, nghỉ trưa 12h-13h, quy định quét thẻ QR Kiosk.\n"
                f"- 📊 **Tra cứu ngày công**: Kiểm tra số công trong tháng, xem ngày nào quên quét thẻ.\n"
                f"- 🌴 **Số dư phép & Nghỉ phép**: Tra cứu ngày phép năm còn lại, hỗ trợ soạn nhanh đơn xin nghỉ.\n"
                f"- 💰 **Lương & Thuế**: Cách tính lương GROSS, trích nộp bảo hiểm BHXH/BHYT/BHTN (10.5%) và thuế TNCN."
            ),
            action=None
        )
