# Đối chiếu nghiệm thu AI Copilot

Đối chiếu phạm vi công cụ và luồng hiện tại trong [AI Copilot](AI_COPILOT.md). Có code, unit test hoặc UI fixture chưa đồng nghĩa hoàn thành DB integration. Không có mục nào được coi đã nghiệm thu toàn bộ nếu còn thiếu bằng chứng trong cột cuối.

## Tasks T01–T16

| Task | Code/artifact hiện có | Bằng chứng phù hợp và phần còn thiếu |
|---|---|---|
| T01 | schemas/ai.py, schemas/reports.py; frontend/types/ai.ts, reports.ts | Schema/action tests và frontend build; cần round-trip với API thực |
| T02 | ai_access.py, report_service.py, catalog | Role/scope tests và SQL compile; cần SQL trên fixture hai manager/nhân viên ngoài scope |
| T03 | leave/attendance services, view=approvals, form tabs | Test cấm tự duyệt/bypass ADMIN; cần DB reassignment/event và thao tác UI |
| T04 | migrations a1b2c3d4e5f6 → b7c8d9e0f1a2 → c8d9e0f1a2b3 → d9e0f1a2b3c4 | SQL offline/model checks; chưa upgrade/backfill/constraint trên DB test |
| T05 | knowledge.py, knowledge_storage.py, DRAFT editor/preview | Parser/path/role/immutable tests; cần upload/publish/commit failure với DB thực |
| T06 | 3 PDF + manifest, docs/knowledge-drafts, generator/seed | Page/hash/parser/outline và visual viewer; chưa seed hai lần trên DB riêng |
| T07 | lexical section retrieval + closed quotes/citations | Mock provider/source tests; cần published/effective/revoked DB sources |
| T08 | KnowledgePage/KnowledgeViewerPage, local PDF worker | Edge đã render 3 PDF đúng heading và denied message với API fixture; chưa thử 2 version/revoke trên backend thật |
| T09 | registry/default_inputs, owner/revision/TTL draft, report collection | Unit/schema tests; cần draft persistence/concurrency với DB |
| T10 | typed chat actions, shortcuts, fixed errors, login notice | Build; viewer fixture có Bearer header, không token URL. Cần dirty form/cùng trang/logout/offline tương tác |
| T11 | 5 report queries + catalog fixed columns/scopes | Query compile/role/limit/empty tests; chưa SQL thật |
| T12 | 7 XLSX templates, private run lifecycle/snapshot/cleanup | Workbook readback, FAILED/expiry/orphan tests; cần DB commit/read/download/cleanup thực |
| T13 | ReportsPage và fallback chat tạo actual run_id | Service tests/typed UI/build; cần chat → run → preview → file bằng DB/backend thật |
| T14 | enum intent/quotes, timeout/fallback, minimal provider payload | Provider mocks; không dùng live model để chứng minh quyền. Cần fault injection nối với API thực |
| T15 | 2 payroll reports, released status, currency snapshot/totals | Decimal/currency/status tests; cần migration, legacy currency verification và SQL payroll fixtures |
| T16 | Unit/API tests và browser viewer harness | Chưa đạt: DB test không kết nối được, chưa có bộ integration đầy đủ/multi-process và browser flows thực |

Các tên backend ở bảng trên thuộc `backend/app/`, migrations thuộc `backend/alembic/versions/`; tests ở `backend/tests/unit/`. UI thuộc `frontend/src/`. Endpoint upload tạo version + PDF + section nguyên tử bằng `POST /ai/knowledge/{id}/versions` multipart; không tạo version rỗng rồi upload riêng. Đây là hợp đồng hiện thực được ghi trong SETUP_GUIDE/API, vẫn giữ lifecycle upload → preview → publish/archive.

## Acceptance A01–A25

| ID | Evidence hiện có | Chưa chứng minh |
|---|---|---|
| A01 | test_ai_service: lookup/draft fallback không provider | Dữ liệu JWT owner trên DB |
| A02 | foreign/company denial trước lookup; typed scope checks | Query thực không trả hàng ngoài scope |
| A03 | report query compile giao manager/department/frozen IDs | Rows và aggregate trên DB hai phòng ban |
| A04 | direct-manager/self-review tests | Mutation/event DB và HR là manager hợp lệ |
| A05 | approvals SQL filter PENDING/current manager | Reassignment trên DB và tab browser |
| A06 | API role/version/section/preview tests | DB objects thật và file authorization thật |
| A07 | Lifecycle read predicates/published immutable | Archive/revoke/đổi version qua API thực |
| A08 | Owner draft/missing-field/revision service tests | Persistence nhiều lượt, không submit trong browser |
| A09 | Owner/TTL/revision/schema tests; HTTP envelope | Hai request đồng thời trên DB |
| A10 | Provider timeout/key/ungrounded fallback mocks | API fault injection và exact message trên browser |
| A11 | Safe exception envelope, FAILED artifact tests | DB disconnected trong luồng thực; browser offline |
| A12 | NULL balance/empty scoped query và empty template | Query thành công rỗng trên DB thật |
| A13 | Actual run_id service path; workbook/snapshot creation | Preview/file same run trên DB và browser |
| A14 | Formula/control-char sanitizer và XLSX readback | Các field dữ liệu fixture DB qua export endpoint |
| A15 | Decimal lớn chính xác; USD/VND rows và Excel totals tách | Currency migration/fixtures SQL thật; legacy review |
| A16 | Owner predicate và frozen/current scope tests | Đổi manager/role rồi download thật |
| A17 | Route/action allowlist, dirty-form confirms trong code | Click shortcut cùng/khác trang và giữ dữ liệu form |
| A18 | Edge viewer 3 PDF + heading highlight; API source mapping | Click reference không chat, refresh, 2 version và backend thật |
| A19 | Closed enum/schema; no model SQL/URL execution path | Provider capture + injection qua API thực |
| A20 | Quote exact substring/source permission validation | Published/revoked source rows thực |
| A21 | Unknown role denied, user-keyed chat reset, typed action | Login đổi user/multi-role và file reuse trong browser |
| A22 | Invalid/encrypted/active/oversize PDF parser tests | Multipart upload và IO/commit failure với DB |
| A23 | Limit/FAILED/expiry/dry-run orphan logic tests | DB commit fault, retention job và >10k SQL rows |
| A24 | APPROVED/CLOSED rule và manager summary denied | Direct URL/legacy export trên payroll DB fixtures |
| A25 | README/ARCHITECTURE/SETUP được cập nhật cùng features | Rà lại lệnh/flow sau khi có DB integration evidence |

## Môi trường cần để hoàn tất

- PostgreSQL test riêng có tên/DSN xác định, có quyền migration và dữ liệu fixture tách biệt. Không dùng DB hiện hữu chưa xác định để chạy suite ghi dữ liệu.
- Upgrade head; seed PDF hai lần; fixture đủ hai manager, nhân viên ngoài scope, HR/ADMIN và payroll statuses/currencies; kiểm SQL, draft/run, publish/archive, file revoke và budget nhiều process.
- Chạy backend/frontend trên DB đó rồi nghiệm thu shortcuts/dirty form/offline/logout/report flows. Viewer fixture không thay authorization thật.
- Native Edge harness ở `frontend/scripts/check_ai_viewer.mjs` dùng build/PDF thật và API fixture cục bộ, không cài dependency. Chạy sau `npm run build`; không dùng nó làm fallback production. Artifacts browser ở thư mục validation đã gitignore, không đưa profile/ảnh tạm vào source control.

Hiện PostgreSQL local từ chối kết nối và Docker/psql không có trong PATH. Chưa đạt gate hoàn thành toàn plan; không đánh dấu T16 hoặc toàn bộ A01–A25 đã xong.
