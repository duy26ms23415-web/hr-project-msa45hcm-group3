from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class AIChatMessage(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str


class AIChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[AIChatMessage]] = []


class AIChatAction(BaseModel):
    action_type: str  # "NAVIGATE", "SHOW_DATA", "DRAFT_LEAVE", "DRAFT_FIX"
    data: Optional[Dict[str, Any]] = None


class AIChatResponse(BaseModel):
    reply: str
    action: Optional[AIChatAction] = None
