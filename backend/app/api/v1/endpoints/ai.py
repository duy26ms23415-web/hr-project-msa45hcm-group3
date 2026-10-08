import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.auth import UserAccount
from app.schemas.ai import AIChatRequest, AIChatResponse, AISuggestion, AISource
from app.services.ai_service import AIService
from app.services.ai_access import allowed_knowledge_roles, user_roles
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSection
from app.services.ai_request_security import secured_operation
from app.services.ai_suggestions import SUGGESTIONS
from app.services.ai_report_draft_service import suggestion_report_defaults

router = APIRouter()


@router.get("/suggestions", response_model=list[AISuggestion])
async def get_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    """Return only actions permitted by the authenticated role and citations visible to it."""
    roles = user_roles(current_user)
    allowed_roles = allowed_knowledge_roles(roles)
    policy_ids = {"leave_policy", "attendance_policy", "report_security"}
    suggestions = [AISuggestion(suggestion_id=key, prompt=value.prompt)
        for key, value in SUGGESTIONS.items()
        if key not in policy_ids and value.roles & roles
        and (not value.needs_employee or current_user.employee_id is not None)]

    # Add policy prompts only when an answerable, currently published PDF is readable.
    citation_specs = [
        ("leave_policy", "Quy định nghỉ phép hằng năm như thế nào?", "DEMO-LEAVE-POLICY", "LEAVE.ANNUAL"),
        ("attendance_policy", "Tôi cần làm gì để giải trình lượt chấm công?", "DEMO-ATTENDANCE-GUIDE", "ATTENDANCE.FIX"),
        ("report_security", "Ai được xem báo cáo nhân sự?", "DEMO-REPORT-SECURITY", "REPORT.ACCESS"),
        ("leave_request", None, "DEMO-LEAVE-POLICY", "LEAVE.REQUEST"),
        ("report_export", None, "DEMO-REPORT-SECURITY", "REPORT.CATALOG"),
    ]
    references = {}
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    for suggestion_id, prompt, document_code, section_code in citation_specs:
        row = (await db.execute(select(
            KnowledgeDocument.document_id,
            KnowledgeDocumentVersion.version_id,
            KnowledgeDocument.title,
            KnowledgeSection.section_id,
            KnowledgeSection.section_code,
            KnowledgeSection.heading,
            KnowledgeSection.page_start,
            KnowledgeSection.page_end,
        ).join(
            KnowledgeDocumentVersion,
            KnowledgeDocumentVersion.version_id == KnowledgeDocument.current_version_id,
        ).join(
            KnowledgeSection,
            KnowledgeSection.version_id == KnowledgeDocumentVersion.version_id,
        ).where(
            KnowledgeDocument.document_code == document_code,
            KnowledgeDocument.status == "PUBLISHED",
            KnowledgeDocument.minimum_role.in_(allowed_roles),
            KnowledgeDocumentVersion.status == "PUBLISHED",
            KnowledgeDocumentVersion.minimum_role.in_(allowed_roles),
            KnowledgeDocumentVersion.effective_from.is_(None) | (KnowledgeDocumentVersion.effective_from <= today),
            KnowledgeDocumentVersion.effective_to.is_(None) | (KnowledgeDocumentVersion.effective_to >= today),
            KnowledgeSection.section_code == section_code,
            KnowledgeSection.is_answerable.is_(True),
        ))).mappings().first()
        if row:
            label = f"tham khảo mục {row['section_code']} {row['heading']}, trang {row['page_start']}"
            source = {
                "document_id": row["document_id"], "title": row["title"], "excerpt": "",
                "version_id": row["version_id"], "section_id": row["section_id"],
                "section_code": row["section_code"], "heading": row["heading"],
                "page_start": row["page_start"], "page_end": row["page_end"],
                "viewer_path": f"/knowledge/view/{row['document_id']}?version={row['version_id']}&section={row['section_id']}",
            }
            references[suggestion_id] = AISource.model_validate(source)
            if prompt:
                suggestions.append(AISuggestion(suggestion_id=suggestion_id, prompt=f"{prompt} ({label})", source=source))
    for suggestion in suggestions:
        suggestion.default_inputs = suggestion_report_defaults(current_user, SUGGESTIONS[suggestion.suggestion_id].prompt, today)
        if suggestion.source:
            continue
        reference_id = SUGGESTIONS[suggestion.suggestion_id].reference_id
        suggestion.source = references.get(reference_id)
        if suggestion.source:
            source = suggestion.source
            suggestion.prompt += f" (tham khảo mục {source.section_code} {source.heading}, trang {source.page_start})"
    return suggestions


@router.post("/chat", response_model=AIChatResponse)
async def chat_with_hr_ai(
    req: AIChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """
    AI Assistant chat endpoint.
    Answers company policy, checks attendance and leave balance,
    and supports drafting leave requests or attendance fixes.
    """
    try:
        async with asyncio.timeout(30):
            async with secured_operation(db, current_user.user_account_id, "CHAT", "CHAT") as audit:
                result = await AIService.process_chat(
                    db,
                    current_user.employee_id,
                    req,
                    user_roles(current_user),
                    owner_user_account_id=current_user.user_account_id,
                    authenticated_user=current_user,
                )
                result.request_id = audit["request_id"]
                audit["command"] = result.action.action_type if result.action else result.answer_mode
                audit["scope"] = "SELF" if result.draft_id or result.action and result.action.action_type in {"SHOW_DATA", "DRAFT_LEAVE", "DRAFT_FIX"} else "NONE"
                if result.answer_mode == "OUT_OF_SCOPE":
                    audit["outcome"] = "DENIED" if result.reply.startswith("Bạn không có quyền") else "REJECTED"
                    if audit["outcome"] == "DENIED":
                        raise HTTPException(403, "PERMISSION_DENIED")
                return result
    except (SQLAlchemyError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=503, detail="DATA_SERVICE_UNAVAILABLE") from exc
    except HTTPException as exc:
        # Preserve the expiration state update; get_db rolls back on HTTP errors.
        if exc.status_code == 410 and exc.detail == "AI_DRAFT_EXPIRED":
            await db.commit()
        raise
