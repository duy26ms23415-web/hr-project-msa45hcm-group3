"""Add versioned knowledge, owned chat drafts and private report runs.

Legacy knowledge rows are retained and backfilled as text-only version 1.
"""
from alembic import op
import sqlalchemy as sa


revision = "b7c8d9e0f1a2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hr_ai_knowledge_documents", sa.Column("document_code", sa.String(80), nullable=True))

    op.create_table(
        "hr_ai_knowledge_document_versions",
        sa.Column("version_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("hr_ai_knowledge_documents.document_id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("minimum_role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("storage_key", sa.String(500)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("byte_size", sa.BigInteger()),
        sa.Column("page_count", sa.Integer()),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("effective_from", sa.Date()),
        sa.Column("effective_to", sa.Date()),
        sa.Column("created_by_user_id", sa.BigInteger(), sa.ForeignKey("hr_user_accounts.user_account_id"), nullable=True),
        sa.Column("published_by_user_id", sa.BigInteger(), sa.ForeignKey("hr_user_accounts.user_account_id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "version_number", name="uq_ai_knowledge_doc_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_ai_knowledge_version_status"),
        sa.CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_ai_knowledge_effective_range"),
    )
    op.create_index("ix_ai_knowledge_versions_doc_status", "hr_ai_knowledge_document_versions", ["document_id", "status"])

    op.create_table(
        "hr_ai_knowledge_sections",
        sa.Column("section_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.BigInteger(), sa.ForeignKey("hr_ai_knowledge_document_versions.version_id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_code", sa.String(100), nullable=False),
        sa.Column("heading", sa.String(300), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("anchor", sa.String(300)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_answerable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("version_id", "section_code", name="uq_ai_knowledge_section_code"),
        sa.CheckConstraint("page_start IS NULL OR page_start > 0", name="ck_ai_knowledge_section_page_start"),
        sa.CheckConstraint("(page_start IS NULL AND page_end IS NULL) OR (page_start IS NOT NULL AND page_end >= page_start)", name="ck_ai_knowledge_section_page_range"),
    )
    op.create_index("ix_ai_knowledge_sections_version", "hr_ai_knowledge_sections", ["version_id"])

    op.add_column("hr_ai_knowledge_documents", sa.Column("current_version_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_ai_knowledge_current_version", "hr_ai_knowledge_documents",
        "hr_ai_knowledge_document_versions", ["current_version_id"], ["version_id"],
    )

    op.execute("""
        UPDATE hr_ai_knowledge_documents
        SET document_code = 'LEGACY-' || document_id::text
    """)
    op.alter_column("hr_ai_knowledge_documents", "document_code", nullable=False)
    op.create_unique_constraint("uq_ai_knowledge_document_code", "hr_ai_knowledge_documents", ["document_code"])

    op.execute("""
        INSERT INTO hr_ai_knowledge_document_versions
            (document_id, version_number, title, minimum_role, status,
             created_at, updated_at)
        SELECT document_id, 1, title, minimum_role,
               CASE WHEN status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED') THEN status ELSE 'DRAFT' END,
               created_at, updated_at
        FROM hr_ai_knowledge_documents
    """)
    op.execute("""
        UPDATE hr_ai_knowledge_documents d
        SET current_version_id = v.version_id
        FROM hr_ai_knowledge_document_versions v
        WHERE v.document_id = d.document_id AND v.version_number = 1
    """)
    op.execute("""
        INSERT INTO hr_ai_knowledge_sections
            (version_id, section_code, heading, content, is_answerable, created_at)
        SELECT v.version_id, 'LEGACY_TEXT', d.title, d.content,
               (d.status = 'PUBLISHED'), d.created_at
        FROM hr_ai_knowledge_documents d
        JOIN hr_ai_knowledge_document_versions v ON v.document_id = d.document_id AND v.version_number = 1
    """)

    op.create_table(
        "hr_ai_chat_drafts",
        sa.Column("draft_id", sa.String(36), primary_key=True),
        sa.Column("owner_user_account_id", sa.BigInteger(), sa.ForeignKey("hr_user_accounts.user_account_id", ondelete="CASCADE"), nullable=False),
        sa.Column("command", sa.String(50), nullable=False),
        sa.Column("typed_params", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("missing_fields", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(20), server_default="COLLECTING", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('COLLECTING', 'READY', 'CANCELLED', 'EXPIRED')", name="ck_ai_chat_draft_status"),
    )
    op.create_index("ix_ai_chat_drafts_owner_expiry", "hr_ai_chat_drafts", ["owner_user_account_id", "expires_at"])

    op.create_table(
        "hr_report_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("owner_user_account_id", sa.BigInteger(), sa.ForeignKey("hr_user_accounts.user_account_id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("scope", sa.String(30), nullable=False),
        sa.Column("filters", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("template_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="GENERATING", nullable=False),
        sa.Column("row_count", sa.Integer()),
        sa.Column("scope_snapshot", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("snapshot_storage_key", sa.String(500)),
        sa.Column("storage_key", sa.String(500)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("as_of", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('GENERATING', 'READY', 'FAILED', 'EXPIRED')", name="ck_report_run_status"),
    )
    op.create_index("ix_report_runs_owner_created", "hr_report_runs", ["owner_user_account_id", "created_at"])
    op.create_index("ix_report_runs_expiry", "hr_report_runs", ["status", "expires_at"])


def downgrade():
    # Downgrade removes draft/run/version data created after this migration.
    op.drop_index("ix_report_runs_expiry", table_name="hr_report_runs")
    op.drop_index("ix_report_runs_owner_created", table_name="hr_report_runs")
    op.drop_table("hr_report_runs")
    op.drop_index("ix_ai_chat_drafts_owner_expiry", table_name="hr_ai_chat_drafts")
    op.drop_table("hr_ai_chat_drafts")
    op.drop_constraint("uq_ai_knowledge_document_code", "hr_ai_knowledge_documents", type_="unique")
    op.drop_constraint("fk_ai_knowledge_current_version", "hr_ai_knowledge_documents", type_="foreignkey")
    op.drop_column("hr_ai_knowledge_documents", "current_version_id")
    op.drop_column("hr_ai_knowledge_documents", "document_code")
    op.drop_index("ix_ai_knowledge_sections_version", table_name="hr_ai_knowledge_sections")
    op.drop_table("hr_ai_knowledge_sections")
    op.drop_index("ix_ai_knowledge_versions_doc_status", table_name="hr_ai_knowledge_document_versions")
    op.drop_table("hr_ai_knowledge_document_versions")
