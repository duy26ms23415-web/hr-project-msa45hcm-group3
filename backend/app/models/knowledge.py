from datetime import date, datetime
from sqlalchemy import BigInteger, String, Text, DateTime, ForeignKey, Integer, Boolean, Date, JSON, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base


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
        Index("ix_ai_knowledge_versions_doc_status", "document_id", "status"),
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    version: Mapped[KnowledgeDocumentVersion] = relationship("KnowledgeDocumentVersion", back_populates="sections")


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
