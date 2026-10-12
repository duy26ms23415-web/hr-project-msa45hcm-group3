"""Live grounded-answer smoke test with synthetic policies, no DB/secret output."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.schemas.ai import AIChatRequest
from app.services.ai_service import AIService


async def main():
    if not settings.GEMINI_ENABLED or not settings.GEMINI_API_KEY:
        print('SKIP: Gemini is disabled or unconfigured.')
        return 2
    original = AIService._knowledge_documents
    failures = 0
    try:
        for index, (question, content) in enumerate([
            ('Chính sách nghỉ phép như thế nào?', 'Nghỉ phép năm cần được quản lý trực tiếp duyệt. Không được tự duyệt đơn của mình.'),
            ('Quy định đặt phòng họp?', 'Nhân viên đặt phòng họp qua lịch chung trước khi sử dụng. Đặt phòng họp không cần HR duyệt.'),
        ], 1):
            AIService._knowledge_documents = AsyncMock(return_value=[{
                'document_id': 1, 'title': 'Synthetic policy', 'status': 'PUBLISHED', 'content': content,
                'version_id': 2, 'section_id': 3, 'heading': 'Synthetic section', 'page_start': 1, 'page_end': 1,
            }])
            response = await AIService.process_chat(object(), None, AIChatRequest(message=question), {'EMPLOYEE'})
            ok = response.answer_mode == 'GEMINI' and bool(response.sources) and bool(response.sources[0].viewer_path)
            print(f'case {index}: {"PASS" if ok else "FALLBACK"}; mode={response.answer_mode}; source_links={len(response.sources)}; reply_chars={len(response.reply)}')
            failures += not ok
    finally:
        AIService._knowledge_documents = original
    return int(failures > 0)


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
