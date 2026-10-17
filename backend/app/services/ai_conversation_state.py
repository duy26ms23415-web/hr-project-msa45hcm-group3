"""Owner-bound follow-up context made of enums and IDs, never message text.

"Còn tháng trước thì sao?" or "còn của anh ấy?" can then reuse the previous
intent/target/topic without sending chat history to the provider. Everything
reused here still passes the normal permission checks.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.knowledge import AIConversationState

STATE_TTL = timedelta(minutes=30)
MAX_SECTIONS = 6


@dataclass
class ConversationContext:
    last_intent: str | None = None
    last_target: str | None = None
    last_employee_code: str | None = None
    last_section_ids: list[int] = field(default_factory=list)


async def load_context(db, owner_user_account_id) -> ConversationContext | None:
    if db is None or owner_user_account_id is None:
        return None
    row = await db.scalar(select(AIConversationState).where(
        AIConversationState.owner_user_account_id == owner_user_account_id,
        AIConversationState.expires_at > datetime.now(timezone.utc),
    ))
    if not isinstance(row, AIConversationState):
        return None
    return ConversationContext(row.last_intent, row.last_target, row.last_employee_code,
                               [int(value) for value in (row.last_section_ids or [])][:MAX_SECTIONS])


async def remember(db, owner_user_account_id, *, intent: str, target: str | None,
                   employee_code: str | None = None, section_ids=()) -> None:
    if db is None or owner_user_account_id is None:
        return
    values = {
        "last_intent": intent, "last_target": target, "last_employee_code": employee_code,
        "last_section_ids": [int(value) for value in section_ids if value][:MAX_SECTIONS],
        "expires_at": datetime.now(timezone.utc) + STATE_TTL,
    }
    statement = insert(AIConversationState).values(owner_user_account_id=owner_user_account_id, **values)
    await db.execute(statement.on_conflict_do_update(
        index_elements=[AIConversationState.owner_user_account_id], set_=values))

