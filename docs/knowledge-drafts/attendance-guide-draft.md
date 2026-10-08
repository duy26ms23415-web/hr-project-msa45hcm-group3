# Bản nháp tham khảo: Chấm công và giải trình

Tài liệu mô phỏng phục vụ demo — DRAFT, chưa được công ty phê duyệt.

## 1. Trạng thái và phạm vi hướng dẫn

Mục ATTENDANCE.STATUS — trang PDF 1.

ĐÂY LÀ BẢN NHÁP MINH HỌA, CHƯA ĐƯỢC CÔNG TY PHÊ DUYỆT.

Tài liệu mô tả cách sử dụng hệ thống HR nội bộ cho một văn phòng. Đây không phải quy định về ca làm, xử phạt hoặc khấu trừ lương.

Giờ nghiệp vụ được hiển thị theo Asia/Ho_Chi_Minh. Nhân viên cần đối chiếu hướng dẫn đã được HR công bố và liên hệ HR khi dữ liệu có sai lệch.

## 2. Ghi nhận chấm công

Mục ATTENDANCE.RECORD — trang PDF 2.

Nhân viên quét QR tại kiosk được công ty cấu hình. Mỗi sự kiện ghi nhận được lưu trong hệ thống và không bị sửa trực tiếp.

Ứng dụng có thể tổng hợp ngày công từ các sự kiện đã ghi nhận. Ngày chưa có bản ghi không đồng nghĩa với nghỉ hoặc vắng mặt; cần kiểm tra lịch làm việc và hướng dẫn có hiệu lực.

Không chia sẻ mã QR, tài khoản hoặc ảnh chụp có thể làm lộ thông tin xác thực. Báo ngay cho bộ phận phụ trách nếu kiosk hiển thị bất thường.

## 3. Giải trình lượt công (bản nháp)

Mục ATTENDANCE.FIX — trang PDF 3.

Quy trình minh họa: chọn ngày và lượt chấm công cần giải trình, nhập giờ thực tế cùng lý do do người lao động xác nhận, sau đó gửi qua biểu mẫu hiện có.

Quản lý trực tiếp xem xét theo luồng nghiệp vụ của ứng dụng. Chatbot chỉ điền bản nháp và mở đúng màn hình; không sửa sự kiện gốc hoặc tự duyệt giải trình.

Nếu chưa biết ngày, lượt hoặc giờ thực tế, chatbot hỏi lại. Không tạo dữ liệu công giả để lấp chỗ trống.

## 4. Rà soát và bảo vệ dữ liệu

Mục ATTENDANCE.PRIVACY — trang PDF 4.

Chỉ xem dữ liệu của bản thân hoặc phạm vi cấp dưới trực tiếp được hệ thống cấp quyền. Yêu cầu HR xem xét quyền quản trị được thực hiện qua kênh nội bộ.

Bản ghi chấm công gốc có tính chất append-only; điều chỉnh cần đi theo quy trình giải trình được duyệt và lưu dấu vết.

Bản nháp này chưa thay thế quy chế lao động, nội quy hoặc hướng dẫn bảo mật chính thức của công ty.
