# Bản nháp tham khảo: Báo cáo nhân sự và giới hạn dữ liệu

Tài liệu mô phỏng phục vụ demo — DRAFT, chưa được công ty phê duyệt.

## 1. Trạng thái và mục đích

Mục REPORT.STATUS — trang PDF 1.

ĐÂY LÀ BẢN NHÁP MINH HỌA, CHƯA ĐƯỢC CÔNG TY PHÊ DUYỆT.

Tài liệu đề xuất cách đọc báo cáo của ứng dụng, không phải quy định lương thưởng hoặc quyết định nhân sự.

Báo cáo chỉ phản ánh dữ liệu nguồn đang được lưu tại thời điểm tạo. Không suy ra lịch sử nếu hệ thống chưa lưu snapshot lịch sử.

## 2. Danh mục báo cáo dự kiến

Mục REPORT.CATALOG — trang PDF 2.

ATTENDANCE: ngày công đã được ghi nhận trong phạm vi được phép.

LEAVE: đề nghị nghỉ, trạng thái và số dư hiện hành theo dữ liệu ứng dụng.

ATTENDANCE_FIX: các giải trình công đã ghi nhận và trạng thái xử lý.

APPROVAL_QUEUE: đề nghị đang chờ quản lý trực tiếp xử lý; HEADCOUNT: số nhân sự hiện tại theo phạm vi được cấp.

MY_PAYSLIP: phiếu lương của bản thân; PAYROLL_SUMMARY: tổng hợp lương cho HR/Admin. Chỉ xuất snapshot kỳ trọn tháng đã APPROVED hoặc CLOSED; mã tiền tệ lấy từ snapshot, tổng tách theo mã và không tính lại lương. Thiếu mã thì cần HR xác minh trước khi xuất.

Danh mục chỉ là đề xuất. Chỉ các loại xuất hiện trong giao diện và được backend cho phép mới khả dụng.

Chọn loại, kỳ và phạm vi; tạo báo cáo rồi xem preview và tải Excel theo template. Preview và file cùng một snapshot dữ liệu thật. File hết hạn sau một giờ; khi thiếu dữ liệu hoặc mất kết nối, không tạo số liệu giả.

## 3. Phạm vi truy cập

Mục REPORT.ACCESS — trang PDF 3.

Nhân viên xem dữ liệu bản thân. Quản lý xem bản thân và cấp dưới trực tiếp. HR/Admin chỉ nhận phạm vi rộng khi capability tương ứng được backend cấp.

Quyền được xác định từ JWT và dữ liệu quan hệ phía máy chủ. Bộ lọc gửi từ trình duyệt không thể mở rộng quyền.

Không tải hoặc chuyển tiếp báo cáo của người khác. Tệp xuất cần được lưu tại vị trí được công ty phê duyệt và xóa theo thời hạn lưu trữ.

## 4. Sử dụng chatbot an toàn

Mục REPORT.AI — trang PDF 4.

Chatbot gọi các nghiệp vụ có allowlist; không chạy SQL do người dùng hoặc mô hình sinh, không tự duyệt đơn và không quyết định quyền.

Khi Gemini hoặc mạng không khả dụng, chatbot chỉ dùng fallback xác định nếu có. Nếu không có handler phù hợp, ứng dụng hiển thị thông báo lỗi chuẩn và không tạo kết quả giả.

Không nhập mật khẩu, mã xác thực, dữ liệu sức khỏe không cần thiết hoặc thông tin nhân sự không thuộc phạm vi công việc.
