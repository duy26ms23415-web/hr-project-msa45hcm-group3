"""Published policy lookup with permissions applied before retrieval."""
from sqlalchemy import and_, case, or_, select
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSection
from app.schemas.ai import AISource
from app.services.ai_access import allowed_knowledge_roles
from app.services.knowledge_retrieval import retrieve


class AIKnowledgeTool:
    @staticmethod
    async def documents(db, roles, today):
        allowed_roles = allowed_knowledge_roles(roles)
        document_legacy = KnowledgeDocument.current_version_id.is_(None)
        version_available = and_(
            KnowledgeDocumentVersion.version_id.is_not(None),
            KnowledgeDocumentVersion.status == "PUBLISHED",
            KnowledgeDocumentVersion.minimum_role.in_(allowed_roles),
            KnowledgeSection.is_answerable.is_(True),
            (KnowledgeDocumentVersion.effective_from.is_(None) | (KnowledgeDocumentVersion.effective_from <= today)),
            (KnowledgeDocumentVersion.effective_to.is_(None) | (KnowledgeDocumentVersion.effective_to >= today)),
        )
        documents_stmt = select(
            KnowledgeDocument.document_id.label("document_id"),
            KnowledgeDocument.source_url.label("source_url"),
            KnowledgeDocument.status.label("document_status"),
            KnowledgeDocumentVersion.version_id.label("version_id"),
            case((KnowledgeDocumentVersion.version_id.is_(None), KnowledgeDocument.title), else_=KnowledgeDocumentVersion.title).label("title"),
            case((KnowledgeDocumentVersion.version_id.is_(None), KnowledgeDocument.status), else_=KnowledgeDocumentVersion.status).label("status"),
            KnowledgeSection.section_id.label("section_id"),
            KnowledgeSection.section_code.label("section_code"),
            KnowledgeSection.heading.label("heading"),
            KnowledgeSection.page_start.label("page_start"),
            KnowledgeSection.page_end.label("page_end"),
            case((KnowledgeDocumentVersion.version_id.is_(None), KnowledgeDocument.content), else_=KnowledgeSection.content).label("content"),
            case((KnowledgeDocumentVersion.version_id.is_(None), True), else_=KnowledgeSection.is_answerable).label("is_answerable"),
        ).outerjoin(
            KnowledgeDocumentVersion,
            KnowledgeDocumentVersion.version_id == KnowledgeDocument.current_version_id,
        ).outerjoin(
            KnowledgeSection,
            KnowledgeSection.version_id == KnowledgeDocumentVersion.version_id,
        ).where(
            KnowledgeDocument.status == "PUBLISHED",
            KnowledgeDocument.minimum_role.in_(allowed_roles),
            or_(and_(document_legacy, KnowledgeDocument.content != ""), version_available),
        )
        return (await db.execute(documents_stmt)).mappings().all()

    @staticmethod
    async def sources(db, roles, today, question):
        if db is None:
            return []
        documents = await AIKnowledgeTool.documents(db, roles, today)
        return [AISource(
            document_id=p.document_id, title=p.title, excerpt=p.content, source_url=p.source_url if p.version_id is None else None,
            version_id=p.version_id, section_id=p.section_id, section_code=p.section_code,
            heading=p.heading, page_start=p.page_start, page_end=p.page_end,
            viewer_path=(f"/knowledge/view/{p.document_id}?version={p.version_id}&section={p.section_id}"
                         if p.version_id and p.section_id and p.page_start else None),
        ) for p in retrieve(question, documents, limit=2)]
