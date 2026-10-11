"""Safe, deterministic error envelopes for AI, private knowledge and reports."""
import re
from uuid import uuid4

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler

from app.services.ai_request_security import request_context

MESSAGES = {
    "ANALYSIS_DEPENDENCIES_UNAVAILABLE": "Máy chủ chưa có đủ thư viện phân tích. Vui lòng liên hệ quản trị viên hệ thống.",
    "ANALYSIS_ROW_LIMIT": "Báo cáo vượt giới hạn 10.000 dòng để phân tích. Vui lòng thu hẹp kỳ hoặc bộ lọc.",
    "ANALYSIS_VALUE_OUT_OF_RANGE": "Dữ liệu báo cáo vượt phạm vi tạo biểu đồ. Vui lòng liên hệ HR để kiểm tra dữ liệu.",
    "PDF_SIZE_INVALID": "PDF phải có dung lượng từ 1 byte đến 10 MiB.",
    "PDF_MIME_INVALID": "Nội dung file không phải PDF. Đổi đuôi file sang .pdf không chuyển đổi định dạng.",
    "PDF_INVALID": "Không đọc được PDF. Hãy xuất lại file PDF và thử lại.",
    "PDF_ENCRYPTED": "PDF có mật khẩu hoặc mã hóa. Hãy tải bản không có mật khẩu.",
    "PDF_ACTIVE_CONTENT": "PDF chứa nội dung tương tác không được phép. Hãy xuất bản PDF tĩnh rồi tải lại.",
    "PDF_PAGE_LIMIT": "PDF phải có từ 1 đến 100 trang. Hãy chia tài liệu thành các file nhỏ hơn.",
    "PDF_TEXT_REQUIRED": "PDF chưa có văn bản đọc được (có thể là bản scan). Hãy dùng OCR hoặc xuất PDF có văn bản trước khi tải.",
    "PDF_TEXT_LIMIT": "Văn bản PDF vượt giới hạn xử lý. Hãy chia tài liệu thành các file nhỏ hơn.",
    "PAYROLL_CURRENCY_UNAVAILABLE": "Thông tin tiền tệ của kỳ lương chưa được xác minh. Vui lòng liên hệ HR; báo cáo chưa được tạo.",
    "AI_UNAVAILABLE": "Hiện không thể kết nối dịch vụ AI để xử lý yêu cầu này. Bạn có thể chọn một gợi ý có sẵn hoặc thử lại sau.",
    "PERMISSION_DENIED": "Bạn không có quyền thực hiện yêu cầu này hoặc truy cập dữ liệu được yêu cầu. Vui lòng chọn chức năng trong phạm vi quyền của bạn.",
    "SESSION_EXPIRED": "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để tiếp tục.",
    "DOCUMENT_UNAVAILABLE": "Tài liệu không còn khả dụng hoặc bạn không có quyền truy cập.",
    "REPORT_UNAVAILABLE": "Báo cáo không còn khả dụng hoặc bạn không có quyền truy cập.",
    "REPORT_EXPIRED": "File báo cáo đã hết hạn. Vui lòng tạo báo cáo mới.",
    "DATA_SERVICE_UNAVAILABLE": "Hiện không thể truy xuất dữ liệu HR. Vui lòng thử lại sau. Báo cáo chưa được tạo.",
    "INVALID_INPUT": "Thông tin chưa hợp lệ. Vui lòng kiểm tra các trường được yêu cầu.",
    "DRAFT_EXPIRED": "Nháp hội thoại đã hết hạn. Vui lòng bắt đầu lại yêu cầu.",
    "DRAFT_CONFLICT": "Nháp đã được cập nhật ở lượt khác. Vui lòng tải lại nháp trước khi tiếp tục.",
    "REPORT_LIMIT_EXCEEDED": "Báo cáo vượt giới hạn dữ liệu. Vui lòng thu hẹp kỳ hoặc bộ lọc.",
    "RATE_LIMITED": "Bạn đang gửi yêu cầu quá nhanh. Vui lòng thử lại sau.",
    "INVALID_AI_OUTPUT": "Dịch vụ AI chưa trả về kết quả hợp lệ cho yêu cầu này. Vui lòng chọn một gợi ý có sẵn hoặc thử lại sau.",
}


class AIRequestContextMiddleware:
    def __init__(self, app, prefixes):
        self.app, self.prefixes = app, prefixes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not any(scope["path"] == prefix or scope["path"].startswith(prefix + "/") for prefix in self.prefixes):
            return await self.app(scope, receive, send)
        request_id = uuid4().hex  # Never trust an inbound request ID.
        scope.setdefault("state", {})["ai_request_id"] = request_id

        async def send_response(message):
            if message["type"] == "http.response.start":
                headers = [(key, value) for key, value in message.get("headers", []) if key.lower() not in {b"x-request-id", b"cache-control"}]
                message["headers"] = headers + [(b"x-request-id", request_id.encode()), (b"cache-control", b"private, no-store")]
            await send(message)

        with request_context(request_id):
            await self.app(scope, receive, send_response)


def install_ai_errors(app, prefixes):
    def scoped(request):
        return any(request.url.path == prefix or request.url.path.startswith(prefix + "/") for prefix in prefixes)

    def envelope(request, status, detail, headers=None):
        raw = detail if isinstance(detail, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", detail) else None
        if status == 401:
            code = "SESSION_EXPIRED"
        elif status == 403:
            code = "PERMISSION_DENIED"
        elif status == 404:
            code = "REPORT_UNAVAILABLE" if "/reports" in request.url.path else "DOCUMENT_UNAVAILABLE" if "/knowledge" in request.url.path else "PERMISSION_DENIED"
        elif raw == "PAYROLL_CURRENCY_UNAVAILABLE":
            code = raw
        elif raw in MESSAGES and raw.startswith("ANALYSIS_") and status in {422, 503}:
            code = raw
        elif status == 422 and raw in MESSAGES and raw.startswith("PDF_"):
            code = raw
        elif status == 410:
            code = "DRAFT_EXPIRED" if raw and "DRAFT" in raw else "REPORT_EXPIRED"
        elif status == 409:
            code = "DRAFT_CONFLICT" if raw and "DRAFT" in raw else "INVALID_INPUT"
        elif status == 429:
            code = "RATE_LIMITED"
        elif raw in {"REPORT_TOO_LARGE", "REPORT_LIMIT_EXCEEDED"}:
            code = "REPORT_LIMIT_EXCEEDED"
        elif status >= 500:
            code = raw if raw in {"AI_UNAVAILABLE", "INVALID_AI_OUTPUT"} else "DATA_SERVICE_UNAVAILABLE"
        else:
            code = "INVALID_INPUT"
        message = MESSAGES[code]
        safe_headers = {key: value for key, value in (headers or {}).items() if key.lower() in {"retry-after", "www-authenticate"}}
        request_id = getattr(request.state, "ai_request_id", None) or uuid4().hex
        safe_headers.update({"X-Request-ID": request_id, "Cache-Control": "private, no-store"})
        # Keep a bounded legacy code for existing clients; never return validation inputs/exception text.
        legacy = raw if raw and raw.startswith(("AI_", "PDF_", "REPORT_", "PERMISSION_", "DATA_", "ANALYSIS_")) else code
        return JSONResponse({"detail": legacy, "code": code, "message_code": code, "message": message, "reply": message, "status": "DENIED" if status in {401, 403} else "UNAVAILABLE" if status >= 500 else "OUT_OF_SCOPE", "action": None, "sources": [], "request_id": request_id}, status_code=status, headers=safe_headers)

    async def http_error(request, exc):
        if not scoped(request):
            return await http_exception_handler(request, exc)
        return envelope(request, exc.status_code, exc.detail, exc.headers)

    async def validation_error(request, exc):
        if not scoped(request):
            return await request_validation_exception_handler(request, exc)
        return envelope(request, 422, "INVALID_INPUT")

    async def unexpected_error(request, exc):
        if not scoped(request):
            return PlainTextResponse("Internal Server Error", status_code=500)
        return envelope(request, 503, "DATA_SERVICE_UNAVAILABLE")

    app.add_middleware(AIRequestContextMiddleware, prefixes=prefixes)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, unexpected_error)
