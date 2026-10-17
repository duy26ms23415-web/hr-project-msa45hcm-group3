"""Hybrid RAG: hierarchical sections, chunks with pgvector/FTS, follow-up state.

Requires the pgvector extension (docker image pgvector/pgvector:pg16).
"""
from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


revision = "4e5f6a7b8c93"
down_revision = "3d4e5f6a7b82"
branch_labels = None
depends_on = None


def upgrade():
    if not context.is_offline_mode() and not op.get_bind().execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")).scalar():
        raise RuntimeError(
            "PostgreSQL extension 'vector' is not available. Use the pgvector/pgvector:pg16 image "
            "(docker-compose.yml) or install pgvector on the server, then rerun 'alembic upgrade head'."
        )
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column("hr_ai_knowledge_sections", sa.Column("level", sa.SmallInteger(), nullable=True))
    op.add_column("hr_ai_knowledge_sections", sa.Column("heading_path", sa.Text(), nullable=True))
    op.add_column("hr_ai_knowledge_document_versions", sa.Column("extraction_method", sa.String(30), nullable=True))
    op.add_column("hr_ai_knowledge_document_versions", sa.Column("index_status", sa.String(20), server_default="PENDING", nullable=False))
    op.add_column("hr_ai_knowledge_document_versions", sa.Column("embedding_model", sa.String(100), nullable=True))
    # Only one published version per document: older publications that are no
    # longer current become ARCHIVED, then a partial unique index enforces it.
    op.execute("""
        UPDATE hr_ai_knowledge_document_versions AS v SET status = 'ARCHIVED'
        WHERE v.status = 'PUBLISHED' AND NOT EXISTS (
            SELECT 1 FROM hr_ai_knowledge_documents d
            WHERE d.current_version_id = v.version_id AND d.status = 'PUBLISHED')
    """)
    op.create_index("uq_ai_knowledge_one_published_version", "hr_ai_knowledge_document_versions", ["document_id"],
                    unique=True, postgresql_where=sa.text("status = 'PUBLISHED'"))
    op.create_check_constraint(
        "ck_ai_knowledge_version_index_status", "hr_ai_knowledge_document_versions",
        "index_status IN ('PENDING', 'READY', 'LEXICAL_ONLY', 'FAILED')",
    )

    op.create_table(
        "hr_ai_knowledge_chunks",
        sa.Column("chunk_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("section_id", sa.BigInteger(), sa.ForeignKey("hr_ai_knowledge_sections.section_id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.BigInteger(), sa.ForeignKey("hr_ai_knowledge_document_versions.version_id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("contextual_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("rule_type", sa.String(20), server_default="INFO", nullable=False),
        sa.Column("applies_to", postgresql.ARRAY(sa.String(20)), server_default="{}", nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("search_tsv", postgresql.TSVECTOR(), sa.Computed("to_tsvector('simple', normalized_text)", persisted=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("section_id", "chunk_index", name="uq_ai_knowledge_chunk_index"),
        sa.CheckConstraint("rule_type IN ('PROHIBITION', 'OBLIGATION', 'PERMISSION', 'PROCEDURE', 'INFO')", name="ck_ai_knowledge_chunk_rule_type"),
    )
    op.create_index("ix_ai_knowledge_chunks_version", "hr_ai_knowledge_chunks", ["version_id"])
    op.create_index("ix_ai_knowledge_chunks_tsv", "hr_ai_knowledge_chunks", ["search_tsv"], postgresql_using="gin")
    op.create_index("ix_ai_knowledge_chunks_applies_to", "hr_ai_knowledge_chunks", ["applies_to"], postgresql_using="gin")
    op.execute("CREATE INDEX ix_ai_knowledge_chunks_trgm ON hr_ai_knowledge_chunks USING gin (normalized_text gin_trgm_ops)")
    op.execute("CREATE INDEX ix_ai_knowledge_chunks_embedding ON hr_ai_knowledge_chunks USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "hr_ai_conversation_states",
        sa.Column("owner_user_account_id", sa.BigInteger(), sa.ForeignKey("hr_user_accounts.user_account_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_intent", sa.String(40)),
        sa.Column("last_target", sa.String(30)),
        sa.Column("last_employee_code", sa.String(50)),
        sa.Column("last_section_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("hr_ai_conversation_states")
    op.drop_table("hr_ai_knowledge_chunks")
    op.drop_constraint("ck_ai_knowledge_version_index_status", "hr_ai_knowledge_document_versions", type_="check")
    op.drop_index("uq_ai_knowledge_one_published_version", table_name="hr_ai_knowledge_document_versions")
    op.drop_column("hr_ai_knowledge_document_versions", "embedding_model")
    op.drop_column("hr_ai_knowledge_document_versions", "index_status")
    op.drop_column("hr_ai_knowledge_document_versions", "extraction_method")
    op.drop_column("hr_ai_knowledge_sections", "heading_path")
    op.drop_column("hr_ai_knowledge_sections", "level")
