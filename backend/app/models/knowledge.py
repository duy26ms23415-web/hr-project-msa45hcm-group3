from datetime import date, datetime
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, String, Text, DateTime, ForeignKey, Integer, SmallInteger, Boolean, Date, JSON, CheckConstraint, Computed, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import text
from sqlalchemy.sql import func
from app.core.database import Base

# Changing the dimension requires a migration and a full reindex.
EMBEDDING_DIM = 768
RULE_TYPES = ("PROHIBITION", "OBLIGATION", "PERMISSION", "PROCEDURE", "INFO")
RULE_DOMAINS = ("LEAVE", "REMOTE", "ATTENDANCE", "ATTENDANCE_FIX", "PAYROLL", "REPORT", "CONDUCT", "GENERAL")


class KnowledgeDocument(Base):
    __tablename__ = "hr_ai_knowledge_documents"

    document_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    minimum_role: Mapped[str] = mapped_column(String(20), default="EMPLOYEE", nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("hr_ai_knowledge_document_versions.version_id"), nullable=True)
    updated_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    versions: Mapped[list["KnowledgeDocumentVersion"]] = relationship(
        "KnowledgeDocumentVersion", back_populates="document", foreign_keys="KnowledgeDocumentVersion.document_id"
    )


class KnowledgeDocumentVersion(Base):
    __tablename__ = "hr_ai_knowledge_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_ai_knowledge_doc_version"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_ai_knowledge_version_status"),
        CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_ai_knowledge_effective_range"),
        CheckConstraint("index_status IN ('PENDING', 'READY', 'LEXICAL_ONLY', 'FAILED')", name="ck_ai_knowledge_version_index_status"),
        Index("ix_ai_knowledge_versions_doc_status", "document_id", "status"),
        Index("uq_ai_knowledge_one_published_version", "document_id", unique=True,
              postgresql_where=text("status = 'PUBLISHED'")),
    )

    version_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_ai_knowledge_documents.document_id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    minimum_role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id"), nullable=True)
    published_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id"), nullable=True)
    # How sections were derived (LAYOUT, OUTLINE, PRINTED_TOC, MANUAL, GEMINI_*).
    extraction_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    index_status: Mapped[str] = mapped_column(String(20), default="PENDING", server_default="PENDING", nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    document: Mapped[KnowledgeDocument] = relationship(
        "KnowledgeDocument", back_populates="versions", foreign_keys=[document_id]
    )
    sections: Mapped[list["KnowledgeSection"]] = relationship("KnowledgeSection", back_populates="version")


class KnowledgeSection(Base):
    __tablename__ = "hr_ai_knowledge_sections"
    __table_args__ = (
        UniqueConstraint("version_id", "section_code", name="uq_ai_knowledge_section_code"),
        CheckConstraint("page_start IS NULL OR page_start > 0", name="ck_ai_knowledge_section_page_start"),
        CheckConstraint("(page_start IS NULL AND page_end IS NULL) OR (page_start IS NOT NULL AND page_end >= page_start)", name="ck_ai_knowledge_section_page_range"),
        Index("ix_ai_knowledge_sections_version", "version_id"),
    )

    section_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_ai_knowledge_document_versions.version_id", ondelete="CASCADE"), nullable=False)
    section_code: Mapped[str] = mapped_column(String(100), nullable=False)
    heading: Mapped[str] = mapped_column(String(300), nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_answerable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    heading_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    version: Mapped[KnowledgeDocumentVersion] = relationship("KnowledgeDocumentVersion", back_populates="sections")


class KnowledgeChunk(Base):
    """Retrieval unit: a slice of one section with lexical and vector indexes."""
    __tablename__ = "hr_ai_knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("section_id", "chunk_index", name="uq_ai_knowledge_chunk_index"),
        CheckConstraint("rule_type IN ('PROHIBITION', 'OBLIGATION', 'PERMISSION', 'PROCEDURE', 'INFO')", name="ck_ai_knowledge_chunk_rule_type"),
        Index("ix_ai_knowledge_chunks_version", "version_id"),
    )

    chunk_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_ai_knowledge_sections.section_id", ondelete="CASCADE"), nullable=False)
    version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_ai_knowledge_document_versions.version_id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    contextual_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_type: Mapped[str] = mapped_column(String(20), default="INFO", server_default="INFO", nullable=False)
    applies_to: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, server_default="{}", nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    search_tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', normalized_text)", persisted=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIConversationState(Base):
    """Owner-bound enum context for follow-ups; never holds message text."""
    __tablename__ = "hr_ai_conversation_states"

    owner_user_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id", ondelete="CASCADE"), primary_key=True)
    last_intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_target: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Resolved employee code; reused only through the normal scoped lookup.
    last_employee_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_section_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AIChatDraft(Base):
    __tablename__ = "hr_ai_chat_drafts"
    __table_args__ = (
        CheckConstraint("status IN ('COLLECTING', 'READY', 'CANCELLED', 'EXPIRED')", name="ck_ai_chat_draft_status"),
        Index("ix_ai_chat_drafts_owner_expiry", "owner_user_account_id", "expires_at"),
    )

    draft_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id", ondelete="CASCADE"), nullable=False)
    command: Mapped[str] = mapped_column(String(50), nullable=False)
    typed_params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="COLLECTING", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ReportRun(Base):
    __tablename__ = "hr_report_runs"
    __table_args__ = (
        CheckConstraint("status IN ('GENERATING', 'READY', 'FAILED', 'EXPIRED')", name="ck_report_run_status"),
        Index("ix_report_runs_owner_created", "owner_user_account_id", "created_at"),
        Index("ix_report_runs_expiry", "status", "expires_at"),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    scope: Mapped[str] = mapped_column(String(30), nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="GENERATING", nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_snapshot: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    snapshot_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
