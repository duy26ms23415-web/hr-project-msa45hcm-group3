from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AIRequestEvent(Base):
    """Structured security/audit event; deliberately contains no user text."""

    __tablename__ = "hr_ai_request_events"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('CHAT', 'REPORT', 'UPLOAD', 'KNOWLEDGE')",
            name="ck_ai_request_event_channel",
        ),
        CheckConstraint(
            "action IN ('BUDGET_REQUEST', 'CHAT', 'DRAFT_CREATE', 'DRAFT_UPDATE', "
            "'DRAFT_CANCEL', 'REPORT_CREATE', 'REPORT_DOWNLOAD', 'UPLOAD', "
            "'PUBLISH', 'KNOWLEDGE_SEARCH')",
            name="ck_ai_request_event_action",
        ),
        CheckConstraint(
            "scope IN ('NONE', 'SELF', 'DIRECT_REPORTS', 'COMPANY')",
            name="ck_ai_request_event_scope",
        ),
        CheckConstraint(
            "outcome IN ('ALLOWED', 'SUCCESS', 'DENIED', 'RATE_LIMITED', "
            "'FAILED', 'REJECTED', 'ERROR')",
            name="ck_ai_request_event_outcome",
        ),
        Index(
            "ix_ai_request_events_actor_channel_time",
            "actor_user_account_id",
            "channel",
            "created_at",
        ),
        Index("ix_ai_request_events_request_id", "request_id"),
    )

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("hr_user_accounts.user_account_id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    scope: Mapped[str] = mapped_column(String(30), nullable=False, default="NONE")
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    command: Mapped[str | None] = mapped_column(String(50), nullable=True)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
