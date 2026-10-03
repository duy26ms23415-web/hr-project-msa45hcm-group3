# HR Management with AI Project

Tài liệu định hướng ban đầu cho hệ thống quản lý nhân sự, chấm công và tính lương của Group 3 HCM.

## 1. Mục tiêu và giả định

Xây dựng ứng dụng web nội bộ để quản lý hồ sơ nhân viên, ghi nhận chấm công bằng QR, xử lý giải trình chấm công thiếu, quản lý đơn nghỉ phép theo buổi và lập bảng lương theo kỳ.

Các giả định cần được xác nhận trước khi triển khai:

- Backend dùng Python/FastAPI; giao diện web dùng React và Ant Design. Ant Design là thư viện giao diện phía frontend, không phải thư viện Python.
- CSDL quan hệ PostgreSQL; thời gian lưu theo UTC, ngày công và kỳ lương áp dụng múi giờ `Asia/Ho_Chi_Minh`.
- Phiên bản đầu chỉ cho đăng ký nghỉ đúng một buổi (sáng hoặc chiều), không cho nghỉ nguyên ngày. Việc có hỗ trợ nghỉ nửa buổi làm việc hay không cần PO xác nhận.
- Công thức thuế, bảo hiểm, phụ cấp, khấu trừ, quy định làm thêm và số ngày phép chưa được cung cấp; các mục này phải cấu hình hoặc chốt nghiệp vụ trước khi phát hành bảng lương thực tế.

## 2. Yêu cầu kỹ thuật

### Kiến trúc đề xuất

- **Frontend:** React + TypeScript + Ant Design; giao diện desktop-first cho HR/quản lý, responsive cho nhân viên tra cứu và gửi yêu cầu.
- **Backend:** Python 3.12+, FastAPI, Pydantic; REST API có version `/api/v1`.
- **Persistence:** PostgreSQL; SQLAlchemy 2.x và Alembic cho ORM/migration.
- **Kiểm thử:** pytest, pytest-asyncio; kiểm thử API, phân quyền, tính công/lương và các trạng thái duyệt.
- **Triển khai:** cấu hình qua environment variables, Docker; secrets không lưu trong source. Có môi trường local, staging và production.

### Nguyên tắc kỹ thuật và bảo mật

- Tách router, service nghiệp vụ, repository và schema/request-response; không đặt quy tắc duyệt hoặc tính lương trực tiếp trong endpoint.
- Xác thực tài khoản; phân quyền tối thiểu theo vai trò `ADMIN`, `HR`, `MANAGER`, `EMPLOYEE`. API lấy danh tính từ phiên/token, không tin `employeeId` do client tự khai báo để vượt quyền.
- Mật khẩu chỉ lưu dạng hash. QR chứa token ngẫu nhiên/opaque, CSDL chỉ lưu hash; có thể thu hồi và cấp lại thẻ. Endpoint quét QR chỉ nhận request từ thiết bị/kiosk đã xác thực.
- Nhật ký quét gốc là append-only; chỉnh sửa công đi qua yêu cầu giải trình và lưu người duyệt, thời điểm, lý do. Chặn gửi lặp bằng idempotency key.
- Dữ liệu lương và thông tin cá nhân giới hạn theo quyền; ghi audit log cho thay đổi hồ sơ, duyệt công/phép và chốt lương.
- Danh sách API phải phân trang; bộ lọc ngày dùng ngày ISO `YYYY-MM-DD`, timestamp có timezone. API tiền tệ dùng decimal, không dùng số thực dấu phẩy động.
- Có backup/restore CSDL, log lỗi có correlation ID và không ghi token QR, mật khẩu hay dữ liệu lương nhạy cảm vào log thông thường.

## 3. Danh sách tính năng

### 3.1 Quản lý nhân sự

- Tạo, xem, cập nhật và ngừng hoạt động hồ sơ nhân viên; tìm kiếm theo mã, tên, phòng ban, chức vụ và trạng thái.
- Quản lý phòng ban, chức vụ, quản lý trực tiếp, thông tin liên hệ và ngày vào/nghỉ việc.
- Liên kết tài khoản đăng nhập với nhân viên; quản lý vai trò và trạng thái tài khoản.

### 3.2 Chấm công QR và giải trình

- HR cấp, thu hồi hoặc cấp lại QR cho nhân viên; QR không hiển thị thông tin cá nhân.
- Kiosk/thiết bị đã xác thực quét QR để ghi nhận vào/ra, thời điểm, thiết bị và kết quả xử lý.
- Hiển thị lịch sử chấm công theo ngày/tháng; phát hiện thiếu lượt vào/ra hoặc lượt trùng.
- Nhân viên gửi giải trình ngày công, loại lượt cần bổ sung (vào/ra), thời gian đề xuất và lý do.
- Quản lý/HR duyệt hoặc từ chối; khi duyệt, hệ thống tạo sự kiện điều chỉnh có liên kết yêu cầu, không sửa mất log quét gốc.

### 3.3 Nghỉ phép

- Nhân viên tạo đơn cho một ngày và một buổi cụ thể (`MORNING` hoặc `AFTERNOON`); không nhận đơn cả ngày trong phạm vi phiên bản đầu.
- Quản lý/HR duyệt hoặc từ chối và ghi chú phản hồi.
- Nhân viên và người duyệt xem lịch sử/trạng thái đơn. Số dư phép chỉ được hiển thị/tính khi chính sách phép đã được xác nhận.

### 3.4 Tính lương

- HR cấu hình mức lương cơ bản và phụ cấp có hiệu lực theo thời gian.
- Tạo kỳ lương tháng, tổng hợp dữ liệu công/phép đã duyệt và lập dòng lương cho từng nhân viên.
- Cho phép kiểm tra, điều chỉnh khoản cộng/trừ có lý do, gửi duyệt và chốt kỳ lương.
- Lưu snapshot các khoản và kết quả tính để bảng lương đã chốt không thay đổi khi hồ sơ lương/công về sau được cập nhật.
- Công thức thuế, bảo hiểm, làm thêm và khấu trừ phải theo chính sách được phê duyệt; không mặc định đây là tư vấn hay cấu hình pháp lý.

## 4. Màn hình và API

API dùng tiền tố `/api/v1`. Tất cả API yêu cầu đăng nhập, ngoại trừ endpoint quét QR được bảo vệ bằng thông tin xác thực riêng của kiosk. Endpoint danh sách nhận `page` và `limit`, trả `items` cùng thông tin phân trang. Các route bên dưới là hợp đồng định hướng, cần chuẩn hóa schema/error code trong OpenAPI trước khi code.

| Màn hình | Người dùng | API chính |
|---|---|---|
| Đăng nhập / thông tin tài khoản | Tất cả | `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` |
| Dashboard | HR, quản lý | `GET /dashboard/summary`, `GET /attendance/daily-summary?date=YYYY-MM-DD` |
| Danh sách và chi tiết nhân viên | HR, ADMIN | `GET /employees`, `POST /employees`, `GET /employees/{employeeId}`, `PATCH /employees/{employeeId}`, `POST /employees/{employeeId}/deactivate` |
| Phòng ban và chức vụ | HR, ADMIN | `GET/POST /departments`, `PATCH /departments/{departmentId}`, `GET/POST /positions`, `PATCH /positions/{positionId}` |
| QR nhân viên | HR, ADMIN | `POST /employees/{employeeId}/qr-cards`, `GET /employees/{employeeId}/qr-cards`, `POST /qr-cards/{qrCardId}/revoke` |
| Kiosk quét công | Kiosk | `POST /attendance/scans` |
| Bảng công cá nhân / toàn công ty | Nhân viên, quản lý, HR | `GET /attendance/records?fromDate=...&toDate=...&employeeId=...`, `GET /attendance/records/{attendanceDayId}` |
| Giải trình chấm công | Nhân viên, quản lý, HR | `POST /attendance/fixes`, `GET /attendance/fixes`, `GET /attendance/fixes/{fixId}`, `POST /attendance/fixes/{fixId}/approve`, `POST /attendance/fixes/{fixId}/reject` |
| Đơn nghỉ phép | Nhân viên, quản lý, HR | `POST /leave-requests`, `GET /leave-requests`, `GET /leave-requests/{leaveRequestId}`, `POST /leave-requests/{leaveRequestId}/approve`, `POST /leave-requests/{leaveRequestId}/reject` |
| Chính sách nghỉ phép | HR, ADMIN | `GET /leave-types`, `POST /leave-types`, `PATCH /leave-types/{leaveTypeId}` |
| Hồ sơ lương | HR, ADMIN | `GET /employees/{employeeId}/compensations`, `POST /employees/{employeeId}/compensations` |
| Kỳ lương và bảng lương | HR; nhân viên xem phiếu của mình | `POST /payroll-periods`, `GET /payroll-periods`, `GET /payroll-periods/{periodId}/lines`, `POST /payroll-periods/{periodId}/calculate`, `POST /payroll-periods/{periodId}/submit`, `POST /payroll-periods/{periodId}/approve`, `POST /payroll-periods/{periodId}/close`, `GET /payroll/me/slips` |

### Quy tắc API trọng yếu

- `POST /attendance/scans` nhận `qrToken`, `eventType` (`CHECK_IN`/`CHECK_OUT`), `deviceId`, `idempotencyKey`; backend xác minh token, thẻ còn hiệu lực, thiết bị, trùng lượt và thời gian.
- `POST /attendance/fixes` nhận `workDate`, `eventType`, `requestedAt`, `reason`. Chỉ chủ đơn hoặc HR được tạo; người duyệt không được là người gửi nếu chính sách phân tách nhiệm vụ yêu cầu.
- Đơn công/phép chỉ được duyệt khi `PENDING`; thao tác duyệt/từ chối lặp phải trả kết quả xung đột thay vì tạo hiệu ứng lần hai.
- `POST /leave-requests` chỉ nhận `leaveDate` và `session` là `MORNING` hoặc `AFTERNOON`; server từ chối yêu cầu toàn ngày và đơn trùng buổi của cùng nhân viên.
- Payroll chỉ được tính/chốt khi dữ liệu đầu vào hợp lệ; kỳ `CLOSED` là bất biến. Mọi lần tính lại trước chốt cần lưu phiên bản/kết quả tính và người thực hiện.
- Quyền truy cập phiếu lương nhân viên giới hạn theo tài khoản đang đăng nhập; HR có quyền theo chính sách được cấp.

## 5. Thiết kế cơ sở dữ liệu

### Các thực thể chính

| Nhóm | Bảng | Mục đích |
|---|---|---|
| Tổ chức | `hr_departments`, `hr_positions`, `hr_employees` | Cơ cấu tổ chức và hồ sơ nhân viên |
| Tài khoản | `hr_user_accounts`, `hr_roles`, `hr_user_role_assignments` | Đăng nhập và phân quyền |
| QR/chấm công | `hr_qr_cards`, `hr_attendance_events`, `hr_attendance_days`, `hr_attendance_fixes` | Credential QR, log gốc, tổng hợp ngày công và giải trình |
| Nghỉ phép | `hr_leave_types`, `hr_leave_requests` | Loại nghỉ và yêu cầu nghỉ theo buổi |
| Lương | `hr_employee_compensation`, `hr_payroll_periods`, `hr_payroll_lines` | Lịch sử mức lương, kỳ lương và snapshot lương |

### DBML sơ bộ

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
	manager_employee_id bigint
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
	password_hash varchar(255) [not null, note: 'Hash bằng thuật toán password hashing chuyên dụng; không lưu mật khẩu thô']
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

Table hr_qr_cards {
	qr_card_id bigint [pk, increment]
	employee_id bigint [not null]
	token_hash varchar(255) [not null, unique]
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
	device_id varchar(100)
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
	attendance_status varchar(20) [not null, note: 'PRESENT, INCOMPLETE, ABSENT, ON_LEAVE']
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
	reviewer_employee_id bigint
	reviewed_at timestamp
	review_note text
	created_at timestamp [not null, default: `now()`]
}

Table hr_leave_types {
	leave_type_id bigint [pk, increment]
	leave_code varchar(30) [not null, unique]
	leave_name varchar(100) [not null]
	is_paid boolean [not null, default: true]
	is_active boolean [not null, default: true]
}

Table hr_leave_requests {
	leave_request_id bigint [pk, increment]
	employee_id bigint [not null]
	leave_type_id bigint [not null]
	leave_date date [not null]
	session varchar(20) [not null, note: 'MORNING hoặc AFTERNOON; mỗi đơn đúng một buổi']
	reason text
	status varchar(20) [not null, note: 'PENDING, APPROVED, REJECTED, CANCELLED']
	reviewer_employee_id bigint
	reviewed_at timestamp
	review_note text
	created_at timestamp [not null, default: `now()`]
}

Table hr_employee_compensation {
	employee_compensation_id bigint [pk, increment]
	employee_id bigint [not null]
	base_monthly_salary decimal(18, 2) [not null]
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
	start_date date [not null]
	end_date date [not null]
	status varchar(20) [not null, note: 'DRAFT, CALCULATED, PENDING_APPROVAL, APPROVED, CLOSED']
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
	base_salary decimal(18, 2) [not null]
	allowance_amount decimal(18, 2) [not null, default: 0]
	overtime_amount decimal(18, 2) [not null, default: 0]
	deduction_amount decimal(18, 2) [not null, default: 0]
	gross_salary decimal(18, 2) [not null]
	net_salary decimal(18, 2) [not null]
	calculation_details json
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
Ref: hr_qr_cards.employee_id > hr_employees.employee_id
Ref: hr_qr_cards.created_by_user_id > hr_user_accounts.user_account_id
Ref: hr_attendance_events.employee_id > hr_employees.employee_id
Ref: hr_attendance_events.qr_card_id > hr_qr_cards.qr_card_id
Ref: hr_attendance_events.attendance_fix_id > hr_attendance_fixes.attendance_fix_id
Ref: hr_attendance_days.employee_id > hr_employees.employee_id
Ref: hr_attendance_fixes.employee_id > hr_employees.employee_id
Ref: hr_attendance_fixes.reviewer_employee_id > hr_employees.employee_id
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

### Ràng buộc dữ liệu cần triển khai

- `hr_leave_requests`: chỉ nhận `MORNING`/`AFTERNOON`; unique theo nhân viên, ngày, buổi cho các đơn chưa bị hủy. Một ngày không thể tạo hai đơn cùng buổi.
- `hr_attendance_fixes`: chỉ một yêu cầu đang `PENDING` cho cùng nhân viên/ngày/loại lượt; khi duyệt phải tạo đúng một `hr_attendance_events` nguồn `APPROVED_FIX`.
- `hr_employee_compensation`: các khoảng `effective_from`/`effective_to` của cùng nhân viên không được chồng lấn.
- `hr_payroll_lines`: mỗi nhân viên có tối đa một dòng trong một kỳ; lưu snapshot số tiền và đầu vào để truy vết.
- Dùng transaction khi duyệt yêu cầu, tạo event điều chỉnh và cập nhật ngày công; không xóa cứng dữ liệu công/lương đã phát sinh.

## 6. Câu hỏi cần chốt trước khi triển khai

1. Nghỉ “một buổi hoặc nửa buổi” có nghĩa chỉ nghỉ một buổi sáng/chiều (nửa ngày), hay cần cho phép nghỉ nửa buổi làm việc (một phần tư ngày)?
2. Ai có quyền duyệt giải trình công và phép; có yêu cầu quản lý trực tiếp duyệt trước HR không?
3. Lịch làm việc, ca, ngày nghỉ lễ, quy tắc đi trễ/về sớm và cách xử lý thiếu lượt quẹt là gì?
4. Công thức lương cần gồm khoản nào; quy định thuế, bảo hiểm, làm thêm giờ và ngày công chuẩn do ai cung cấp?
5. Có cần quản lý số dư phép, chuyển phép, nghỉ không lương, nhiều chi nhánh hoặc xuất bảng lương ra Excel/PDF ở phiên bản đầu không?
6. QR là thẻ vật lý tĩnh hay QR trên ứng dụng có thể thay đổi theo thời gian; kiosk chạy trên thiết bị nào và cần hoạt động offline không?
