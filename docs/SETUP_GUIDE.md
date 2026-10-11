# HƯỚNG DẪN CÀI ĐẶT & TRIỂN KHAI DỰ ÁN (PROJECT SETUP & DEPLOYMENT GUIDE)
## HỆ THỐNG QUẢN LÝ NHÂN SỰ & CHẤM CÔNG THÔNG MINH (GROUP 3 HRMS)

---

### 1. Yêu cầu hệ thống (Prerequisites)

Trước khi bắt đầu cài đặt, đảm bảo máy tính của bạn đã cài đặt các công cụ sau:
* **Hệ điều hành:** macOS, Linux (Ubuntu/Debian/Fedora), hoặc Windows 11 (khuyến nghị dùng WSL2).
* **Git:** Phiên bản `>= 2.30`
* **Docker & Docker Compose:** Docker Engine `>= 24.0`, Docker Compose `>= v2.20`
* **Python:** Phiên bản `>= 3.10` (Khuyến nghị Python 3.11 hoặc 3.12/3.14)
* **Node.js & npm:** Node.js `>= 18.x` (Khuyến nghị LTS 20.x) và npm `>= 9.x`

---

### 2. Cấu trúc thư mục dự án

```text
hr-project-msa45hcm-group3/
├── .env.example              # File mẫu cấu hình biến môi trường
├── .gitignore                # Danh sách loại trừ Git
├── docker-compose.yml        # Định nghĩa dịch vụ PostgreSQL 16
├── README.md                 # Tài liệu tổng quan dự án
├── docs/                     # Tài liệu kỹ thuật
│   ├── ARCHITECTURE.md       # Tài liệu Kiến trúc Phần mềm (SAD)
│   └── SETUP_GUIDE.md        # Hướng dẫn cài đặt & vận hành (File này)
├── backend/                  # Nguồn Backend FastAPI
│   ├── alembic/              # Thư mục migration cơ sở dữ liệu
│   ├── app/                  # Mã nguồn ứng dụng (models, schemas, services, api)
│   ├── tests/                # Bộ kiểm thử tự động (pytest)
│   ├── requirements.txt      # Thư viện phụ thuộc Python
│   └── pytest.ini            # Cấu hình pytest
└── frontend/                 # Nguồn Frontend React TypeScript
    ├── src/                  # Mã nguồn giao diện (components, pages, context, api)
    ├── package.json          # Thư viện phụ thuộc npm
    └── vite.config.ts        # Cấu hình Vite & API Proxy
```

---

### 3. Hướng dẫn cài đặt từng bước (Step-by-Step Setup)

#### Bước 1: Clone mã nguồn dự án
```bash
git clone https://github.com/duy26ms23415-web/hr-project-msa45hcm-group3.git
cd hr-project-msa45hcm-group3
```

#### Bước 2: Thiết lập biến môi trường (`.env`)
Tạo file `.env` từ file mẫu `.env.example`:
```bash
cp .env.example .env
cp .env.example backend/.env
```

**Bảng giải thích các biến môi trường quan trọng:**

| Tên biến | Giá trị mặc định | Giải thích ý nghĩa |
| :--- | :--- | :--- |
| `POSTGRES_SERVER` | `localhost` | Địa chỉ máy chủ PostgreSQL |
| `POSTGRES_PORT` | `5432` | Cổng kết nối PostgreSQL |
| `POSTGRES_USER` | `hr_user` | Tên tài khoản Database |
| `POSTGRES_PASSWORD` | `hr_secret_password` | Mật khẩu tài khoản Database |
| `POSTGRES_DB` | `hr_management_db` | Tên Database |
| `SECRET_KEY` | *(Chuỗi bảo mật 32+ ký tự)* | Khóa bí mật ký mã hóa JWT Token |
| `KIOSK_API_SECRET_KEY`| `kiosk_secret_key_group3` | Mã khóa bảo mật của thiết bị Kiosk quét QR |
| `GEMINI_API_KEY` | *(Để trống hoặc điền key Google)*| Khóa API Google Gemini cho Trợ lý AI |
| `GEMINI_MODEL_NAME` | `gemini-1.5-flash` | Tên mô hình AI được sử dụng |

---

#### Bước 3: Khởi động Cơ sở dữ liệu PostgreSQL qua Docker
Khởi chạy container PostgreSQL 16 ở chế độ chạy ngầm (detached mode):
```bash
docker compose up -d
```

Kiểm tra trạng thái container đang hoạt động khỏe mạnh:
```bash
docker ps
```
*(Đảm bảo container `hr_postgres_group3` có trạng thái `Up (healthy)` trên cổng `5432`)*.

---

#### Bước 4: Thiết lập và Khởi động Backend (FastAPI)

1. **Tạo và kích hoạt môi trường ảo Python (Virtual Environment):**
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate  # Trên Windows: .venv\Scripts\activate
   ```

2. **Cài đặt các gói phụ thuộc (Dependencies):**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Chạy Migration Cơ sở dữ liệu (Alembic):**
   Cập nhật cấu trúc bảng lên phiên bản mới nhất:
   ```bash
   alembic upgrade head
   ```

4. **Nạp dữ liệu mẫu khởi tạo (Seed Data):**
   Khởi tạo sẵn các phòng ban, chức vụ, nhân viên, số dư phép năm 12 ngày và tài khoản demo:
   ```bash
   python -m app.scripts.seed_data
   ```

5. **Khởi chạy máy chủ Backend Development (Uvicorn):**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   * Backend API: `http://127.0.0.1:8000`
   * Tài liệu tương tác API Swagger UI: `http://127.0.0.1:8000/api/v1/docs`
   * Kiểm tra sức khỏe hệ thống: `http://127.0.0.1:8000/health`

---

#### Bước 5: Thiết lập và Khởi động Frontend (React + Vite)

Mở một cửa sổ Terminal mới:
```bash
cd frontend
npm install
npm run dev
```
* Ứng dụng Frontend chạy tại: `http://localhost:5173`
* Mọi request đến `/api/*` sẽ được Vite tự động chuyển tiếp (proxy) an toàn về Backend `http://127.0.0.1:8000`.

---

### 4. Danh sách tài khoản Demo & Kịch bản kiểm thử (Testing Scenarios)

Hệ thống đã có sẵn 3 tài khoản mẫu được kích hoạt đầy đủ quyền:

| Vai trò | Email | Mật khẩu | Phạm vi chức năng kiểm thử |
| :--- | :--- | :--- | :--- |
| **Admin & HR** | `admin@hrgroup3.com` | `Password@123` | Quản trị nhân sự, cấp phát thẻ QR, tạo & tính bảng lương, xuất Excel, khóa kỳ lương. |
| **Quản lý (Manager)** | `manager@hrgroup3.com` | `Password@123` | Chấm công cá nhân, phê duyệt đơn giải trình công và đơn xin nghỉ phép của cấp dưới. |
| **Nhân viên (Employee)**| `employee@hrgroup3.com` | `Password@123` | Quẹt thẻ Kiosk, xem lịch công, gửi giải trình, nộp đơn nghỉ phép, xem phiếu lương. |

#### Kịch bản 1: Quẹt thẻ chấm công Kiosk
1. Mở trang Kiosk: `http://localhost:5173/kiosk`.
2. Bấm vào nút quẹt thẻ mẫu **"Quẹt: Employee (EMP003)"**.
3. Hệ thống phát âm thanh bíp, nổ pháo hoa (`confetti`) và thông báo **CHECK_IN** thành công.
4. Bấm lại một lần nữa sau giờ làm để ghi nhận **CHECK_OUT** và xem tổng giờ làm việc tích lũy trong ngày.

#### Kịch bản 2: Giải trình quên chấm công & Quản lý duyệt
1. Đăng nhập tài khoản **Nhân viên** (`employee@hrgroup3.com`).
2. Vào mục **Chấm công** -> Bấm **Gửi giải trình bổ sung công** (chọn ngày và loại quẹt, nhập lý do).
3. Đăng xuất, đăng nhập vào tài khoản **Quản lý** (`manager@hrgroup3.com`).
4. Vào mục **Chấm công** -> Tab **Duyệt giải trình** -> Bấm **Duyệt** và nhập ghi chú.
5. Bảng công của nhân viên lập tức được cập nhật sang trạng thái hợp lệ (`PRESENT`).

#### Kịch bản 3: Xin nghỉ phép theo buổi & Hạn mức phép năm
1. Đăng nhập tài khoản **Nhân viên** (`employee@hrgroup3.com`) -> Vào mục **Nghỉ phép**.
2. Kiểm tra số dư phép năm (được cấp 12 ngày).
3. Bấm **Tạo đơn xin nghỉ phép**, chọn buổi **Buổi sáng (0.5 công)** hoặc **Buổi chiều (0.5 công)** hoặc **Cả ngày (1.0 công)**.
4. Đăng nhập tài khoản **Quản lý** (`manager@hrgroup3.com`) -> Tab **Duyệt đơn nghỉ phép** -> Bấm **Duyệt**.
5. Số dư ngày phép của nhân viên tự động được trừ chính xác.

#### Kịch bản 4: Tính lương, Khóa kỳ & Xuất file Excel
1. Đăng nhập tài khoản **Admin & HR** (`admin@hrgroup3.com`) -> Vào mục **Bảng lương**.
2. Bấm **Tính bảng lương** cho kỳ hiện tại.
3. Xem bảng lương chi tiết (Lương Gross, Trích bảo hiểm 10.5%, Giảm trừ bản thân 11M, Thuế TNCN, Lương Net).
4. Bấm **Xuất file Excel** -> Trình duyệt tự động tải về file `Bang_Luong_Thang_X.xlsx` hoàn chỉnh.
5. Bấm **Khóa kỳ lương** -> Hệ thống chốt số liệu và chặn mọi hành động chỉnh sửa chấm công/nghỉ phép của tháng này.

#### Kịch bản 5: Trải nghiệm Trợ lý ảo AI
1. Nhấn nút Trợ lý AI ở góc phải màn hình.
2. Bấm thử các câu hỏi nhanh:
   * *"Quy chế giờ làm việc và nghỉ trưa?"*
   * *"Số dư phép năm của tôi còn bao nhiêu?"*
   * *"Tôi muốn xin nghỉ phép sáng mai"* -> AI tự động tạo thẻ hành động đề xuất tạo đơn!

---

### 5. Chạy Kiểm thử tự động (Automated Test Suite)

Dự án trang bị bộ kiểm thử tích hợp đầy đủ từ xác thực, chấm công, nghỉ phép, tính lương, xuất Excel đến AI:

```bash
cd backend
source .venv/bin/activate
pytest tests/test_api.py -v
```

**Kết quả mong đợi:** Toàn bộ `6/6 tests PASSED 100%`:
* `test_health_check` PASSED
* `test_login_flow` PASSED
* `test_qr_card_issue_and_kiosk_scan` PASSED
* `test_leave_request_and_manager_approval` PASSED
* `test_payroll_calculation_and_export` PASSED
* `test_ai_chat_flow` PASSED

Kiểm tra biên dịch Frontend:
```bash
cd frontend
npm run build
```
*(Kết quả: `built in ...ms` thành công không có lỗi TypeScript).*

---

### 6. Cẩm nang xử lý sự cố (Troubleshooting Guide)

#### Q1: Cổng 5432 hoặc Cổng 8000 đã bị ứng dụng khác chiếm dụng?
* **Khắc phục:** 
  * Tìm tiến trình đang chiếm cổng: `lsof -i :8000` hoặc `lsof -i :5432`.
  * Đổi cổng trong file `docker-compose.yml` (ví dụ `5433:5432`) và cập nhật lại `POSTGRES_PORT=5433` trong file `.env`.

#### Q2: Trợ lý AI có bị treo khi mất mạng hoặc không có API Key?
* **Giải đáp:** Hoàn toàn **không**. Hệ thống đã được lập trình với cơ chế bảo vệ kép (`asyncio.wait_for` timeout 5s + `asyncio.to_thread`). Khi không có API key hoặc mạng chậm, hệ thống tự động trả lời bằng Bộ luật tri thức nội bộ cục bộ trong vòng dưới 20ms mà không làm nghẽn máy chủ.

#### Q3: Quản lý không thấy đơn duyệt của nhân viên?
* **Nguyên nhân:** Nhân viên chưa được gán người quản lý trực tiếp.
* **Khắc phục:** Vào tài khoản Admin -> Mục **Nhân sự** -> Cập nhật trường `manager_employee_id` cho nhân viên đó trỏ về ID của Quản lý.
