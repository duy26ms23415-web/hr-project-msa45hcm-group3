from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.auth import UserAccount
from app.schemas.ai import AIChatRequest, AIChatResponse
from app.services.ai_service import AIService

router = APIRouter()


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
    response = await AIService.process_chat(db, current_user.employee_id, req)
    return response
