# Quyền prompt và công cụ AI

Quyền lấy từ role assignments của tài khoản JWT, không lấy từ prompt hay history. EMPLOYEE đơn thuần không có quyền tạo, xem, xuất, tải, chỉnh hoặc phân tích báo cáo, kể cả SELF và các report run đã tạo trước đây. Tài khoản có nhiều role dùng các capability của role được cấp; EMPLOYEE + MANAGER vẫn có quyền của MANAGER. Vai trò thiếu/không hợp lệ bị từ chối.

| Nhóm prompt mẫu | EMPLOYEE | MANAGER | HR | ADMIN | Điều kiện |
|---|---|---|---|---|---|
| Số dư phép; tra cứu công cá nhân | Có | Có | Có | Có | Có employee_id; chỉ dữ liệu bản thân |
| Soạn đơn nghỉ phép; giải trình công | Có | Có | Có | Có | Có employee_id; nháp không tự gửi/duyệt |
| Báo cáo công cá nhân; phiếu lương cá nhân | Không | Có | Có | Có | Có employee_id; SELF; lương chỉ kỳ phát hành |
| Đơn nghỉ/giải trình đang chờ tôi duyệt | Không | Có | Có | Có | Có employee_id và quan hệ quản lý trực tiếp; không tự duyệt |
| Báo cáo công/phép nhân viên trực tiếp | Không | Có | Có | Có | Có employee_id; chỉ DIRECT_REPORTS |
| Headcount | Không | Cấp dưới trực tiếp | Toàn công ty | Toàn công ty | Mặc định scope theo catalog; không suy ra lịch sử |
| Báo cáo công toàn công ty | Không | Không | Có | Có | COMPANY |
| Tổng hợp lương | Không | Không | Có | Có | COMPANY; kỳ APPROVED/CLOSED; không tính lại lương |
| Quản lý tài liệu nội quy | Không | Không | Có | Có | HR không nâng/đọc tài liệu ADMIN |
| Hỏi chính sách phép/công/quyền báo cáo | Có | Có | Có | Có | Chỉ gợi ý khi nguồn published, answerable, còn hiệu lực và đúng quyền |
| Phân tích dữ liệu, tạo biểu đồ của báo cáo | Không | Theo scope báo cáo | Theo scope báo cáo | Theo scope báo cáo | Snapshot do chính tài khoản tạo, còn hạn; kiểm lại quyền hiện tại |

Không có capability duyệt rộng cho HR/Admin: prompt hàng đợi chỉ mở đơn của cấp dưới trực tiếp. Định danh suggestion không cấp quyền. Nội dung tự do/Gemini nhận intent cũng phải qua cùng kiểm tra service.

`/reports` chặn EMPLOYEE tại router, bao gồm catalog, history, JSON/CSV/XLSX, tạo run, preview, download/file và analysis. Service bảo vệ thêm scope/generate/visible IDs và snapshot; nháp báo cáo kiểm quyền trước adapter. Không thay quyền xem công, phép hay phiếu lương trong màn hình cá nhân.

Nguồn implementation: `backend/app/services/ai_suggestions.py`, `ai_access.py`, `report_catalog.py`, `report_service.py`, `report_access.py`, `ai_report_draft_service.py` và router reports. Test hồi quy: `backend/tests/unit/test_report_permissions.py`.

Audit phân tích cần revision `0a1b2c3d4e5f` cho phép REPORT_ANALYSIS trong CHECK constraint. Chỉ thêm action ở service mà không cập nhật model/DB sẽ làm phân tích trả 503 dù tạo báo cáo vẫn thành công. Tests mock không chứng minh constraint DB đã được áp; đối chiếu model/service và kiểm tra PostgreSQL khi thêm action mới.
