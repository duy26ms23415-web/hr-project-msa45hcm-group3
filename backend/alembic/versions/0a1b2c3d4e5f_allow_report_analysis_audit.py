"""Allow report analysis in the structured audit action constraint."""

from alembic import op

revision = "0a1b2c3d4e5f"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

OLD_ACTIONS = (
    "action IN ('BUDGET_REQUEST', 'CHAT', 'DRAFT_CREATE', 'DRAFT_UPDATE', "
    "'DRAFT_CANCEL', 'REPORT_CREATE', 'REPORT_DOWNLOAD', 'UPLOAD', "
    "'PUBLISH', 'KNOWLEDGE_SEARCH')"
)
NEW_ACTIONS = (
    "action IN ('BUDGET_REQUEST', 'CHAT', 'DRAFT_CREATE', 'DRAFT_UPDATE', "
    "'DRAFT_CANCEL', 'REPORT_CREATE', 'REPORT_DOWNLOAD', 'REPORT_ANALYSIS', 'UPLOAD', "
    "'PUBLISH', 'KNOWLEDGE_SEARCH')"
)


def upgrade():
    op.drop_constraint("ck_ai_request_event_action", "hr_ai_request_events", type_="check")
    op.create_check_constraint("ck_ai_request_event_action", "hr_ai_request_events", NEW_ACTIONS)


def downgrade():
    # PostgreSQL rejects downgrade if analysis events exist; preserve audit history.
    op.drop_constraint("ck_ai_request_event_action", "hr_ai_request_events", type_="check")
    op.create_check_constraint("ck_ai_request_event_action", "hr_ai_request_events", OLD_ACTIONS)
