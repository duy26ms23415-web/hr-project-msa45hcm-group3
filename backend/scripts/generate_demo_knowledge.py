"""Generate draft-only HR knowledge PDFs and their section manifest.

The documents are examples for local development. They are not adopted company
policy and must be reviewed by HR/legal before publication.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "storage" / "tmp" / "ai-knowledge-demo"
LABOR_CODE_URL = "https://vanban.chinhphu.vn/?classid=0&docid=217002&pageid=27160"

DOCUMENTS = [
    {
        "document_code": "DEMO-LEAVE-POLICY",
        "title": "Bản nháp tham khảo: Nghỉ phép và nghỉ việc riêng",
        "file": "leave-policy-draft.pdf",
        "source_url": LABOR_CODE_URL,
        "sections": [
            {"section_code": "LEAVE.PURPOSE", "heading": "1. Mục đích và trạng thái tài liệu", "page_start": 1, "page_end": 1},
            {"section_code": "LEAVE.ANNUAL", "heading": "2. Nghỉ hằng năm theo Bộ luật Lao động", "page_start": 2, "page_end": 2},
            {"section_code": "LEAVE.REQUEST", "heading": "3. Quy trình đề xuất nội bộ (bản nháp)", "page_start": 3, "page_end": 3},
            {"section_code": "LEAVE.CHECKLIST", "heading": "4. Thông tin cần có trong đề nghị nghỉ", "page_start": 4, "page_end": 4},
        ],
        "pages": [
            ("1. Mục đích và trạng thái tài liệu", [
                "ĐÂY LÀ BẢN NHÁP MINH HỌA, CHƯA ĐƯỢC CÔNG TY PHÊ DUYỆT.",
                "Tài liệu giúp nhân viên tra cứu khái niệm nghỉ phép và chuẩn bị đề nghị. Nội dung nội bộ dưới đây là quy trình đề xuất để nhóm dự án trình HR xem xét, không tạo quyền lợi hoặc nghĩa vụ mới.",
                "Nếu có khác biệt, quy định pháp luật hiện hành và văn bản chính thức của công ty được ưu tiên. HR cần rà soát trước khi đổi trạng thái tài liệu sang PUBLISHED.",
            ]),
            ("2. Nghỉ hằng năm theo Bộ luật Lao động", [
                "Nguồn pháp lý tham khảo: Văn bản hợp nhất số 18/VBHN-VPQH năm 2026, Bộ luật Lao động, Điều 113. Xem văn bản chính thức tại:",
                LABOR_CODE_URL,
                "Điều 113 quy định số ngày nghỉ hằng năm hưởng nguyên lương theo điều kiện làm việc và thời gian làm việc; có quy định tính theo tỷ lệ khi làm chưa đủ 12 tháng. Lịch nghỉ năm được người sử dụng lao động lập sau khi tham khảo ý kiến người lao động và phải thông báo trước.",
                "Không dùng trang này để tự tính số dư cá nhân. Số dư hiển thị trong ứng dụng và HR cần xác minh theo hồ sơ lao động, thời gian làm việc, điều kiện công việc và chính sách đang có hiệu lực.",
            ]),
            ("3. Quy trình đề xuất nội bộ (bản nháp)", [
                "Quy trình minh họa để HR xem xét: nhân viên gửi đề nghị trên ứng dụng, nêu ngày/buổi và loại nghỉ; quản lý trực tiếp xem xét và phản hồi; hệ thống lưu trạng thái và lịch sử xử lý.",
                "AI chỉ hỗ trợ điền bản nháp. Người lao động kiểm tra và tự gửi đề nghị; AI không phê duyệt, không gửi thay và không bảo đảm đề nghị được chấp thuận.",
                "Các mốc báo trước, chứng từ, người thay thế và luồng xử lý ngoại lệ phải được công ty xác nhận trước khi áp dụng. Không coi các gợi ý trong PDF này là điều kiện pháp lý.",
            ]),
            ("4. Thông tin cần có trong đề nghị nghỉ", [
                "Ngày nghỉ cụ thể; buổi nghỉ nếu hệ thống hỗ trợ; loại nghỉ đã chọn; lý do do người lao động tự cung cấp; thông tin bàn giao nếu quy định nội bộ yêu cầu.",
                "Nếu thiếu ngày, buổi hoặc loại nghỉ, chatbot cần hỏi lại bằng câu hỏi ngắn. Không tự suy đoán lý do, không thêm thông tin sức khỏe nhạy cảm và không gửi đề nghị khi người dùng chưa xác nhận trong biểu mẫu.",
                "Nguồn pháp lý: Bộ luật Lao động, Điều 113 về nghỉ hằng năm và Điều 115 về nghỉ việc riêng, nghỉ không hưởng lương. URL nguồn chính thức được ghi ở trang 2.",
            ]),
        ],
    },
    {
        "document_code": "DEMO-ATTENDANCE-GUIDE",
        "title": "Bản nháp tham khảo: Chấm công và giải trình",
        "file": "attendance-guide-draft.pdf",
        "source_url": None,
        "sections": [
            {"section_code": "ATTENDANCE.STATUS", "heading": "1. Trạng thái và phạm vi hướng dẫn", "page_start": 1, "page_end": 1},
            {"section_code": "ATTENDANCE.RECORD", "heading": "2. Ghi nhận chấm công", "page_start": 2, "page_end": 2},
            {"section_code": "ATTENDANCE.FIX", "heading": "3. Giải trình lượt công (bản nháp)", "page_start": 3, "page_end": 3},
            {"section_code": "ATTENDANCE.PRIVACY", "heading": "4. Rà soát và bảo vệ dữ liệu", "page_start": 4, "page_end": 4},
        ],
        "pages": [
            ("1. Trạng thái và phạm vi hướng dẫn", [
                "ĐÂY LÀ BẢN NHÁP MINH HỌA, CHƯA ĐƯỢC CÔNG TY PHÊ DUYỆT.",
                "Tài liệu mô tả cách sử dụng hệ thống HR nội bộ cho một văn phòng. Đây không phải quy định về ca làm, xử phạt hoặc khấu trừ lương.",
                "Giờ nghiệp vụ được hiển thị theo Asia/Ho_Chi_Minh. Nhân viên cần đối chiếu hướng dẫn đã được HR công bố và liên hệ HR khi dữ liệu có sai lệch.",
            ]),
            ("2. Ghi nhận chấm công", [
                "Nhân viên quét QR tại kiosk được công ty cấu hình. Mỗi sự kiện ghi nhận được lưu trong hệ thống và không bị sửa trực tiếp.",
                "Ứng dụng có thể tổng hợp ngày công từ các sự kiện đã ghi nhận. Ngày chưa có bản ghi không đồng nghĩa với nghỉ hoặc vắng mặt; cần kiểm tra lịch làm việc và hướng dẫn có hiệu lực.",
                "Không chia sẻ mã QR, tài khoản hoặc ảnh chụp có thể làm lộ thông tin xác thực. Báo ngay cho bộ phận phụ trách nếu kiosk hiển thị bất thường.",
            ]),
            ("3. Giải trình lượt công (bản nháp)", [
                "Quy trình minh họa: chọn ngày và lượt chấm công cần giải trình, nhập giờ thực tế cùng lý do do người lao động xác nhận, sau đó gửi qua biểu mẫu hiện có.",
                "Quản lý trực tiếp xem xét theo luồng nghiệp vụ của ứng dụng. Chatbot chỉ điền bản nháp và mở đúng màn hình; không sửa sự kiện gốc hoặc tự duyệt giải trình.",
                "Nếu chưa biết ngày, lượt hoặc giờ thực tế, chatbot hỏi lại. Không tạo dữ liệu công giả để lấp chỗ trống.",
            ]),
            ("4. Rà soát và bảo vệ dữ liệu", [
                "Chỉ xem dữ liệu của bản thân hoặc phạm vi cấp dưới trực tiếp được hệ thống cấp quyền. Yêu cầu HR xem xét quyền quản trị được thực hiện qua kênh nội bộ.",
                "Bản ghi chấm công gốc có tính chất append-only; điều chỉnh cần đi theo quy trình giải trình được duyệt và lưu dấu vết.",
                "Bản nháp này chưa thay thế quy chế lao động, nội quy hoặc hướng dẫn bảo mật chính thức của công ty.",
            ]),
        ],
    },
    {
        "document_code": "DEMO-REPORT-SECURITY",
        "title": "Bản nháp tham khảo: Báo cáo nhân sự và giới hạn dữ liệu",
        "file": "report-security-draft.pdf",
        "source_url": None,
        "sections": [
            {"section_code": "REPORT.STATUS", "heading": "1. Trạng thái và mục đích", "page_start": 1, "page_end": 1},
            {"section_code": "REPORT.CATALOG", "heading": "2. Danh mục báo cáo dự kiến", "page_start": 2, "page_end": 2},
            {"section_code": "REPORT.ACCESS", "heading": "3. Phạm vi truy cập", "page_start": 3, "page_end": 3},
            {"section_code": "REPORT.AI", "heading": "4. Sử dụng chatbot an toàn", "page_start": 4, "page_end": 4},
        ],
        "pages": [
            ("1. Trạng thái và mục đích", [
                "ĐÂY LÀ BẢN NHÁP MINH HỌA, CHƯA ĐƯỢC CÔNG TY PHÊ DUYỆT.",
                "Tài liệu đề xuất cách đọc báo cáo của ứng dụng, không phải quy định lương thưởng hoặc quyết định nhân sự.",
                "Báo cáo chỉ phản ánh dữ liệu nguồn đang được lưu tại thời điểm tạo. Không suy ra lịch sử nếu hệ thống chưa lưu snapshot lịch sử.",
            ]),
            ("2. Danh mục báo cáo dự kiến", [
                "ATTENDANCE: ngày công đã được ghi nhận trong phạm vi được phép.",
                "LEAVE: đề nghị nghỉ, trạng thái và số dư hiện hành theo dữ liệu ứng dụng.",
                "ATTENDANCE_FIX: các giải trình công đã ghi nhận và trạng thái xử lý.",
                "APPROVAL_QUEUE: đề nghị đang chờ quản lý trực tiếp xử lý; HEADCOUNT: số nhân sự hiện tại theo phạm vi được cấp.",
                "MY_PAYSLIP: phiếu lương của bản thân; PAYROLL_SUMMARY: tổng hợp lương cho HR/Admin. Chỉ xuất snapshot kỳ trọn tháng đã APPROVED hoặc CLOSED; mã tiền tệ lấy từ snapshot, tổng tách theo mã và không tính lại lương. Thiếu mã thì cần HR xác minh trước khi xuất.",
                "Danh mục chỉ là đề xuất. Chỉ các loại xuất hiện trong giao diện và được backend cho phép mới khả dụng.",
                "Chọn loại, kỳ và phạm vi; tạo báo cáo rồi xem preview và tải Excel theo template. Preview và file cùng một snapshot dữ liệu thật. File hết hạn sau một giờ; khi thiếu dữ liệu hoặc mất kết nối, không tạo số liệu giả.",
            ]),
            ("3. Phạm vi truy cập", [
                "Nhân viên xem dữ liệu bản thân. Quản lý xem bản thân và cấp dưới trực tiếp. HR/Admin chỉ nhận phạm vi rộng khi capability tương ứng được backend cấp.",
                "Quyền được xác định từ JWT và dữ liệu quan hệ phía máy chủ. Bộ lọc gửi từ trình duyệt không thể mở rộng quyền.",
                "Không tải hoặc chuyển tiếp báo cáo của người khác. Tệp xuất cần được lưu tại vị trí được công ty phê duyệt và xóa theo thời hạn lưu trữ.",
            ]),
            ("4. Sử dụng chatbot an toàn", [
                "Chatbot gọi các nghiệp vụ có allowlist; không chạy SQL do người dùng hoặc mô hình sinh, không tự duyệt đơn và không quyết định quyền.",
                "Khi Gemini hoặc mạng không khả dụng, chatbot chỉ dùng fallback xác định nếu có. Nếu không có handler phù hợp, ứng dụng hiển thị thông báo lỗi chuẩn và không tạo kết quả giả.",
                "Không nhập mật khẩu, mã xác thực, dữ liệu sức khỏe không cần thiết hoặc thông tin nhân sự không thuộc phạm vi công việc.",
            ]),
        ],
    },
]


def _register_font() -> str:
    candidates = [os.getenv("AI_KNOWLEDGE_FONT_FILE"), r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    font_path = next((Path(path) for path in candidates if path and Path(path).is_file()), None)
    if font_path is None:
        raise SystemExit("No Unicode TTF font found. Set AI_KNOWLEDGE_FONT_FILE to a local font path.")
    pdfmetrics.registerFont(TTFont("DemoUnicode", str(font_path)))
    return "DemoUnicode"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    font = _register_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("DemoTitle", parent=styles["Title"], fontName=font, fontSize=18, leading=23)
    heading_style = ParagraphStyle("DemoHeading", parent=styles["Heading2"], fontName=font, fontSize=14, leading=19)
    body_style = ParagraphStyle("DemoBody", parent=styles["BodyText"], fontName=font, fontSize=10, leading=15, spaceAfter=7)
    class BookmarkedDocument(SimpleDocTemplate):
        def afterFlowable(self, flowable):
            if isinstance(flowable, Paragraph) and flowable.style.name == "DemoHeading":
                heading = flowable.getPlainText()
                key = next(section["section_code"] for section in doc["sections"] if section["heading"] == heading)
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(heading, key, level=0, closed=False)

    def page_footer(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 9)
        canvas.drawString(22 * mm, 12 * mm, "Tài liệu mô phỏng phục vụ demo — chưa được công ty phê duyệt")
        canvas.drawRightString(A4[0] - 22 * mm, 12 * mm, f"Trang {document.page}")
        canvas.restoreState()

    for doc in DOCUMENTS:
        target = OUTPUT / doc["file"]
        flowables = [Paragraph(doc["title"], title_style), Spacer(1, 8 * mm)]
        flowables.append(Paragraph("Mục lục", body_style))
        flowables.extend(Paragraph(f"{section['section_code']} — {section['heading'].split('. ', 1)[-1]} — trang {section['page_start']}", body_style) for section in doc["sections"])
        flowables.append(Spacer(1, 5 * mm))
        for index, (heading, paragraphs) in enumerate(doc["pages"]):
            if index:
                flowables.append(PageBreak())
            flowables.append(Paragraph(heading, heading_style))
            flowables.append(Spacer(1, 5 * mm))
            flowables.extend(Paragraph(text.replace("&", "&amp;"), body_style) for text in paragraphs)
        BookmarkedDocument(str(target), pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm, topMargin=20 * mm, bottomMargin=20 * mm, title=doc["title"], author="HR Project Group 3 - draft sample").build(flowables, onFirstPage=page_footer, onLaterPages=page_footer)
        from pypdf import PdfReader
        reader = PdfReader(target)
        if len(reader.pages) != len(doc["pages"]) or len(reader.outline) != len(doc["sections"]):
            raise SystemExit("PDF page/outline mapping changed; refusing to generate a stale manifest.")
        for section in doc["sections"]:
            if section["heading"] not in reader.pages[section["page_start"] - 1].extract_text():
                raise SystemExit("PDF section heading does not match its mapped page.")
        doc["sha256"] = __import__("hashlib").sha256(target.read_bytes()).hexdigest()
        drafts = ROOT.parent / "docs" / "knowledge-drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        markdown = [f"# {doc['title']}", "", "Tài liệu mô phỏng phục vụ demo — DRAFT, chưa được công ty phê duyệt.", ""]
        if doc.get("source_url"):
            markdown.extend([f"Nguồn tham khảo: {doc['source_url']}", ""])
        for section, (heading, paragraphs) in zip(doc["sections"], doc["pages"], strict=True):
            markdown.extend([f"## {heading}", "", f"Mục {section['section_code']} — trang PDF {section['page_start']}.", "", *[paragraph + "\n" for paragraph in paragraphs]])
        (drafts / (Path(doc["file"]).stem + ".md")).write_text("\n".join(markdown), encoding="utf-8")
    manifest_path = OUTPUT / "manifest.json"
    manifest_path.write_text(json.dumps({"status": "DRAFT_ONLY", "generated_notice": "All documents are examples, not approved company policy.", "documents": DOCUMENTS}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(DOCUMENTS)} draft PDFs and manifest at {OUTPUT}")


if __name__ == "__main__":
    main()
