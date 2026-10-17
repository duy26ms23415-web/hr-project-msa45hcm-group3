# Enterprise HR AI Copilot

## Sử dụng

Câu tự do được giải nghĩa bằng Gemini khi bật `GEMINI_ENABLED=true` và `GEMINI_SEMANTIC_ENABLED=true`. Backend kiểm quyền, danh tính và phạm vi trước khi truy vấn dữ liệu; kết quả model không được cấp quyền hoặc tự thực thi SQL. Nếu provider lỗi, yêu cầu cần suy luận trả `UNAVAILABLE`, không tự chuyển sang hồ sơ người dùng.

Câu hỏi chính sách ưu tiên tài liệu nội bộ đã công bố và lọc quyền. Google Search grounding (nếu bật `GEMINI_PUBLIC_SEARCH_ENABLED`) chỉ được dùng khi thiếu bằng chứng phù hợp; nguồn công khai phải qua kiểm tra URL chính thức. Không gửi hồ sơ nhân viên hoặc lịch sử hội thoại cho provider.

- Nháp follow-up bắt buộc có draft_id/draft_revision; có thể gửi inputs có kiểu mà không thêm message giả. Báo cáo tự do hỏi loại/kỳ/phạm vi theo quyền qua DRAFT_REPORT, sau đó tạo run thật. Gợi ý mẫu giữ mặc định minh bạch.
- Lỗi AI/knowledge/reports trả code/message/request_id với action null; ID server khớp audit. Tham khảo gợi ý trỏ đúng LEAVE.REQUEST/REPORT.CATALOG/REPORT.ACCESS. PDF demo có mục lục/bookmarks/số trang và bản Markdown trong `docs/knowledge-drafts`.

- Chatbot lấy số dư phép năm và bản ghi công trong tháng theo danh tính JWT, ngày nghiệp vụ `Asia/Ho_Chi_Minh`. Không có số dư được báo là chưa có dữ liệu.
- Ví dụ: `Tôi còn bao nhiêu ngày phép?`, `Các ngày thiếu công của tôi?`, `Xin nghỉ sáng mai`, `Xin nghỉ Thứ Sáu tuần này`, `Quên check-out hôm qua lúc 17h`.
- Quick Action Cards truyền nháp vào form nghỉ phép/giải trình. Người dùng kiểm tra và gửi bằng API nghiệp vụ hiện có. Không có thao tác ghi dữ liệu từ LLM. Không tự đổi phép năm sang không lương; không đoán ngày hoặc giờ chấm công khi thiếu thông tin.
- Nếu thiếu ngày/buổi/loại/lý do/giờ, backend giữ draft owner-bound trong tối đa 15 phút và chatbot hỏi từng trường còn thiếu. Request follow-up chỉ gửi opaque `draft_id`; server đọc owner từ JWT, khóa row và chỉ cập nhật key theo command allowlist. Có thể hủy bằng “hủy bản nháp”. Draft hết hạn trả mã ổn định `AI_DRAFT_EXPIRED`; draft của user khác trả 404 chung.
- Câu hỏi nội quy dùng tối đa ba truy vấn ngữ nghĩa do Gemini diễn đạt lại trên tài liệu PUBLISHED đã lọc quyền, kết hợp câu gốc. Câu trả lời nội bộ vẫn phải có evidence nguyên văn và số liệu được kiểm tra. Khi không có/không đủ bằng chứng, `GEMINI_PUBLIC_SEARCH_ENABLED=true` cho phép tra luật/chính sách lao động công khai bằng Google Search; không gắn PDF không liên quan vào câu trả lời thiếu căn cứ.
- Gemini phân loại câu tự do vào enum đóng và target trước handler, không dựa cổng từ khóa HR để quyết định có gọi mô hình. Backend vẫn quyết định identity, quyền và thao tác. Thông tin liên hệ được che trước giải nghĩa; câu hỏi có “lý do” được giữ đầy đủ, tên/mã người được hỏi được giữ để resolve ở backend. Tra cứu không nhắc ai khác được hiểu là của người đang hỏi; câu có dấu hiệu người khác (mã NV, họ tên, “đồng nghiệp”, “bạn ấy”…) mà model không xác định được thì phải hỏi lại, không tự chuyển sang dữ liệu người đăng nhập. Phạm vi báo cáo không nêu thì luôn hỏi. Lỗi giải nghĩa trả status UNAVAILABLE, mã chẩn đoán AI_INTENT_* và action null; chat chỉ thông báo thử lại dễ hiểu, không nêu nhà cung cấp/hạn mức. Ngoài HR không chạy tool.
- Nguồn tham khảo hiển thị ngay dưới câu trả lời. Mở nguồn gọi lại API kiểm tra quyền và trạng thái tài liệu hiện tại.
- `GET /api/v1/ai/suggestions` trả gợi ý theo role xác thực; câu hỏi chính sách chỉ có khi PDF tương ứng đang được công bố, còn hiệu lực và user có quyền đọc. Reference gắn section/trang mở viewer PDF có xác thực.
- Báo cáo tạo bằng ReportRun ngay trong chat; thông tin thiếu được hỏi thêm. AI không gửi/duyệt đơn hoặc chạy SQL; bản nháp mở form nghiệp vụ để người dùng kiểm tra và gửi.

## Xử lý PDF động và Hybrid RAG

- **Tách cấu trúc tự động** (`services/knowledge_ingest/`), không cấu hình theo từng tài liệu. Thứ tự ưu tiên: bookmark của PDF → mục lục in ("Mục lục"/"Contents", dòng có dấu chấm dẫn + số trang) → định dạng (cỡ chữ lớn, chữ đậm, chữ in hoa) → mẫu đánh số (`Chương/Phần/Mục/Điều`, `I.`, `1.`, `1.2`, `a)`) → theo từng trang. Header/footer lặp và số trang bị loại.
- **Mục lục in:** số trang in được hiệu chỉnh độ lệch so với trang PDF (bìa, trang La Mã) bằng cách dò heading trong thân bài; mỗi mục phải tìm lại được trong khoảng ±2 trang, mục lục có dưới 50% mục xác minh được bị bỏ qua. Trang mục lục luôn bị loại khỏi nội dung để AI không trích nhầm dòng mục lục.
- Mỗi section là nội dung từ heading đến heading kế tiếp (xuyên trang, không lặp nội dung), có `level` và `heading_path` (ví dụ `Chương II > Điều 5`). HR vẫn sửa được danh sách mục; nội dung được cắt lại theo các heading đã sửa.
- **Gemini fallback** (`GEMINI_PDF_STRUCTURE_ENABLED`, mặc định tắt): PDF scan (không có lớp chữ) hoặc không nhận ra heading nào được gửi cho Gemini. Với PDF có chữ, Gemini chỉ đề xuất heading; nội dung vẫn cắt nguyên văn từ PDF và heading do model bịa (không có trong PDF) bị loại. Với PDF scan, bản chép của Gemini thành nội dung (`GEMINI_OCR`).
- **Chunk:** khoảng 900 ký tự, chồng lấn 150, cắt theo câu và không cắt giữa số; luôn là đoạn nguyên văn của section để kiểm tra evidence. Mỗi chunk có ngữ cảnh `Tên tài liệu > heading_path` dùng khi embed.
- **Lập chỉ mục:** bản nháp có chunk từ khóa ngay khi upload; khi công bố thêm nhãn quy định và embedding. Bảng `hr_ai_knowledge_chunks` có `embedding vector(768)` (pgvector, HNSW cosine), `search_tsv` (full-text) và trigram trên văn bản bỏ dấu. `index_status`: `PENDING`, `READY` (vector + từ khóa), `LEXICAL_ONLY` (embedding tắt/lỗi, vẫn tìm được), `FAILED`.
- **Embedding** (`GEMINI_EMBEDDINGS_ENABLED`, mặc định tắt): `gemini-embedding-001`, 768 chiều, đã chuẩn hóa L2. Chỉ embed nội dung tài liệu (vốn đã gửi Gemini khi trả lời) và câu hỏi đã che email/SĐT/tên/mã NV; không embed dữ liệu nhân viên.
- **Truy xuất hybrid** (`services/knowledge_search.py`): ba nhánh SQL (vector, full-text, trigram chịu lỗi gõ), mỗi nhánh đã có điều kiện quyền/PUBLISHED/hiệu lực trong câu SQL; hợp nhất bằng Reciprocal Rank Fusion, mỗi section trích một lần. Kết quả chỉ có từ full-text phải trùng ≥35% từ khóa. Embedding lỗi thì chỉ dùng hai nhánh từ khóa. Tài liệu chưa có chunk (legacy, chưa reindex) dùng RAG từ khóa cũ.
- **Nhãn quy định** (`GEMINI_KNOWLEDGE_TAGGING_ENABLED`, mặc định tắt): mỗi chunk được gắn `rule_type` (`PROHIBITION/OBLIGATION/PERMISSION/PROCEDURE/INFO`) và `applies_to` (`LEAVE/REMOTE/ATTENDANCE/ATTENDANCE_FIX/PAYROLL/REPORT/CONDUCT/GENERAL`). Nhãn chỉ dùng để xếp hạng và cảnh báo, không cấp hay chặn quyền.
- **Một phiên bản được công bố:** mỗi tài liệu có tối đa một version `PUBLISHED` (unique index một phần trong DB). Công bố bản mới hoặc **Công bố bản này** (version `ARCHIVED`, kiểm tra lại hash và heading) tự chuyển bản đang dùng sang `ARCHIVED`; **Ngừng công bố** đưa tài liệu về `DRAFT` để AI và người đọc ngừng dùng ngay, các phiên bản vẫn giữ để công bố lại.
- Lập chỉ mục lại: nút **Lập chỉ mục lại** ở danh sách phiên bản, `POST /api/v1/ai/knowledge/{id}/versions/{vid}/reindex`, hoặc `python -B -m scripts.reindex_knowledge` (dry-run; `--apply`, `--only-missing`).

## Intent → hành động

Trọng tâm của chatbox là hiểu đúng người dùng muốn **làm gì**, rồi chạy đúng một hành động.

- **Catalog hành động** (`ai/actions.py`) là nguồn duy nhất: mỗi hành động có tên, một câu mô tả mục đích và tham số có kiểu. Hiện có: trả lời chính sách, xem số dư phép, xem chấm công, xem tình trạng đơn của tôi, xem lương của tôi, mở hàng chờ duyệt, soạn đơn nghỉ/WFH, soạn giải trình công, tạo báo cáo Excel, phân tích/vẽ biểu đồ, mở quản lý tài liệu, hỏi lại khi mơ hồ, từ chối ngoài phạm vi; thêm “hủy form” khi đang có form mở.
- **Hiểu ngữ nghĩa bằng Gemini function calling** (`ai/understanding.py`): mỗi tin nhắn một lần gọi, model chọn hàm theo *nghĩa* của câu (không dấu, teencode, gián tiếp, Anh–Việt) với instruction ngắn, không có danh sách câu ví dụ. Câu nhiều ý trả nhiều lời gọi hàm. Payload chỉ gồm tin nhắn đã che email/SĐT, ngày hôm nay và context enum (`previous_action`, `open_form`, `waiting_for`); không gửi lịch sử, dữ liệu nhân viên hay danh tính.
- **Kiểm tra trước khi chạy** (`ai/parsing/intent.py` → `ChatPlan`, `ai/semantic_router.py`): tên hàm lạ hoặc tham số sai schema bị bỏ; ngày do model chép nguyên văn được resolver tất định giải; danh tính/phạm vi lấy từ JWT; quyền và quy tắc nghiệp vụ kiểm lại ở service. Phép năm chỉ được điền khi người dùng nêu rõ.
- **Lock-in form:** khi đang soạn đơn nghỉ/giải trình/báo cáo, mọi tin nhắn được đọc là câu trả lời cho form. Câu trả lời ngắn khớp trường đang hỏi đi đường tất định (không gọi model); câu khác được hiểu với form làm context: điền/sửa trường (“thôi để chiều”), hỏi phụ được trả lời mà vẫn giữ form (“à mà còn mấy ngày phép?”), hành động ghi khác thì yêu cầu hoàn tất hoặc “hủy” trước, câu hủy tự nhiên (“thôi khỏi làm đơn”) hủy form.
- **Biểu đồ:** “vẽ biểu đồ/thống kê…” mở draft báo cáo với `purpose=ANALYZE`; khi đủ loại/kỳ/phạm vi, chat trả luôn phân tích và biểu đồ của run vừa tạo.
- **Follow-up:** “còn tháng trước thì sao?”, “còn bạn ấy?” dùng `previous_action` và state enum (`hr_ai_conversation_states`, TTL 30 phút); nhân viên cũ lấy từ state server và kiểm lại phạm vi. SELF kế thừa từ lượt trước chỉ dùng khi câu không nêu chủ thể mới.
- Mơ hồ: không chạy tool, trả `INTENT_CONFIRMATION_REQUIRED`/`CLARIFICATION_REQUIRED` với lựa chọn do server viết. Provider lỗi: `UNAVAILABLE` + `AI_INTENT_*`, giữ nguyên form đang mở, không đoán.
- **Đo lường:** `backend/scripts/ai_eval/eval_intent.py` chấm riêng bước hiểu intent trên bộ có nhãn (`intent_dev.json` để tinh chỉnh; `intent_test.json`, `intent_test2.json` giữ riêng). Thêm hành động mới = thêm một mục catalog + handler + vài câu nhãn vào bộ eval; không thêm câu ví dụ vào prompt.
- Nhánh rule (Gemini/semantic tắt, gợi ý có sẵn, report run) vẫn dùng `ai/parsing/lexicon.canonical` và từ khóa làm đường dự phòng.

## Nghiệp vụ và điều cấm trong tài liệu

- Quy tắc trong code (thiếu phép, kỳ lương `CLOSED`, chỉ quản lý trực tiếp duyệt, không tự duyệt, quyền theo JWT) luôn có hiệu lực cuối; tài liệu không nới hay ghi đè.
- Câu hỏi "có được…không/nếu…thì sao" ưu tiên đoạn có nhãn quy định; câu trả lời phải nói rõ được/không được/có điều kiện kèm trích dẫn, không có căn cứ thì báo chưa có quy định.
- Khi bản nháp nghỉ/giải trình sẵn sàng, `services/ai_policy_guard.py` đối chiếu dữ kiện đã che (loại nghỉ, số ngày báo trước, buổi, thứ, số ngày kể từ ngày cần giải trình — không tên, mã NV hay lý do) với các đoạn `PROHIBITION/OBLIGATION` cùng lĩnh vực. Phát hiện chỉ được giữ khi evidence là trích nguyên văn và không có số bịa. Kết quả là `policy_warnings` hiển thị trong thẻ nháp: **chỉ cảnh báo, không chặn**; người dùng tự quyết gửi, quản lý trực tiếp quyết định. Provider lỗi thì báo "chưa kiểm tra được quy định", bản nháp vẫn tạo.
- Yêu cầu thao tác AI không làm được (tự duyệt, sửa/xóa chấm công, chấm công hộ) bị từ chối với `ACTION_NOT_PERMITTED`, kèm trích dẫn điều cấm nếu có.

## Kiến thức và quyền

- ADMIN/HR quản lý tài liệu tại `/knowledge`: PDF versioned riêng tư, section/page đã kiểm tra, trạng thái `DRAFT`/`PUBLISHED`/`ARCHIVED` và quyền tối thiểu; legacy text được giữ tương thích.
- Mức đọc kiến thức: `EMPLOYEE < MANAGER < HR < ADMIN`; nhiều vai trò dùng mức cao nhất. HR không đọc, sửa hoặc công bố tài liệu mức ADMIN. Vai trò không biết không được truy xuất kiến thức.
- Chỉ `PUBLISHED` được dùng trong chat; bộ lọc quyền chạy tại SQL trước khi retrieval và trước khi gửi dữ liệu sang Gemini. Lịch sử hội thoại là dữ liệu không đáng tin, chỉ nhận role user/assistant. Client không cấp quyền hoặc chọn danh tính cho copilot.
- Có ba PDF demo trong `backend/storage/tmp/ai-knowledge-demo`; chúng là bản nháp minh họa, chưa được công ty thông qua. Script seed chỉ development/test, cần xác nhận tường minh và tạo DRAFT.
- API: `GET/POST /api/v1/ai/knowledge`, `GET/PUT /api/v1/ai/knowledge/{document_id}`, `POST /api/v1/ai/chat`.

## Báo cáo

Quyền AI Chatbox có thể bị giới hạn thêm tại `GET/PUT /api/v1/ai/access/roles` (chỉ ADMIN sửa), nhưng không thể vượt quyền HR gốc. Chạy migration `c4d5e6f70819` bằng `alembic upgrade head` trước khi triển khai backend mới.

- `/reports` tạo ATTENDANCE, LEAVE, ATTENDANCE_FIX, APPROVAL_QUEUE, HEADCOUNT, MY_PAYSLIP và PAYROLL_SUMMARY theo kỳ/phạm vi được backend cho phép; JSON/CSV/XLSX dùng cùng scope. Bảy file template v1 có sheet thông tin/dữ liệu/tổng hợp; tiền vượt 15 chữ số lưu text chính xác. Giới hạn 10.000 dòng, không truncate. GET legacy có XLSX trực tiếp; UI dùng ReportRun snapshot/TTL.
- ReportRun API tạo bản xem trước và workbook private có TTL một giờ. Chỉ chủ sở hữu xem/tải; lúc đọc và tải backend kiểm tra hạn dùng, phân quyền hiện tại và các nhân viên trong scope snapshot. Script cleanup đánh dấu hết hạn và xóa artifact private đã liên kết.
- Chỉnh run hoặc draft báo cáo: scope được nêu lại thay thế employee filter cũ, kể cả COMPANY → COMPANY; đổi sang kind không hỗ trợ employee cũng bỏ filter cũ. Đổi kỳ hoặc kind tương thích vẫn giữ nhân viên. Filter mới luôn được validation và kiểm scope; không nới quyền khi đổi loại/phạm vi.
- EMPLOYEE được tạo/xem/xuất/phân tích báo cáo SELF khi catalog cho phép, nhưng không được dùng HEADCOUNT, APPROVAL_QUEUE hoặc PAYROLL_SUMMARY. MANAGER dùng SELF/DIRECT_REPORTS cho báo cáo được cấp; HR/ADMIN thêm COMPANY. Phiếu lương report chỉ SELF cho các role được quyền report, tổng hợp lương chỉ HR/ADMIN và không tính lại PayrollLine snapshot. Kỳ trọn tháng APPROVED/CLOSED, tổng tách mã tiền tệ; legacy chưa xác minh bị từ chối. Gợi ý/chat/API kiểm cùng quyền; [ma trận prompt](AI_PROMPT_PERMISSIONS.md). Audit phân tích cần migration 0a1b2c3d4e5f.
- Công chỉ đếm các trạng thái/bản ghi đã lưu, không suy diễn ngày thiếu bản ghi hoặc kết quả chốt lương. Ngày phép được duyệt gồm tất cả loại phép trong kỳ. Số dư phép năm là số dư hiện tại của năm được chọn, không phải số dư lịch sử tại cuối kỳ.
- API: `GET /api/v1/reports?kind=ATTENDANCE&start_date=2026-10-01&end_date=2026-10-31&output=json`; `output=csv` để tải file.

## Thiết lập và kiểm tra

- **Xoay vòng model:** `GEMINI_MODEL_POOL` (ví dụ `gemini-3.5-flash-lite,gemini-3.1-flash-lite`) chia các lần gọi sinh văn bản (hiểu intent, trả lời chính sách, đối chiếu quy định, tra cứu công khai) round-robin giữa các model để dùng quota/phút riêng của từng model (free tier Flash Lite: 15 RPM, 500 RPD mỗi model). Mỗi process đếm số lần gọi từng model trong 60 giây và ưu tiên model ít dùng nhất, bỏ qua model đã chạm `GEMINI_MODEL_RPM` (mặc định 15) trước khi bị 429. Model vẫn trả 429 được nghỉ 60 giây và yêu cầu đó chuyển ngay sang model kế tiếp; model không tồn tại (404) cũng được bỏ qua. Để trống thì chỉ dùng `GEMINI_MODEL_NAME`. Embedding dùng `GEMINI_EMBEDDING_MODEL` riêng. Trạng thái nghỉ nằm trong từng process.
- Dependencies PDF/generator/viewer có trong manifest/lock; xem SETUP_GUIDE. Gemini sử dụng provider và cấu hình đã có; không cần API key để chạy rule/RAG fallback.
- Migration `4e5f6a7b8c93` cần extension `vector` (image `pgvector/pgvector:pg16` trong docker-compose) và `pg_trgm`; nó thêm `hr_ai_knowledge_chunks`, `hr_ai_conversation_states` và các cột section/version mới. Nếu container cũ dùng `postgres:16-alpine`, đổi image rồi chạy lại `alembic upgrade head`, sau đó `python -B -m scripts.reindex_knowledge --apply` để tạo chunk cho tài liệu đã công bố.
- Có migration `a1b2c3d4e5f6` thêm `hr_ai_knowledge_documents`. Tại backend, áp dụng bằng `alembic upgrade head` trong môi trường và DB phù hợp theo SETUP_GUIDE. Không tự chạy migration hoặc seed trên DB chưa xác định.
- Unit/API tests không kết nối DB: trong backend dùng interpreter `hr-backend` chạy `python -B -m pytest --confcutdir=tests/unit tests/unit -q -p no:cacheprovider`. Mock Gemini và session; cần kiểm thử tích hợp trên DB test riêng để xác nhận migration và CRUD thực tế.
- Frontend kiểm tra bằng scripts `npm run build` và `npm run lint`; các trang kiến thức được tải bằng React lazy.
- Bằng chứng/gate chưa hoàn tất ở [AI_ACCEPTANCE](AI_ACCEPTANCE.md); head currency migration là d9e0f1a2b3c4. Edge viewer harness dùng API fixture, không chứng minh SQL authorization.

- Migration `c8d9e0f1a2b3` thêm audit/budget: 20 chat và 5 lần tạo report/tài khoản/phút, advisory lock PostgreSQL dùng chung process. Audit enum metadata, không raw prompt/reason/history. Script `python -B -m scripts.cleanup_ai_audit` dry-run retention 90 ngày; `--apply` mới xóa. SQLAlchemy ẩn bind parameters.
- Unit tests có mock không thay thế việc kiểm tra migration, phân quyền SQL, concurrency và browser acceptance trong staging.


## Mở rộng công cụ trong phạm vi AI

Các lệnh mẫu là capability của cùng chat, không cần tab AI riêng. Xem bảng module/luồng tại [ARCHITECTURE](ARCHITECTURE.md#kiến-trúc-ai-chatbox-và-công-cụ).

Thêm lệnh: khai báo suggestion/điều kiện trong registry, thêm intent đóng nếu cần provider hỗ trợ, dispatch tới service nghiệp vụ có kiểm quyền, mở rộng schema action/validator và UI, rồi kiểm thử trái quyền/fallback. Không cho provider trả SQL, employee IDs, route tùy ý hoặc template path. Giữ Adapter tách khỏi service nghiệp vụ; ReportPromptInterpreter là điểm thay interpreter. Python xử lý dữ liệu/thuật toán xác định, Gemini hỗ trợ nhận dạng ngôn ngữ và chọn tham số trong contract.

Số dư phép/công lấy ORM theo actor, có thể kèm policy citation đã lọc quyền. Không có tài liệu vẫn trả DB, không dựng chính sách. Thiếu số dư được báo sớm; người dùng chọn loại nghỉ và gửi ở form. Hỏi số dư trong lúc soạn giữ state/revision, không biến câu hỏi thành lý do.

Báo cáo preview/download trong chat, không tab báo cáo/lịch sử tải. Chỉnh dùng run owner làm context, tạo snapshot mới. ReportPromptInterpreter chỉ gửi đoạn thời gian đã làm sạch cùng filter/template metadata, không DB rows/history. Kỳ phổ biến chạy Python; lỗi/timeout hỏi phần thiếu. Upload PDF một bước, section theo cấu trúc tài liệu (xem "Xử lý PDF động"), quyền mặc định EMPLOYEE; version DRAFT phải được kiểm tra/công bố trước khi trích nguồn.

Hỏi chính sách ưu tiên trước soạn đơn. Gemini diễn giải động nguồn đã lọc quyền theo JSON statements (source/text/evidence); backend kiểm dẫn chứng và số liệu, route citation do server tạo. Provider lỗi dùng tối đa ba câu liên quan hoàn chỉnh; không dán cover/bảng quản trị PDF. Nội dung ghi dự thảo/chưa xác nhận luôn được nhắc rõ, không coi ví dụ là quy định có hiệu lực. Đây chưa phải kiểm chứng ngữ nghĩa hoàn chỉnh. Timeout policy riêng 15s; hướng dẫn/test ở SETUP_GUIDE. Kho có xem/tải archive cho HR/Admin, đổi nhãn và restore thành draft mới từ file/mapping cũ; công bố có màn review mở trực tiếp từ list.
