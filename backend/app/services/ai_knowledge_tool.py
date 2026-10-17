"""Published policy lookup with permissions applied before retrieval."""
from sqlalchemy import and_, case, exists, or_, select
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSection
from app.schemas.ai import AISource
from app.services.ai_access import allowed_knowledge_roles
from app.services.knowledge_retrieval import Passage, retrieve
from app.services.knowledge_search import hybrid_search


def passage_source(p: Passage, excerpt: str | None = None) -> AISource:
    return AISource(
        document_id=p.document_id, title=p.title, excerpt=p.content if excerpt is None else excerpt,
        source_url=p.source_url if p.version_id is None else None,
        version_id=p.version_id, section_id=p.section_id, section_code=p.section_code,
        heading=p.heading, page_start=p.page_start, page_end=p.page_end,
        viewer_path=(f"/knowledge/view/{p.document_id}?version={p.version_id}&section={p.section_id}"
                     if p.version_id and p.section_id and p.page_start else None),
    )


def _key(p: Passage):
    # A PDF section is cited once; legacy text documents are keyed by excerpt.
    return (p.document_id, p.version_id, p.section_id) if p.section_id is not None else (p.document_id, p.version_id, p.content)


class AIKnowledgeTool:
    @staticmethod
    async def documents(db, roles, today, unindexed_only: bool = False):
        """Section-level rows for lexical retrieval.

        unindexed_only limits this to legacy text documents and versions that
        have no chunks yet (before reindexing); chunked versions use hybrid_search.
        """
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
        if unindexed_only:
            version_available = and_(version_available, ~exists().where(
                KnowledgeChunk.version_id == KnowledgeDocumentVersion.version_id))
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
    async def search(db, roles, today, queries, *, limit=3, legacy_documents=None, **options) -> list[Passage]:
        """Hybrid hits over chunked versions, then lexical hits over unchunked ones."""
        if db is None and legacy_documents is None:
            return []
        queries = [query for query in queries if query]
        passages = list(await hybrid_search(db, roles, today, queries, limit=limit, **options))
        if options.get("rule_types") or options.get("domains"):
            return passages  # Unchunked documents carry no rule labels to filter on.
        if legacy_documents is None:
            legacy_documents = await AIKnowledgeTool.documents(db, roles, today, unindexed_only=True)
        seen = {_key(p) for p in passages}
        per_query = limit if len(queries) == 1 else min(limit, 2)
        for query in queries:
            for passage in retrieve(query, legacy_documents, limit=per_query):
                if _key(passage) not in seen:
                    seen.add(_key(passage))
                    passages.append(passage)
        return passages[:limit]

    @staticmethod
    async def sources(db, roles, today, question):
        if db is None:
            return []
        return [passage_source(p) for p in await AIKnowledgeTool.search(db, roles, today, [question], limit=2)]
