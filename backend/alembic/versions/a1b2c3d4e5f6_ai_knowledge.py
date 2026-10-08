"""Managed AI knowledge documents."""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "853259f774e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hr_ai_knowledge_documents",
        sa.Column("document_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(2000)),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("minimum_role", sa.String(20), nullable=False, server_default="EMPLOYEE"),
        sa.Column("updated_by_user_id", sa.BigInteger(), sa.ForeignKey("hr_user_accounts.user_account_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("hr_ai_knowledge_documents")
