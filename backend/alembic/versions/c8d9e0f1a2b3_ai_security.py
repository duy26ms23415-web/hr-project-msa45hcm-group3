"""Add structured AI request audit and rate-limit events."""

from alembic import op
import sqlalchemy as sa


revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hr_ai_request_events",
        sa.Column("event_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "actor_user_account_id",
            sa.BigInteger(),
            sa.ForeignKey("hr_user_accounts.user_account_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("scope", sa.String(30), server_default="NONE", nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("command", sa.String(50)),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "channel IN ('CHAT', 'REPORT', 'UPLOAD', 'KNOWLEDGE')",
            name="ck_ai_request_event_channel",
        ),
        sa.CheckConstraint(
            "action IN ('BUDGET_REQUEST', 'CHAT', 'DRAFT_CREATE', 'DRAFT_UPDATE', "
            "'DRAFT_CANCEL', 'REPORT_CREATE', 'REPORT_DOWNLOAD', 'UPLOAD', "
            "'PUBLISH', 'KNOWLEDGE_SEARCH')",
            name="ck_ai_request_event_action",
        ),
        sa.CheckConstraint(
            "scope IN ('NONE', 'SELF', 'DIRECT_REPORTS', 'COMPANY')",
            name="ck_ai_request_event_scope",
        ),
        sa.CheckConstraint(
            "outcome IN ('ALLOWED', 'SUCCESS', 'DENIED', 'RATE_LIMITED', "
            "'FAILED', 'REJECTED', 'ERROR')",
            name="ck_ai_request_event_outcome",
        ),
    )
    op.create_index(
        "ix_ai_request_events_actor_channel_time",
        "hr_ai_request_events",
        ["actor_user_account_id", "channel", "created_at"],
    )
    op.create_index(
        "ix_ai_request_events_request_id", "hr_ai_request_events", ["request_id"]
    )


def downgrade():
    op.drop_index("ix_ai_request_events_request_id", table_name="hr_ai_request_events")
    op.drop_index(
        "ix_ai_request_events_actor_channel_time", table_name="hr_ai_request_events"
    )
    op.drop_table("hr_ai_request_events")
