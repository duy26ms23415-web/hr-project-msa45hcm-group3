# HƯỚNG DẪN CÀI ĐẶT & TRIỂN KHAI DỰ ÁN (PROJECT SETUP & DEPLOYMENT GUIDE)

Kiểm tra hồi quy hai parser tại backend bằng interpreter Conda hr-backend: `python -B -m pytest tests/unit/test_ai_service.py tests/unit/test_knowledge_storage.py -q`. Tests kiểm lý do có từ chỉ ngày/buổi/giờ vẫn giữ trường đã chọn, câu nhập gộp buổi/lý do, PDF XFA/action trong form/bookmark, bookmark an toàn và đồ thị có vòng lặp. Tests dùng mock/PDF trong bộ nhớ, không ghi DB hoặc gọi Gemini thật; không cần cấu hình, dependency hay migration mới.

Để tiết kiệm quota, giữ `GEMINI_ENABLED=false` trong môi trường backend; có API key cũng không tự bật provider. Chỉ đặt true và khởi động lại backend khi muốn dùng Gemini cho yêu cầu ngoài fallback. Giới hạn đầu ra cố định 128/256/384 token, nguồn 4.000 ký tự, timeout 5 giây và không retry. Không cần dependency mới.

## HỆ THỐNG QUẢN LÝ NHÂN SỰ & CHẤM CÔNG THÔNG MINH (GROUP 3 HRMS)

Kiểm viewer trên Windows có Edge chuẩn bằng `node scripts/check_ai_viewer.mjs` trong frontend sau npm run build. Harness đã chạy: React viewer render đúng heading ba PDF và mẫu denied với API fixture; không dùng DB, không cài packages và không thay backend production. Profiles/ảnh/DOM tạm nằm trong validation dir gitignore. Scope defaults/employee linkage và quota năm của ngày nghỉ do backend xác thực; không cần cấu hình mới. Gate DB/multi-process/browser tương tác chưa đạt, xem [AI_ACCEPTANCE](AI_ACCEPTANCE.md).

Head migration mới d9e0f1a2b3c4 cần áp dụng bằng `python -B -m alembic upgrade head` trên DB development/test xác định trước khi dùng báo cáo lương. Thêm currency_code nullable cho snapshot; không suy ra currency legacy từ compensation hiện tại và không tự điền VND. Sau upgrade, HR cần xác minh mã từ hồ sơ gốc của các dòng cũ; nếu chưa xác minh, report trả 409 PAYROLL_CURRENCY_UNAVAILABLE và không tạo file. Kỳ tính mới ghi currency từ hồ sơ nguồn. Chưa chạy upgrade trên DB test; không downgrade để thử vì sẽ mất snapshot currency mới.

Suggestion có default_inputs; có thể gửi suggestion_id + inputs cho nháp/report, backend kiểm command fields và quyền. Frontend dùng types chung, đọc JSON error cả khi responseType blob. JWT hết hạn chuyển `/login?reason=session-expired` để giữ mẫu SESSION_EXPIRED; query chỉ là nhãn thông báo, không có token hay dữ liệu cá nhân. Kiosk giữ ngoại lệ cũ. Không thêm dependencies.

Generator tạo thêm ba bản Markdown trong docs/knowledge-drafts cùng PDF/manifest. Cleanup report mặc định dry-run, --apply còn dọn UUID artifacts không được run nào tham chiếu đã quá hai giờ và metadata không còn keys đã hết hạn quá 30 ngày. Scan giữ file mới/referenced/symlink/tên ngoài định dạng server; DB lỗi thì không dọn orphan. Job cần account DB maintenance phù hợp, không chạy bằng DB production chỉ để kiểm chứng. Chưa chạy job trên DB test.

PDF demo được tạo lại với mục lục/bookmarks/số trang, PDF báo cáo có đủ bảy loại và hướng dẫn preview/Excel. Generator tự kiểm parser/page/heading/outline và cập nhật manifest hash. Seed hiện hữu có hash khác sẽ từ chối ghi đè: cần import phiên bản DRAFT mới qua UI thay vì sửa tài liệu đã công bố. Gợi ý chỉ gắn tham khảo đúng mục khi nguồn được công bố và actor được đọc. File report quá TTL trả 410 REPORT_EXPIRED cho owner; client nên tạo run mới. Không có migration bổ sung.

Envelope lỗi AI/knowledge/reports được cài từ app.main, không thêm config/dependency/migration. Client đọc code/message/request_id, giữ xử lý HTTP status và detail cũ trong thời gian chuyển đổi. 429 giữ Retry-After; mọi lỗi có private/no-store và không echo input. Khi gọi chat cấu trúc, có thể chỉ gửi suggestion_id; tiếp tục nháp phải có draft_id + draft_revision và inputs hoặc message. Cập nhật client trước nếu client cũ gửi draft_id mà bỏ revision. Nghiệm thu runtime lỗi DB/provider vẫn chưa có bằng chứng tích hợp.

Nháp báo cáo nhiều lượt dùng migration bảng nháp/run hiện có, không thêm dependency hay cấu hình. Sau setup DB, nhập “Tạo báo cáo công”, chọn kỳ rồi chọn phạm vi được cấp quyền; kết quả phải có run_id thật và tải Excel cùng snapshot. Gợi ý báo cáo có sẵn dùng kỳ/phạm vi ghi trong prompt. Có thể nhập “tháng 9/2026” hoặc “2026-09-01 đến 2026-09-30”; phiếu/tổng hợp lương chỉ nhận trọn tháng APPROVED/CLOSED. `inputs` chỉ chứa kind/start_date/end_date/scope/department_id cho DRAFT_REPORT; backend không nhận employee IDs. Luồng đã kiểm tra bằng unit tests/browser fixture; chưa xác minh tích hợp DB/Gemini thật.

Gợi ý chính sách cần PDF PUBLISHED/effective/answerable mà actor được đọc. Nếu nguồn bị thu hồi sau khi UI lấy gợi ý, chat trả KNOWLEDGE_NOT_FOUND; fallback này hoạt động khi không cấu hình Gemini và không cần employee linkage. Không có cấu hình hoặc migration bổ sung cho dispatch này.

**AI hiện tại:** backend kiểm tra JWT/role/scope; chat từ chối field quyền do client gửi. Có bảy loại report JSON/CSV/XLSX template v1, ReportRun private với UI preview/download trong chat và TTL một giờ; chat fallback tạo được run thật. Draft owner/revision/typed fields/TTL 15 phút, chỉ mở form để người dùng gửi. Gemini schema đóng sau fallback, không nhận history/DB rows; key vẫn tùy chọn. MY_PAYSLIP/PAYROLL_SUMMARY đã có, chỉ phát hành APPROVED/CLOSED; Report đọc currency snapshot và không gộp khác tiền tệ. PDF private/version/section/viewer, ba PDF demo DRAFT và seed có kiểm soát đã có. Audit/rate limit cần migration mới; SQL logs ẩn tham số. Migration/seed, DB concurrency và browser flow chưa được kiểm chứng tích hợp. Xem [AI Copilot](AI_COPILOT.md).

Xuất Excel dùng `openpyxl` (đã có trong `backend/requirements.txt`), qua `GET /api/v1/reports?kind=ATTENDANCE&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&output=xlsx`. Các kind được hỗ trợ: `ATTENDANCE`, `LEAVE`, `ATTENDANCE_FIX`, `APPROVAL_QUEUE`, `HEADCOUNT`, `MY_PAYSLIP`, `PAYROLL_SUMMARY`. Đây là file `.xlsx` có sheet Thông tin/Dữ liệu/Tổng hợp, sinh đồng bộ từ truy vấn đã phân quyền; JSON/CSV/XLSX trả `private, no-store`.

`POST /api/v1/reports/runs` tạo snapshot + XLSX riêng tư và trả `run_id`; `GET /api/v1/reports/runs` liệt kê run của user; `GET /api/v1/reports/runs/{run_id}` xem preview; `GET /api/v1/reports/runs/{run_id}/download` tải file. Hết hạn sau 1 giờ; tải lịch sử sẽ dọn artifacts quá hạn. Cấu hình `REPORT_STORAGE_DIR` mặc định `backend/storage/private/reports`, nằm ngoài static serving và được `.gitignore` loại trừ. Từ thư mục `backend/`, xem trước số run cần dọn bằng `python -B -m scripts.cleanup_expired_report_runs`; lập lịch xóa bằng `python -B -m scripts.cleanup_expired_report_runs --apply`. Script chỉ xóa file được tham chiếu bởi run hết hạn, chuyển READY/GENERATING thành EXPIRED và giữ FAILED. Lifecycle dùng session riêng, chốt phạm vi trước truy vấn, chỉ READY khi cả snapshot/XLSX được lưu; lỗi không trả file giả. DB mất kết nối có thể ngăn lưu FAILED. Không cần dependency/migration mới cho thay đổi lifecycle; cleanup chưa chạy trên DB test. Trong Excel, chỉ số là kiểu số; trường text được escape để ngăn formula injection.

Leave và attendance fixes có view `mine`, `approvals`, `visible`. Approval list hiện kiểm tra quan hệ quản lý trực tiếp và lấy đơn PENDING; quyền được kiểm tra lại khi duyệt/từ chối.

Duyệt phép khóa dòng đơn trước khi kiểm tra trạng thái, không cần migration, cấu hình hoặc dependency mới. Tại `backend/`, dùng interpreter Conda `hr-backend` chạy `python -B -m pytest tests/unit/test_leave_review.py -q`: đã đạt hai trường hợp duyệt/duyệt và duyệt/từ chối đồng thời với khóa mô phỏng, không ghi DB thật. Kiểm chứng PostgreSQL còn cần DB test riêng: gửi hai request cho cùng đơn PENDING, xác nhận một quyết định thành công, lượt sau HTTP 400 và số dư chỉ bị trừ một lần; chưa chạy kiểm chứng này trên DB thật.

Migration `b7c8d9e0f1a2` tạo bảng version/section knowledge, chat drafts và report runs, đồng thời backfill legacy text với page null. Chưa chạy `alembic upgrade head` trên DB test; chỉ xác minh sinh SQL offline. Không dùng database production để xác minh migration.

Migration kế tiếp `c8d9e0f1a2b3` tạo `hr_ai_request_events` cho audit và hạn mức dùng chung giữa process. Cần áp dụng migration trước khi dùng chat/báo cáo; thiếu kho bảo mật trả `503 DATA_SERVICE_UNAVAILABLE`. Hạn mức cố định: 20 chat và 5 báo cáo/tài khoản/phút; 429 có `Retry-After`. Không cần Redis hoặc dependency mới. Audit không giữ prompt/history/lý do, retention 90 ngày. Từ `backend/`, xem trước bằng `python -B -m scripts.cleanup_ai_audit`; chỉ thêm `--apply` khi muốn xóa các event quá retention. Cấu hình lịch chạy hằng ngày bằng scheduler của môi trường triển khai. Các lệnh cleanup/migration mới chưa chạy trên DB test.

Để dùng fallback Excel từ chatbot khi Gemini tắt, chọn “Tạo báo cáo công của tôi tháng này”. API tạo ReportRun từ DB, trả `run_id`; preview xuất hiện trong chat, bấm “Tải Excel” để tải cùng snapshot. Kỳ khác hỏi hoặc chỉnh ngay trong chat; không tạo giả khi DB lỗi. Nháp nhiều lượt gửi cả `draft_id` và `draft_revision`, 409 yêu cầu bắt đầu lại. Lương chỉ được phát hành ở **APPROVED hoặc CLOSED** (D01 đã chốt).

Client chọn gợi ý server gửi `suggestion_id`; backend resolve registry và từ chối ID trái quyền với 403. `suggestion_id` không đi cùng draft/inputs. Follow-up có thể gửi `inputs` như `{"session":"MORNING"}` cùng draft ID/revision; không nhận employee/role/path. Response có `status`, `missing_fields`, `message_code`, `request_id`; UI chọn nhanh buổi/loại/lượt công và hủy nháp. Không thêm cấu hình, migration hoặc dependency cho thay đổi này. Key Gemini vẫn có thể để trống; thiếu nguồn nội quy trả mẫu KNOWLEDGE_NOT_FOUND.

Trong “Phiên bản PDF”, HR/ADMIN chọn “Sửa mục/trang” để chỉnh title/minimum_role/effective_from/effective_to và mapping DRAFT. JSON section gồm section_code, heading, page_start, page_end, is_answerable (boolean, mặc định true). Heading phải khớp PDF; dùng false cho mục chưa ban hành. Lưu kiểm parser/hash rồi cập nhật nguyên tử; PUBLISHED trả 409 khi sửa. “Xem trước” dùng viewer với preview=true, JWT và quyền HR/ADMIN trên cả document/version; không công bố tài liệu. Không có migration/dependency mới cho editor; file storage đã tồn tại phải đúng hash đã lưu.

Các template đã tạo nằm trong `backend/app/report_templates/*_v1.xlsx`. Khi thay định nghĩa cột/style, từ `backend/` chạy `python -B -m scripts.generate_report_templates` để tạo lại bảy file (lệnh đã chạy thành công). Runtime đọc template theo kind cố định, không nhận path từ client. Report vượt 10.000 dòng trả `REPORT_TOO_LARGE`, không truncate. Phiếu/tổng hợp lương chọn trọn một tháng; phiếu chỉ SELF, tổng hợp HR/ADMIN có bộ lọc phòng ban. Nhân viên chỉ thấy phiếu APPROVED/CLOSED; API quản trị HR/ADMIN vẫn đọc bản tính để rà soát trước phát hành. Migration d9e0f1a2b3c4 thêm currency_code nullable: legacy giữ NULL, không suy ra từ hồ sơ hiện tại; report từ chối nếu chưa được HR xác minh.

Chat dùng catalog theo quyền, hỏi bộ lọc còn thiếu rồi tạo ReportRun. Preview phân trang 50 dòng, XLSX tải toàn bộ cùng snapshot. API history giữ tương thích nhưng UI không hiển thị lịch sử tải. Route frontend /reports cũ chuyển về dashboard và mở chat. Không có migration/dependency mới; deploy kèm bảy template v1.

Kiểm chứng: 63 unit/API tests với mock và frontend build đạt; build còn warning chunk >500 kB. `alembic upgrade head --sql` đã sinh SQL offline qua revision `c8d9e0f1a2b3`; đây không phải upgrade DB. Docker không có trong PATH phiên này; chưa chạy migration/seed, budget concurrency hoặc browser acceptance trên DB test.

Draft trong chat dùng cùng migration: request kế tiếp gửi `draft_id` opaque; backend chỉ truy vấn theo cả draft ID và `user_account_id` từ JWT, khóa dòng khi cập nhật, chỉ cho command `DRAFT_LEAVE`/`DRAFT_FIX` với field allowlist, và hết hạn sau 15 phút. Không truyền danh tính nhân viên từ client; form nghiệp vụ hiện có vẫn là nơi người dùng xem lại và chủ động gửi đơn.

PDF: backend dùng `pypdf` để kiểm tra/trích text và `reportlab` cho PDF demo; frontend dùng `pdfjs-dist` với worker local. Các package đã được thêm vào manifest/lock; lệnh `pip install 'pypdf>=5.4,<7' 'reportlab>=4.2,<5'` và `npm install pdfjs-dist@^6.3.289` đã chạy thành công trong môi trường hiện tại. Storage mặc định nằm tại `backend/storage/private/ai-knowledge` (không static serve, được gitignore); cấu hình `AI_KNOWLEDGE_STORAGE_DIR` phải trỏ tới thư mục riêng tư. Giới hạn mặc định 10 MiB/100 trang qua `AI_KNOWLEDGE_MAX_UPLOAD_BYTES` và parser.

Để tạo lại ba PDF minh họa (nghỉ phép, chấm công, bảo mật báo cáo), từ thư mục `backend/` chạy `python scripts/generate_demo_knowledge.py`; file và manifest được ghi vào `storage/tmp/ai-knowledge-demo`. Script dùng font Unicode cài sẵn; có thể đặt `AI_KNOWLEDGE_FONT_FILE` nếu máy không có font phù hợp. Các nội dung đều là DRAFT, không đại diện quy định đã được công ty thông qua. Sau khi migration đã áp dụng lên DB development/test, nạp bằng `python scripts/seed_demo_knowledge.py --creator-user-id <ID_TAI_KHOAN_ACTIVE> --confirm-demo-seed`. Seed từ chối môi trường khác development/test, yêu cầu người tạo active, không publish tài liệu và không ghi đè document có nội dung khác. PDF được sao chép vào private storage; DB lưu storage key, không lưu public path.

Sau đăng nhập, frontend gọi `GET /api/v1/ai/suggestions`; API dùng role từ JWT/server và chỉ gắn liên kết PDF nếu tài liệu đang publish và user được đọc. Handler deterministic luôn chạy trước Gemini. Nếu không có key/timeout/quota cho câu hỏi HR tự do chưa có handler, backend trả `503 AI_UNAVAILABLE`; frontend hiển thị đúng mẫu. Mất kết nối HR dùng mẫu `SERVICE_UNREACHABLE`, còn 403 dùng `PERMISSION_DENIED`. Các lỗi không giữ action cũ và không thay dữ liệu thật bằng mẫu.

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
   Cập nhật cấu trúc bảng lên phiên bản mới nhất từ thư mục `backend/`:
   ```bash
   alembic upgrade head
   ```

   Nếu chạy từ root của repo bằng PowerShell/Conda hr-backend, chỉ rõ config:
   ```powershell
   & "C:\Users\huetr\miniconda3\envs\hr-backend\python.exe" -B -m alembic -c backend/alembic.ini upgrade head
   ```
   Không có `-c` ở root sẽ báo `No 'script_location' key found in configuration`. Config dùng đường dẫn theo vị trí `alembic.ini`; migration đọc `backend/.env` dù chạy từ root. PostgreSQL phải đang chạy và khớp cấu hình backend; `Connection refused` tại localhost:5432 nghĩa là chưa kết nối được DB, không phải thiếu migration.

   Revision `f1a2b3c4d5e6` hợp nhất hai head QR/AI (`b7c9d1e2f304`, `e0f1a2b3c4d5`). Hai nhánh QR dùng `ADD COLUMN IF NOT EXISTS` để tránh thêm trùng `card_code`. Merge không sửa dữ liệu; dùng `upgrade head`, không cần stamp/downgrade/reset DB.

   Với Docker chạy trong WSL, giữ một terminal WSL mở khi chạy Python trên Windows. Nếu container báo healthy nhưng Windows localhost:5432 bị từ chối, kiểm tra phiên WSL/localhost forwarding trước khi đổi credentials. Lệnh từ root `upgrade head` và `current` đã kiểm chứng trên PostgreSQL development, head là `f1a2b3c4d5e6`; SQL offline cũng sinh thành công. Không suy ra migration đã chạy trên các DB khác.

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

Gợi ý chat được thu gọn trong menu “Gợi ý câu hỏi”; khi soạn nháp chỉ hiện lựa chọn cần thiết cho bước hiện tại.


Để dùng Gemini nhận ngày từ câu chat, đặt `GEMINI_ENABLED=true` và cấu hình `GEMINI_API_KEY`/`GEMINI_MODEL_NAME`, rồi khởi động lại backend. Không có key hoặc provider tắt: định dạng số/ngày tương đối phổ biến vẫn chạy bằng Python. Gemini trả null khi “tháng sau” chưa có ngày cụ thể; chatbot yêu cầu bổ sung. Kiểm tra ví dụ “tạo đơn nghỉ phép năm vào thứ 3 tuần sau”, rồi trả lời buổi/lý do chung một câu.

Template Excel tạo lại bằng `python -B scripts/generate_report_templates.py` tại backend với `PYTHONPATH=.` trong môi trường hr-backend; không cần migration/dependency mới. Các kiểm tra liên quan: `python -B -m pytest tests/unit/test_ai_service.py tests/unit/test_report_service.py tests/unit/test_ai_report_draft.py -q`. Browser fixture: từ repo chạy `node frontend/scripts/check_ai_chat_layout.mjs` và `node frontend/scripts/check_chat_report.mjs` sau `npm run build` tại frontend; dùng Edge đã cài, tài khoản/API giả cục bộ, không phải kiểm thử PostgreSQL hoặc Gemini thật.


Kiểm tra hồi quy chat/RAG/PDF bằng môi trường Conda `hr-backend`, tại `backend/`: `python -B -m pytest tests/unit/test_knowledge_storage.py tests/unit/test_ai_core.py tests/unit/test_ai_service.py -q`. Các test này dùng PDF tạo trong bộ nhớ, DB mock và Gemini mock/tắt; không cần DB test hoặc API key thật. Giới hạn phản hồi/lịch sử là 8.000 ký tự, câu hỏi mới 2.000 ký tự; không cần migration hoặc dependency mới cho các điều chỉnh này.

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

### Seed fails because hr_qr_cards.card_code is missing

In Anaconda Prompt, activate `conda activate hr-backend` and enter backend/. Run `alembic upgrade head` to apply migration `e0f1a2b3c4d5`, then `python -m app.scripts.seed_data`. Log in after seed completes successfully. No Docker volume deletion is needed. Failed seed rolls back new records; rerunning seed does not reset existing account passwords. Offline SQL generation has passed; migration and seed execution against a real development/test DB remain unverified.


## Kiểm tra flow AI chatbox

Không thêm dependency/migration cho interpreter, preview chat hoặc upload một bước. Các bảng knowledge/version/section/draft/report/audit vẫn cần migrations đã mô tả ở trên. Restart backend và build frontend sau cập nhật. Key ở biến môi trường, không đưa vào repo. GEMINI_ENABLED=false vẫn hỗ trợ lệnh mẫu/ngày/filter phổ biến/DB/template; câu khó cần provider được cấu hình.

Phân tích AI cần pandas>=2.2,<4, numpy>=1.26,<3 và matplotlib>=3.9,<4 trong chính Conda hr-backend (đã khai báo requirements.txt). `matplotlib.pyplot` là module của matplotlib, không phải package riêng. Backend render bằng Agg, không cần GUI hay seed mới; migration audit được mô tả bên dưới. Restart backend và build/reload frontend; MANAGER/HR/ADMIN tạo báo cáo từ chat rồi chọn “Phân tích & biểu đồ”, hoặc hỏi “phân tích báo cáo này”. Test tập trung: `python -B -m pytest tests/unit/test_ai_analysis_tool.py tests/unit/test_ai_report_draft.py tests/unit/test_ai_service.py -q` tại backend; `npm run build` tại frontend. Unit tests không chứng minh Gemini thật/DB thật.

Phân tích cần migration audit `0a1b2c3d4e5f` (head sau merge `f1a2b3c4d5e6`): từ root chạy interpreter hr-backend với `-B -m alembic -c backend/alembic.ini upgrade head`, rồi restart backend/reload frontend. Migration giữ dữ liệu audit và thêm REPORT_ANALYSIS vào CHECK constraint; đã áp dụng trên PostgreSQL development và kiểm tra snapshot HR tạo PNG thành công. Không cần seed lại. Test thêm `tests/unit/test_report_permissions.py` và `tests/unit/test_ai_error_envelopes.py`; EMPLOYEE bị 403 ở mọi endpoint report, prompt mẫu không có report, HR/manager giữ phạm vi được cấp. Ma trận ở [AI_PROMPT_PERMISSIONS](AI_PROMPT_PERMISSIONS.md).

Cập nhật biểu đồ theo nghiệp vụ không cần migration/seed/dependency mới: restart backend và bấm lại “Phân tích & biểu đồ” trên snapshot hiện có. HEADCOUNT hiển thị số người theo phòng ban/trạng thái thay vì Min/Median/Mean/Max; kiểm thử hồi quy trong `tests/unit/test_ai_analysis_tool.py` bao gồm số người, tổng nhóm còn lại, đơn vị ngày công và không gộp tiền khác currency.

Kho tài liệu: restart backend/reload frontend để có xem/tải PDF lưu trữ, đổi tên, lọc người đọc và khôi phục. Khôi phục tạo version nháp từ PDF/mapping cũ, không cần upload lại; phiên bản cũ giữ lịch sử. Mở “Phiên bản PDF” → “Kiểm tra & công bố”, kiểm tên/quyền/hiệu lực/mục cho AI, mở PDF ở tab riêng rồi công bố. Tài liệu văn bản không có PDF: khôi phục về DRAFT, sửa thông tin văn bản rồi công bố theo luồng legacy. Mapping heading tự động mới chỉ áp dụng upload mới; dùng chỉnh bản nháp để sửa mapping đã có. Không seed/publish tự động.

Kiểm thử luồng chính sách: sau công bố tài liệu được phép dùng, đăng nhập employee hỏi “Chính sách nghỉ phép như thế nào?” hoặc “Quy trình tạo đơn nghỉ phép là gì?”. Chat phải trả đoạn nguồn và liên kết “Xem đúng mục”, không tạo draft đơn; mở link phải đúng trang/heading và không có token trong URL. Draft/archive/hết hiệu lực/mục is_answerable=false không được RAG dùng. Unit regression: tại backend chạy `python -B -m pytest tests/unit/test_ai_api.py tests/unit/test_ai_service.py tests/unit/test_ai_analysis_tool.py tests/unit/test_ai_analysis_dispatch.py -q`; frontend `npm run build`. Build/unit không chứng minh browser hoặc Gemini thật; không tự công bố tài liệu demo để vượt kiểm tra.

Cách công bố ngắn nhất cho PDF nháp: từ list bấm **Kiểm tra & công bố** → kiểm thông tin/nguồn → **Công bố vN**. Không cần mở lịch sử phiên bản trước. Với tài liệu đã công bố và có draft thay thế, dùng menu “Kiểm tra phiên bản nháp mới”.

Trả lời chính sách động: bật GEMINI_ENABLED/key/model ở backend; GEMINI_POLICY_TIMEOUT_SECONDS mặc định 15, cho phép 5–30 giây, riêng với intent và adapter ngày/filter. Provider lỗi vẫn trả excerpt ngắn kèm nguồn. Từ backend chạy `python -B scripts/check_ai_policy_prompts.py` để kiểm Gemini thật với hai chính sách giả lập, không dùng DB hoặc in secret; đã kiểm trả GEMINI/citation cả hai. Script dùng quota provider, kết quả không bảo đảm uptime/quota tương lai. Unit `test_ai_policy_answer.py` kiểm diễn giải động, nguồn giả, evidence giả, số liệu bịa và fallback không dán cover PDF. Khi test chỉ kiểm handler/RAG, tắt Gemini trong fixture hoặc mock provider rõ ràng để không phụ thuộc key thật từ .env. Nội dung PDF demo còn chữ dự thảo thì câu trả lời phải nói rõ chưa được xác nhận, không khẳng định số liệu minh họa là chính sách có hiệu lực.

Gemini nhận intent dùng `GEMINI_INTENT_TIMEOUT_SECONDS=15` mặc định (cho phép 5–30), response JSON/schema enum và 512 token. Adapter ngày/filter báo cáo/policy vẫn 5s. Dùng `python -B scripts/check_ai_analysis_prompts.py` tại backend để kiểm tra 4 intent với Gemini thật khi GEMINI_ENABLED=true và cấu hình key/model hợp lệ. Script gửi prompt giả lập, không đọc DB và chỉ in intent/loại lỗi; các lời gọi dùng quota của provider. SDK google.generativeai đã ngừng hỗ trợ theo cảnh báo runtime; chưa chuyển SDK trong thay đổi này.

Trên DB development/test đã xác định:
1. EMPLOYEE hỏi số dư phép, so với DB; mở citation published phù hợp nếu có. DRAFT/ARCHIVED hoặc trái quyền không xuất hiện.
2. “Tạo phép năm cho tôi thứ 3 tuần sau”: giữ ngày, hỏi phần thiếu. Thử số dư 0/0,5; cảnh báo/chọn loại khác hoặc nửa ngày phù hợp. Không tự đổi loại, không gửi đơn từ chat.
3. Hỏi công bản thân tháng trước; chỉ dữ liệu JWT và kỳ đã chọn. Không suy diễn ngày không có record thành vắng.
4. Tạo báo cáo công trong chat, preview/tải Excel cùng snapshot. Chỉnh qua chat sang tháng trước tạo run mới. Thử scope trái quyền/run người khác/hết hạn.
5. HR kéo nhiều PDF và lưu nháp; mỗi file tạo tài liệu riêng. Kiểm kết quả từng file, thử lại chỉ file lỗi; kiểm preview v1 rồi công bố. Tải file mới thành v2, v1 vẫn được dùng tới khi công bố bản thay thế. Quyền hạn chế là tùy chọn. Mỗi PDF tối đa 10 MiB/100 trang; scan cần OCR, bản có mật khẩu/nội dung tương tác bị từ chối.

Upload nhiều file không cần dependency/migration mới. Frontend tại `frontend/`: `node scripts/check_upload_transport.mjs` kiểm transport multipart (boundary, file, quyền) và JSON bằng HTTP receiver local; `node scripts/check_knowledge_layout.mjs` sau build kiểm chọn hai file, lỗi một file và retry không tải lại file thành công bằng Edge/API fixture. Backend: `python -B -m pytest tests/unit/test_pdf_error_messages.py tests/unit/test_knowledge_storage.py -q`. Những kiểm tra này đã đạt; không chứng minh ghi dữ liệu trên DB thật. Restart backend để nhận thông báo PDF mới và reload frontend sau build.

Kiểm tra không dùng DB thật: tại backend, dùng interpreter hr-backend chạy python -B -m pytest tests/unit/test_ai_service.py tests/unit/test_ai_report_draft.py tests/unit/test_ai_api.py tests/unit/test_ai_core.py tests/unit/test_knowledge_storage.py tests/unit/test_report_service.py -q. Tests mock session/provider, kiểm schema, owner/scope, số dư/citation/PDF/template. Frontend: npm run build; Windows có Edge chạy node scripts/check_ai_chat_layout.mjs, node scripts/check_chat_report.mjs và node scripts/check_knowledge_layout.mjs sau build. Browser fixture local kiểm viewport/preview/edit context, không chứng minh SQL thực thi hoặc Gemini thật. Các kịch bản DB ở trên cần nghiệm thu tích hợp riêng. Hồi quy report draft bao phủ payroll kind từ dispatch; fixture check_chat_report.mjs kiểm chuyển từ trang 3 của snapshot cũ về trang 1 của snapshot mới.

Khi kiểm tra fallback với GEMINI_ENABLED=false, thử “thông tin ngày nghỉ của tôi”, “tôi còn bao nhiêu ngày nghỉ”, “còn mấy ngày phép”; phải trả số dư từ DB. Trong Chỉnh qua chat thử “đổi sang tháng sau/tháng tới”: kỳ là trọn tháng kế tiếp tính từ today HCM. Báo cáo chỉ có dữ liệu đã ghi nhận; lương chưa phát hành vẫn bị từ chối theo quy tắc hiện có. Kiểm tra hồi quy: python -B -m pytest tests/unit/test_ai_service.py tests/unit/test_ai_report_draft.py -q tại backend.
