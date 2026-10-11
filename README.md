# HR Management with AI Project

Tài liệu thiết kế và định hướng kiến trúc hệ thống quản lý nhân sự, chấm công QR, tính lương và Trợ lý ảo AI nội bộ của Group 3 HCM.

> 📚 **Tài liệu kỹ thuật chuyên sâu:**
> - 🏛️ **Kiến trúc phần mềm chi tiết (SAD):** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
> - 🚀 **Hướng dẫn cài đặt & vận hành (Setup Guide):** [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)

---

## 1. Mục tiêu và Quy định nghiệp vụ cốt lõi

Xây dựng ứng dụng web nội bộ hỗ trợ doanh nghiệp quản lý hồ sơ nhân sự, ghi nhận chấm công bằng thẻ QR tĩnh qua Kiosk Web, xử lý giải trình chấm công, quản lý đơn nghỉ phép theo buổi/ngày, tính lương tự động theo luật Việt Nam và tích hợp Trợ lý ảo AI hỗ trợ nhân viên tra cứu, thao tác nhanh.

Hệ thống áp dụng cho **một văn phòng/chi nhánh duy nhất**, không chia ca và không vận hành đa chi nhánh.

### 1.1 Lịch làm việc & Ngày công chuẩn
- **Giờ làm việc hành chính:** Cố định từ **08:00 đến 17:00**, từ Thứ Hai đến Thứ Sáu. Không làm việc Thứ Bảy và Chủ Nhật.
- **Thời gian nghỉ trưa:** Từ **12:00 đến 13:00** (1 tiếng, không tính vào giờ làm việc).
- **Ngày công chuẩn:** **8 tiếng / ngày** (tương đương 1.0 công).

### 1.2 Quy định chấm công QR & Xử lý quên quét thẻ
- **Thẻ QR:** Mỗi nhân viên được cấp một thẻ vật lý tĩnh mang mã token hash an toàn, không thay đổi theo thời gian.
- **Kiosk chấm công:** Chạy trực tiếp trên trình duyệt Web (online kết nối server), quét nhận diện lượt vào (`CHECK_IN`) và ra (`CHECK_OUT`).
- **Xử lý quên quẹt thẻ:** 
  - Nhân viên phát hiện thiếu lượt vào/ra cần nộp yêu cầu **Giải trình chấm công** trên hệ thống.
  - **Hạn chốt giải trình:** Giải trình phải được gửi và được Quản lý duyệt **trước ngày chốt công cuối tháng**.
  - **Mất công:** Mọi trường hợp thiếu lượt vào hoặc ra mà không được duyệt giải trình kịp trước ngày chốt tháng xem như **mất ngày công và không được tính lương**.

### 1.3 Chính sách nghỉ phép & Hạn mức phép năm
- **Hình thức nghỉ:**
  - **Nghỉ một buổi:** Buổi sáng (`MORNING`: 08:00 - 12:00, tính 0.5 ngày công) hoặc Buổi chiều (`AFTERNOON`: 13:00 - 17:00, tính 0.5 ngày công).
  - **Nghỉ cả ngày:** Cả ngày (`FULL_DAY`: 08:00 - 17:00, tính 1.0 ngày công).
- **Hạn mức phép năm (Annual Leave Quota):** Mỗi nhân viên có số ngày nghỉ hưởng nguyên lương nhất định trong năm (`total_entitled_days`).
- **Hết hạn cuối năm:** Số ngày phép chưa dùng hết trong năm sẽ **tự động hết hạn vào ngày 31/12**, không bảo lưu hay chuyển sang năm sau.
- **Nghỉ không lương:** Khi nhân viên đã sử dụng hết hạn mức ngày phép hưởng lương, các đơn xin nghỉ tiếp theo bắt buộc phải chọn loại **Nghỉ không hưởng lương (`UNPAID_LEAVE`)**.

### 1.4 Quy định ngày nghỉ lễ (Holidays)
- Danh mục ngày lễ trong năm được cấu hình trên hệ thống bởi vai trò **ADMIN** hoặc **HR**.
- **Quyền lợi:** Vào các ngày lễ, nhân viên được **tính đủ ngày công hưởng nguyên lương** mà **không cần phải chấm công**.
- **Ràng buộc:** Không cho phép chỉnh sửa hoặc xóa ngày nghỉ lễ nếu ngày đó đã trôi qua trong quá khứ (`holiday_date < CURRENT_DATE`).

### 1.5 Cơ chế phê duyệt
- **Quản lý trực tiếp (`manager_employee_id`)** của nhân viên là người duy nhất có thẩm quyền duyệt hoặc từ chối:
  1. Đơn giải trình bổ sung chấm công.
  2. Đơn xin nghỉ phép (hưởng lương và không lương).
- Quy trình phê duyệt diễn ra độc lập, **không cần thông qua HR duyệt**.

### 1.6 Kỳ tính công, Lương và Thuế
- **Kỳ tính công & lương:** Chạy từ **ngày 01 đến ngày cuối cùng của tháng**.
- **Mức lương căn bản:** Tính theo mức **lương GROSS ký trên hợp đồng lao động**, do HR thiết lập và quản lý lịch sử điều chỉnh trên hệ thống.
- **Ngày công chuẩn trong tháng:** Tổng số ngày trong tháng trừ đi các ngày Thứ Bảy, Chủ Nhật; bao gồm cả các ngày nghỉ lễ hưởng nguyên lương.
- **Trích đóng bảo hiểm bắt buộc:** Thực hiện theo luật lao động hiện hành của Việt Nam trên mức lương GROSS đóng bảo hiểm:
  - BHXH: **8%**
  - BHYT: **1.5%**
  - BHTN: **1%**
- **Thuế Thu nhập cá nhân (TNCN):** Tính sau khi giảm trừ các khoản bảo hiểm bắt buộc, áp dụng giảm trừ gia cảnh (bản thân & người phụ thuộc) và biểu thuế lũy tiến từng phần theo luật Việt Nam.
- **Xuất bảng lương:** Hỗ trợ kết xuất bảng lương chi tiết ra file **Excel/PDF** sau khi đã hoàn tất tính toán và chốt kỳ lương tháng (`CLOSED`).

---

## 2. Yêu cầu kỹ thuật

### Kiến trúc công nghệ đề xuất
- **Frontend:** React + TypeScript + Ant Design; giao diện desktop-first cho HR/Quản lý, responsive linh hoạt cho nhân viên tra cứu và tương tác.
- **Backend:** Python 3.12+, FastAPI, Pydantic v2; RESTful API chuẩn `/api/v1`.
- **Database & Migration:** PostgreSQL (lưu trữ timezone UTC, nghiệp vụ theo `Asia/Ho_Chi_Minh`), SQLAlchemy 2.x (Async ORM) và Alembic quản lý migration.
- **Trí tuệ nhân tạo (AI):** Tích hợp Gemini API / LLM với kỹ thuật **Function Calling (Tool Use)** và **RAG (Retrieval-Augmented Generation)** để tra cứu chính sách và tự động tạo đơn.
- **Kiểm thử & Triển khai:** pytest, pytest-asyncio; Docker, Docker Compose; biến môi trường `.env` tách biệt secrets.

### Nguyên tắc kỹ thuật và bảo mật
- **Tách lớp kiến trúc:** Router $\rightarrow$ Service nghiệp vụ $\rightarrow$ Repository $\rightarrow$ Database Model; tách biệt Schema Pydantic cho Request/Response.
- **Xác thực & Phân quyền (RBAC):** Token JWT, hỗ trợ 4 vai trò chính: `ADMIN`, `HR`, `MANAGER`, `EMPLOYEE`. Danh tính lấy trực tiếp từ token, ngăn chặn giả mạo `employeeId`.
- **Bảo mật thẻ QR & Chấm công:** Token thẻ QR được sinh ngẫu nhiên dạng chuỗi opaque, CSDL chỉ lưu chuỗi hash (SHA-256). Kiosk Web gửi request có kèm token xác thực thiết bị và `idempotency_key` chống quét lặp.
- **Bảo vệ toàn vẹn dữ liệu:** Nhật ký quét gốc (`hr_attendance_events`) là append-only, tuyệt đối không chỉnh sửa hay xóa. Điều chỉnh công luôn sinh ra event mới có liên kết giải trình đã duyệt.
- **Độ chính xác tài chính:** Mọi trường liên quan đến tiền tệ dùng kiểu `DECIMAL(18, 2)`, không dùng số thực dấu phẩy động.

---

## 3. Danh sách tính năng chi tiết

### 3.1 Quản lý nhân sự & Cơ cấu tổ chức
- Quản lý hồ sơ nhân viên: Thông tin cá nhân, liên hệ, ngày sinh, ngày vào làm/nghỉ việc, trạng thái (`ACTIVE`, `INACTIVE`, `TERMINATED`).
- Quản lý phòng ban và chức vụ, gán Quản lý trực tiếp (`manager_employee_id`) cho từng nhân viên.
- Quản lý tài khoản đăng nhập (`hr_user_accounts`), gán vai trò quyền hạn RBAC.

### 3.2 Cấu hình ngày lễ (Holidays)
- ADMIN/HR thêm, xem danh sách ngày nghỉ lễ hưởng nguyên lương trong năm.
- Hệ thống tự động ghi nhận ngày lễ vào ngày công hưởng lương khi tính lương tháng.
- Khóa không cho chỉnh sửa/xóa đối với ngày lễ đã diễn ra (`holiday_date < CURRENT_DATE`).

### 3.3 Chấm công QR & Giải trình ngày công
- HR phát hành, thu hồi hoặc cấp lại thẻ QR tĩnh cho nhân viên (in thẻ hoặc lưu ảnh QR bảo mật).
- Màn hình Kiosk Web đặt tại văn phòng: Nhân viên quét mã QR trước camera/máy quét để Check-in hoặc Check-out.
- Bảng công theo dõi trực quan: Tự động tổng hợp giờ vào đầu tiên, giờ ra cuối cùng, số phút làm việc và cảnh báo thiếu lượt quét.
- Nhân viên gửi đơn giải trình ngày công (chọn ngày, loại lượt bổ sung, thời gian đề xuất, lý do).
- Quản lý trực tiếp duyệt/từ chối giải trình. Duyệt trước hạn chốt tháng sẽ phục hồi ngày công tương ứng.

### 3.4 Quản lý nghỉ phép & Số dư phép năm
- Nhân viên gửi đơn nghỉ phép: Chọn loại nghỉ (Phép năm `ANNUAL`, Nghỉ không lương `UNPAID`, Nghỉ ốm `SICK`), chọn buổi (`MORNING` 4h, `AFTERNOON` 4h, hoặc `FULL_DAY` 8h).
- Quản lý trực tiếp tiếp nhận thông báo và phê duyệt đơn trực tuyến.
- Quản lý số dư phép năm (`hr_employee_leave_balances`): 
  - Hiển thị tổng ngày phép, số ngày đã nghỉ, số ngày còn lại.
  - Hết phép năm tự động yêu cầu chuyển sang nghỉ không lương.
  - Reset/hết hạn số dư phép vào cuối năm.

### 3.5 Quản lý hồ sơ lương & Bảng lương tháng
- HR cấu hình mức lương GROSS và phụ cấp cố định theo thời gian (`hr_employee_compensation`).
- Khởi tạo kỳ lương tháng (từ ngày 01 đến ngày cuối tháng):
  - Tự động quét dữ liệu chấm công thực tế, ngày lễ và ngày nghỉ phép đã duyệt.
  - Tính toán số ngày công chuẩn và ngày công hưởng lương thực tế.
  - Tự động tính khấu trừ bảo hiểm (BHXH, BHYT, BHTN) và thuế TNCN theo luật Việt Nam.
  - Cho phép HR rà soát, ghi chú điều chỉnh bổ sung và chốt kỳ lương (`CLOSED`).
- Kết xuất bảng lương tháng ra file **Excel** chuẩn cho kế toán và gửi phiếu lương cá nhân cho nhân viên.

### 3.6 Trợ lý ảo AI nội bộ (HR AI Chatbot Assistant) ⭐
Hệ thống tích hợp một chatbot AI thông minh ngay trên giao diện web (dành cho mọi nhân viên và quản lý), đảm nhận các chức năng:
1. **Hỏi đáp chính sách công ty (Policy Q&A):**
   - Trả lời tức thì các câu hỏi về quy định giờ giấc (8h-17h), thời gian nghỉ trưa, quy chế chấm công, xử lý quên quẹt thẻ.
   - Giải đáp quy định tính ngày công nghỉ lễ, điều kiện hưởng phép năm, chế độ nghỉ không lương.
   - Hướng dẫn cách tính lương GROSS, các khoản trừ BHXH/BHYT/BHTN và thuế TNCN theo luật.
2. **Tra cứu dữ liệu cá nhân theo ngữ cảnh (Contextual Data Lookup):**
   - Nhân viên hỏi: *"Tháng này tôi đã đi làm bao nhiêu công rồi?"*, *"Tôi có ngày nào quên check-out không?"* $\rightarrow$ AI tự động truy vấn bảng công cá nhân để trả lời chính xác.
   - Nhân viên hỏi: *"Tôi còn bao nhiêu ngày phép năm?"* $\rightarrow$ AI tra cứu `hr_employee_leave_balances` và phản hồi số ngày phép còn lại.
3. **Hỗ trợ tạo đơn tự động bằng ngôn ngữ tự nhiên (AI Function Calling):**
   - **Tạo đơn nghỉ phép:** Khi nhân viên chat *"Thứ Sáu tuần này tôi muốn xin nghỉ buổi sáng vì bận việc gia đình"* $\rightarrow$ AI nhận diện ngày, buổi `MORNING`, loại phép, kiểm tra số dư phép và tạo sẵn bản nháp đơn hoặc submit đơn giúp nhân viên sau khi xác nhận.
   - **Tạo giải trình chấm công:** Khi nhân viên chat *"Hôm qua ngày 02/10 tôi quên quẹt thẻ lúc về 17h, tạo giải trình giúp tôi"* $\rightarrow$ AI tự động điền form giải trình `CHECK_OUT` gửi tới Quản lý trực tiếp phê duyệt.

---

## 4. Thiết kế Cơ sở dữ liệu

### 4.1 Sơ đồ quan hệ thực thể (Entity Relationship Diagram)

```mermaid
erDiagram
    hr_departments ||--o{ hr_employees : "thuộc phòng ban"
    hr_positions ||--o{ hr_employees : "đảm nhiệm chức vụ"
    hr_employees ||--o{ hr_employees : "quản lý trực tiếp (manager_id)"
    hr_employees ||--|| hr_user_accounts : "tài khoản đăng nhập"
    
    hr_user_accounts ||--o{ hr_user_role_assignments : "gán vai trò"
    hr_roles ||--o{ hr_user_role_assignments : "định nghĩa quyền"
    
    hr_user_accounts ||--o{ hr_holidays : "cấu hình ngày lễ"
    
    hr_employees ||--o{ hr_qr_cards : "sở hữu thẻ"
    hr_employees ||--o{ hr_attendance_events : "phát sinh quét QR"
    hr_qr_cards ||--o{ hr_attendance_events : "xác thực qua thẻ"
    hr_attendance_fixes ||--o| hr_attendance_events : "sinh event điều chỉnh"
    
    hr_employees ||--o{ hr_attendance_days : "tổng hợp ngày công"
    hr_employees ||--o{ hr_attendance_fixes : "gửi giải trình"
    hr_employees ||--o{ hr_attendance_fixes : "quản lý duyệt"
    
    hr_employees ||--o{ hr_employee_leave_balances : "hạn mức phép năm"
    hr_leave_types ||--o{ hr_leave_requests : "loại nghỉ phép"
    hr_employees ||--o{ hr_leave_requests : "nộp đơn nghỉ"
    hr_employees ||--o{ hr_leave_requests : "quản lý duyệt"
    
    hr_employees ||--o{ hr_employee_compensation : "mức lương hợp đồng"
    hr_payroll_periods ||--o{ hr_payroll_lines : "chi tiết kỳ lương"
    hr_employees ||--o{ hr_payroll_lines : "nhận bảng lương"
```

---

### 4.2 Danh mục thực thể CSDL

| Nhóm | Bảng | Mục đích nghiệp vụ |
|---|---|---|
| **Tổ chức & Nhân sự** | `hr_departments` | Quản lý danh mục phòng ban |
| | `hr_positions` | Quản lý danh mục chức vụ |
| | `hr_employees` | Hồ sơ nhân viên, thông tin quản lý trực tiếp |
| **Tài khoản & Phân quyền** | `hr_user_accounts` | Tài khoản đăng nhập, mật khẩu hash Argon2/bcrypt |
| | `hr_roles` | Danh mục vai trò (`ADMIN`, `HR`, `MANAGER`, `EMPLOYEE`) |
| | `hr_user_role_assignments` | Phân bổ vai trò cho tài khoản người dùng |
| **Cấu hình ngày lễ** | `hr_holidays` | Danh mục ngày nghỉ lễ trong năm hưởng nguyên lương |
| **Chấm công QR** | `hr_qr_cards` | Thẻ QR vật lý tĩnh chứa token hash |
| | `hr_attendance_events` | Log quét công append-only và event điều chỉnh |
| | `hr_attendance_days` | Tổng hợp thời gian làm việc và trạng thái ngày công |
| | `hr_attendance_fixes` | Đơn giải trình bổ sung lượt chấm công |
| **Nghỉ phép** | `hr_leave_types` | Danh mục loại nghỉ phép (`ANNUAL`, `UNPAID`, `SICK`) |
| | `hr_employee_leave_balances`| Quản lý hạn mức, số ngày đã dùng và số dư phép năm |
| | `hr_leave_requests` | Đơn xin nghỉ phép theo buổi/cả ngày |
| **Lương & Thuế** | `hr_employee_compensation` | Lịch sử mức lương GROSS và phụ cấp cố định |
| | `hr_payroll_periods` | Danh mục các kỳ tính lương tháng |
| | `hr_payroll_lines` | Snapshot bảng tính lương chi tiết của từng nhân viên |

---

### 4.3 DBML chi tiết

```dbml
Table hr_departments {
	department_id bigint [pk, increment]
	department_code varchar(30) [not null, unique]
	department_name varchar(150) [not null]
	manager_employee_id bigint
	is_active boolean [not null, default: true]
	created_at timestamp [not null, default: `now()`]
	updated_at timestamp [not null, default: `now()`]
}

Table hr_positions {
	position_id bigint [pk, increment]
	position_code varchar(30) [not null, unique]
	position_name varchar(150) [not null]
	is_active boolean [not null, default: true]
	created_at timestamp [not null, default: `now()`]
	updated_at timestamp [not null, default: `now()`]
}

Table hr_employees {
	employee_id bigint [pk, increment]
	employee_code varchar(30) [not null, unique]
	full_name varchar(200) [not null]
	email varchar(254) [not null, unique]
	phone_number varchar(20)
	date_of_birth date
	department_id bigint [not null]
	position_id bigint [not null]
	manager_employee_id bigint [note: 'Quản lý trực tiếp phê duyệt phép và giải trình']
	employment_status varchar(20) [not null, note: 'ACTIVE, INACTIVE, TERMINATED']
	hire_date date [not null]
	termination_date date
	created_at timestamp [not null, default: `now()`]
	updated_at timestamp [not null, default: `now()`]
}

Table hr_user_accounts {
	user_account_id bigint [pk, increment]
	employee_id bigint [not null, unique]
	login_email varchar(254) [not null, unique]
	password_hash varchar(255) [not null, note: 'Hash bằng Argon2 hoặc bcrypt']
	is_active boolean [not null, default: true]
	last_login_at timestamp
	created_at timestamp [not null, default: `now()`]
}

Table hr_roles {
	role_id bigint [pk, increment]
	role_code varchar(30) [not null, unique, note: 'ADMIN, HR, MANAGER, EMPLOYEE']
	role_name varchar(100) [not null]
}

Table hr_user_role_assignments {
	user_role_assignment_id bigint [pk, increment]
	user_account_id bigint [not null]
	role_id bigint [not null]
	created_at timestamp [not null, default: `now()`]

	indexes {
		(user_account_id, role_id) [unique, name: 'uq_hr_user_roles_account_role']
	}
}

Table hr_holidays {
	holiday_id bigint [pk, increment]
	holiday_date date [not null, unique, note: 'Ngày nghỉ lễ hưởng nguyên lương']
	holiday_name varchar(150) [not null]
	is_paid boolean [not null, default: true]
	created_by_user_id bigint [not null]
	created_at timestamp [not null, default: `now()`]
}

Table hr_qr_cards {
	qr_card_id bigint [pk, increment]
	employee_id bigint [not null]
	token_hash varchar(255) [not null, unique, note: 'Hash SHA-256 của token thẻ tĩnh']
	issued_at timestamp [not null]
	expires_at timestamp
	revoked_at timestamp
	created_by_user_id bigint [not null]
}

Table hr_attendance_events {
	attendance_event_id bigint [pk, increment]
	employee_id bigint [not null]
	qr_card_id bigint
	event_type varchar(20) [not null, note: 'CHECK_IN, CHECK_OUT']
	source varchar(20) [not null, note: 'QR_SCAN, APPROVED_FIX']
	occurred_at timestamp [not null]
	device_id varchar(100) [note: 'ID xác định Kiosk Web']
	idempotency_key varchar(100) [not null, unique]
	attendance_fix_id bigint
	created_at timestamp [not null, default: `now()`]

	indexes {
		(employee_id, occurred_at) [name: 'idx_hr_att_events_employee_time']
	}
}

Table hr_attendance_days {
	attendance_day_id bigint [pk, increment]
	employee_id bigint [not null]
	work_date date [not null]
	first_check_in_at timestamp
	last_check_out_at timestamp
	worked_minutes integer [not null, default: 0]
	attendance_status varchar(20) [not null, note: 'PRESENT, INCOMPLETE, ABSENT, ON_LEAVE, HOLIDAY']
	updated_at timestamp [not null, default: `now()`]

	indexes {
		(employee_id, work_date) [unique, name: 'uq_hr_att_days_employee_date']
	}
}

Table hr_attendance_fixes {
	attendance_fix_id bigint [pk, increment]
	employee_id bigint [not null]
	work_date date [not null]
	event_type varchar(20) [not null, note: 'CHECK_IN, CHECK_OUT']
	requested_at timestamp [not null]
	reason text [not null]
	status varchar(20) [not null, note: 'PENDING, APPROVED, REJECTED']
	reviewer_employee_id bigint [note: 'Quản lý trực tiếp duyệt']
	reviewed_at timestamp
	review_note text
	created_at timestamp [not null, default: `now()`]
}

Table hr_leave_types {
	leave_type_id bigint [pk, increment]
	leave_code varchar(30) [not null, unique, note: 'ANNUAL, UNPAID, SICK']
	leave_name varchar(100) [not null]
	is_paid boolean [not null, default: true]
	is_active boolean [not null, default: true]
}

Table hr_employee_leave_balances {
	leave_balance_id bigint [pk, increment]
	employee_id bigint [not null]
	year integer [not null]
	total_entitled_days decimal(5, 2) [not null, note: 'Hạn mức ngày phép hưởng lương trong năm']
	used_days decimal(5, 2) [not null, default: 0]
	remaining_days decimal(5, 2) [not null, note: 'Tự hủy/hết hạn vào cuối năm']
	updated_at timestamp [not null, default: `now()`]

	indexes {
		(employee_id, year) [unique, name: 'uq_hr_leave_balance_emp_year']
	}
}

Table hr_leave_requests {
	leave_request_id bigint [pk, increment]
	employee_id bigint [not null]
	leave_type_id bigint [not null]
	leave_date date [not null]
	session varchar(20) [not null, note: 'MORNING (4h), AFTERNOON (4h), hoặc FULL_DAY (8h)']
	leave_days decimal(3, 1) [not null, note: '0.5 hoặc 1.0 ngày']
	reason text
	status varchar(20) [not null, note: 'PENDING, APPROVED, REJECTED, CANCELLED']
	reviewer_employee_id bigint [note: 'Quản lý trực tiếp duyệt']
	reviewed_at timestamp
	review_note text
	created_at timestamp [not null, default: `now()`]
}

Table hr_employee_compensation {
	employee_compensation_id bigint [pk, increment]
	employee_id bigint [not null]
	base_monthly_salary decimal(18, 2) [not null, note: 'Mức lương GROSS theo hợp đồng']
	fixed_allowance decimal(18, 2) [not null, default: 0]
	currency_code varchar(3) [not null, default: 'VND']
	effective_from date [not null]
	effective_to date
	created_by_user_id bigint [not null]
	created_at timestamp [not null, default: `now()`]
}

Table hr_payroll_periods {
	payroll_period_id bigint [pk, increment]
	period_year integer [not null]
	period_month integer [not null]
	start_date date [not null, note: 'Ngày 01 đầu tháng']
	end_date date [not null, note: 'Ngày cuối cùng của tháng']
	status varchar(20) [not null, note: 'DRAFT, CALCULATED, APPROVED, CLOSED']
	created_by_user_id bigint [not null]
	approved_by_user_id bigint
	closed_at timestamp
	created_at timestamp [not null, default: `now()`]

	indexes {
		(period_year, period_month) [unique, name: 'uq_hr_pay_period_year_month']
	}
}

Table hr_payroll_lines {
	payroll_line_id bigint [pk, increment]
	payroll_period_id bigint [not null]
	employee_id bigint [not null]
	base_salary decimal(18, 2) [not null, note: 'Lương GROSS hợp đồng']
	standard_work_days decimal(4, 1) [not null, note: 'Ngày công chuẩn trừ T7, CN và tính công Lễ']
	actual_work_days decimal(4, 1) [not null, note: 'Ngày công thực tế hưởng lương']
	gross_salary decimal(18, 2) [not null]
	insurance_deduction decimal(18, 2) [not null, default: 0, note: 'BHXH 8%, BHYT 1.5%, BHTN 1%']
	taxable_income decimal(18, 2) [not null, default: 0]
	personal_income_tax decimal(18, 2) [not null, default: 0, note: 'Thuế TNCN theo luật Việt Nam']
	other_deductions decimal(18, 2) [not null, default: 0]
	net_salary decimal(18, 2) [not null]
	calculation_details json [note: 'Snapshot chi tiết công thức, bảo hiểm và bậc thuế']
	calculated_at timestamp [not null]

	indexes {
		(payroll_period_id, employee_id) [unique, name: 'uq_hr_pay_lines_period_employee']
	}
}

Ref: hr_departments.manager_employee_id > hr_employees.employee_id
Ref: hr_employees.department_id > hr_departments.department_id
Ref: hr_employees.position_id > hr_positions.position_id
Ref: hr_employees.manager_employee_id > hr_employees.employee_id
Ref: hr_user_accounts.employee_id > hr_employees.employee_id
Ref: hr_user_role_assignments.user_account_id > hr_user_accounts.user_account_id
Ref: hr_user_role_assignments.role_id > hr_roles.role_id
Ref: hr_holidays.created_by_user_id > hr_user_accounts.user_account_id
Ref: hr_qr_cards.employee_id > hr_employees.employee_id
Ref: hr_qr_cards.created_by_user_id > hr_user_accounts.user_account_id
Ref: hr_attendance_events.employee_id > hr_employees.employee_id
Ref: hr_attendance_events.qr_card_id > hr_qr_cards.qr_card_id
Ref: hr_attendance_events.attendance_fix_id > hr_attendance_fixes.attendance_fix_id
Ref: hr_attendance_days.employee_id > hr_employees.employee_id
Ref: hr_attendance_fixes.employee_id > hr_employees.employee_id
Ref: hr_attendance_fixes.reviewer_employee_id > hr_employees.employee_id
Ref: hr_employee_leave_balances.employee_id > hr_employees.employee_id
Ref: hr_leave_requests.employee_id > hr_employees.employee_id
Ref: hr_leave_requests.leave_type_id > hr_leave_types.leave_type_id
Ref: hr_leave_requests.reviewer_employee_id > hr_employees.employee_id
Ref: hr_employee_compensation.employee_id > hr_employees.employee_id
Ref: hr_employee_compensation.created_by_user_id > hr_user_accounts.user_account_id
Ref: hr_payroll_periods.created_by_user_id > hr_user_accounts.user_account_id
Ref: hr_payroll_periods.approved_by_user_id > hr_user_accounts.user_account_id
Ref: hr_payroll_lines.payroll_period_id > hr_payroll_periods.payroll_period_id
Ref: hr_payroll_lines.employee_id > hr_employees.employee_id
```

---

## 5. Danh mục Màn hình và API Hệ thống

API sử dụng tiền tố `/api/v1`. Toàn bộ API yêu cầu xác thực JWT (ngoại trừ endpoint quẹt thẻ của Kiosk Web được bảo vệ bằng Kiosk Token).

| Màn hình / Tính năng | Đối tượng sử dụng | Các Endpoint API chính |
|---|---|---|
| **Đăng nhập & Hồ sơ cá nhân** | Tất cả người dùng | `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` |
| **Dashboard** | HR, Quản lý, Nhân viên | `GET /dashboard/summary`, `GET /attendance/daily-summary?date=YYYY-MM-DD` |
| **Quản lý Nhân sự** | HR, ADMIN | `GET /employees`, `POST /employees`, `GET /employees/{employeeId}`, `PATCH /employees/{employeeId}`, `POST /employees/{employeeId}/deactivate` |
| **Phòng ban & Chức vụ** | HR, ADMIN | `GET/POST /departments`, `PATCH /departments/{id}`, `GET/POST /positions`, `PATCH /positions/{id}` |
| **Cấu hình Ngày lễ** | HR, ADMIN | `GET /holidays`, `POST /holidays`, `PATCH /holidays/{id}`, `DELETE /holidays/{id}` |
| **Cấp phát Thẻ QR** | HR, ADMIN | `POST /employees/{id}/qr-cards`, `GET /employees/{id}/qr-cards`, `POST /qr-cards/{id}/revoke` |
| **Kiosk Quẹt thẻ QR** | Kiosk Web Camera | `POST /attendance/scans` (yêu cầu Kiosk-Token & idempotency-key) |
| **Bảng chấm công** | Nhân viên, Quản lý, HR | `GET /attendance/records`, `GET /attendance/records/{attendanceDayId}` |
| **Giải trình Chấm công** | Nhân viên, Quản lý trực tiếp | `POST /attendance/fixes`, `GET /attendance/fixes`, `POST /attendance/fixes/{id}/approve`, `POST /attendance/fixes/{id}/reject` |
| **Đơn xin Nghỉ phép** | Nhân viên, Quản lý trực tiếp | `POST /leave-requests`, `GET /leave-requests`, `POST /leave-requests/{id}/approve`, `POST /leave-requests/{id}/reject` |
| **Số dư Phép năm** | Nhân viên, Quản lý, HR | `GET /leave-balances/me`, `GET /employees/{id}/leave-balance` |
| **Chính sách Nghỉ phép** | HR, ADMIN | `GET /leave-types`, `POST /leave-types`, `PATCH /leave-types/{id}` |
| **Hồ sơ Lương GROSS** | HR, ADMIN | `GET /employees/{id}/compensations`, `POST /employees/{id}/compensations` |
| **Bảng lương & Xuất Excel** | HR, ADMIN; Nhân viên xem của mình | `POST /payroll-periods`, `GET /payroll-periods`, `POST /payroll-periods/{id}/calculate`, `POST /payroll-periods/{id}/close`, `GET /payroll-periods/{id}/export`, `GET /payroll/me/slips` |
| **Trợ lý ảo AI Chatbot** ⭐ | Tất cả nhân viên, Quản lý | `POST /ai/chat` (xử lý hội thoại, RAG hỏi đáp & Function Calling tự tạo đơn) |

### Các quy tắc xử lý API trọng yếu
1. **Duyệt đơn:** Chỉ tài khoản của Quản lý trực tiếp (`manager_employee_id`) được cấp quyền approve/reject đơn giải trình và nghỉ phép của cấp dưới. Tránh tình trạng người nộp tự duyệt đơn của chính mình.
2. **Kiểm tra số dư phép:** Khi nhân viên gọi `POST /leave-requests` cho loại phép hưởng lương (`ANNUAL`), hệ thống phải kiểm tra `remaining_days >= requested_days`. Nếu không đủ, chặn request và yêu cầu đổi sang `UNPAID`.
3. **Chặn sửa ngày lễ quá khứ:** API `PATCH/DELETE /holidays/{id}` bắt buộc từ chối nếu `holiday_date < CURRENT_DATE`.
4. **Hạn chốt giải trình công:** Các yêu cầu giải trình công cho tháng cũ chỉ được duyệt trước thời điểm HR chốt kỳ lương (`CLOSED`). Sau khi kỳ đã đóng, mọi giải trình chưa duyệt đều tự động coi như không hợp lệ.
5. **Function Calling của AI:** Endpoint `POST /ai/chat` khi nhận intent tạo đơn (nghỉ phép/giải trình) sẽ kích hoạt công cụ nội bộ gọi trực tiếp service tương ứng với đầy đủ bước validate, trả về kết quả kèm mã đơn để người dùng xác nhận.
