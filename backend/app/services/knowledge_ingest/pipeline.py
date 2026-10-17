"""Upload → sections, and sections → indexed chunks (lexical, tags, vectors)."""
import logging

from sqlalchemy import bindparam, delete, select, update

from app.ai.providers.gemini import ProviderFailure, embed_texts, embeddings_ready
from app.core.config import settings
from app.models.knowledge import EMBEDDING_DIM, KnowledgeChunk, KnowledgeDocumentVersion, KnowledgeSection
from app.services.knowledge_ingest.chunker import chunk_section
from app.services.knowledge_ingest.gemini_fallback import is_scanned, structure_with_gemini
from app.services.knowledge_ingest.layout import extract_lines
from app.services.knowledge_ingest.models import SectionDraft, StructureResult
from app.services.knowledge_ingest.rule_tagger import tag_chunks
from app.services.knowledge_ingest.structure import _locate, build_structure
from app.services.knowledge_ingest.text import compact
from app.services.knowledge_ingest.toc import detect_toc
from app.services.knowledge_retrieval import normalize
from app.services.knowledge_storage import PDFValidationError

logger = logging.getLogger(__name__)


async def build_sections(raw: bytes, pages_text: list[str]) -> StructureResult:
    """Automatic structure for an uploaded PDF; Gemini only when local parsing is insufficient."""
    pages = extract_lines(raw, pages_text)
    result = build_structure(raw, pages)
    if result.method == "PAGE" or is_scanned(pages_text):
        recovered = await structure_with_gemini(raw, pages, pages_text, result.toc_pages)
        if recovered is not None:
            return recovered
    if not result.sections:
        raise PDFValidationError("PDF_TEXT_REQUIRED")
    return result


def sections_from_manifest(raw: bytes, pages_text: list[str], manifest) -> list[SectionDraft]:
    """HR-edited mapping: each heading must be printed in its page range.

    Content runs from the heading to the next mapped heading (or the end of the
    section's last page), so editing the mapping never duplicates text.
    """
    if not manifest or len(manifest) > 200 or len({section.section_code for section in manifest}) != len(manifest):
        raise PDFValidationError("PDF_SECTION_MANIFEST_INVALID")
    pages = extract_lines(raw, pages_text)
    skip = detect_toc(pages).pages
    located = []
    for order, section in enumerate(manifest):
        if section.page_end < section.page_start or section.page_end > len(pages_text):
            raise PDFValidationError("PDF_SECTION_MANIFEST_INVALID")
        hit = None
        for page in range(section.page_start, section.page_end + 1):
            hit = _locate(section.heading, pages, page, skip)
            if hit and section.page_start <= hit[0] <= section.page_end:
                break
            hit = None
        if not hit:
            raise PDFValidationError("PDF_SECTION_HEADING_MISMATCH")
        located.append((hit, order))
    starts = sorted(position for position, _ in located)
    drafts: list[SectionDraft | None] = [None] * len(manifest)
    for (page, line_index), order in located:
        section = manifest[order]
        later = [start for start in starts if start > (page, line_index)]
        stop = min(later[0], (section.page_end + 1, 0)) if later else (section.page_end + 1, 0)
        lines = [line for number in range(page, section.page_end + 1)
                 for index, line in enumerate(pages[number - 1]) if (page, line_index) <= (number, index) < stop]
        drafts[order] = SectionDraft(
            section.section_code, section.heading, section.page_start, section.page_end,
            "\n".join(line.text for line in lines), level=section.level or 1,
            heading_path=section.heading_path or section.heading, is_answerable=section.is_answerable,
        )
    return drafts


async def index_version(db, version, document_title: str, pages_text: list[str] | None, *, enrich: bool) -> None:
    """Rebuild chunks for a version in the current transaction. enrich adds rule tags
    and embeddings (Gemini) inline; request handlers holding row locks should
    instead write lexical chunks, commit, then call enrich_committed_version.

    Embedding failures never block publishing: the version stays searchable
    through full-text and trigram search (index_status LEXICAL_ONLY).
    """
    chunks = await write_lexical_chunks(db, version, document_title, pages_text)
    if enrich:
        labels, vectors = await _enrichment([(chunk.contextual_text, chunk.content) for chunk in chunks], version.version_id)
        for chunk, (rule_type, domains) in zip(chunks, labels):
            chunk.rule_type, chunk.applies_to = rule_type, domains
        for chunk, vector in zip(chunks, vectors or []):
            chunk.embedding = vector
        _set_index_status(version, vectors)
        await db.flush()


async def write_lexical_chunks(db, version, document_title: str, pages_text: list[str] | None) -> list[KnowledgeChunk]:
    """Replace a version's chunks with untagged, unembedded ones (no provider calls)."""
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.version_id == version.version_id))
    sections = (await db.scalars(select(KnowledgeSection).where(
        KnowledgeSection.version_id == version.version_id
    ).order_by(KnowledgeSection.page_start, KnowledgeSection.section_id))).all()
    chunks: list[KnowledgeChunk] = []
    for section in sections:
        path = section.heading_path or section.heading
        if compact(section.content) == compact(section.heading):
            continue  # A bare chapter title has nothing to retrieve.
        for draft in chunk_section(section.content, section.page_start, section.page_end, pages_text):
            chunks.append(KnowledgeChunk(
                section_id=section.section_id, version_id=version.version_id, chunk_index=draft.index,
                content=draft.content, contextual_text=f"{document_title} > {path}\n{draft.content}",
                normalized_text=normalize(f"{path}\n{draft.content}"),
                page_start=draft.page_start, page_end=draft.page_end,
            ))
    for chunk in chunks:
        db.add(chunk)
    version.embedding_model = None
    version.index_status = "PENDING"
    await db.flush()
    return chunks


async def enrich_committed_version(db, version) -> None:
    """Tag and embed an already committed version without holding row locks.

    Provider calls run first; the results are written in one short transaction
    and only to chunks that still exist, so a concurrent rebuild wins safely.
    """
    rows = (await db.execute(select(KnowledgeChunk.chunk_id, KnowledgeChunk.contextual_text, KnowledgeChunk.content)
                             .where(KnowledgeChunk.version_id == version.version_id)
                             .order_by(KnowledgeChunk.chunk_id))).all()
    labels, vectors = await _enrichment([(row.contextual_text, row.content) for row in rows], version.version_id)
    current = (await db.scalars(select(KnowledgeChunk.chunk_id).where(KnowledgeChunk.version_id == version.version_id)
                                .order_by(KnowledgeChunk.chunk_id))).all()
    if list(current) != [row.chunk_id for row in rows]:
        # A newer rebuild replaced the chunks while the provider worked: it owns the status now.
        await db.rollback()
        return
    table = KnowledgeChunk.__table__
    if rows:
        values = [{"b_id": row.chunk_id, "b_rule": rule_type, "b_domains": domains}
                  for row, (rule_type, domains) in zip(rows, labels)]
        await db.execute(update(table).where(table.c.chunk_id == bindparam("b_id"))
                         .values(rule_type=bindparam("b_rule"), applies_to=bindparam("b_domains")), values)
        if vectors:
            await db.execute(update(table).where(table.c.chunk_id == bindparam("b_id"))
                             .values(embedding=bindparam("b_vector")),
                             [{"b_id": row.chunk_id, "b_vector": vector} for row, vector in zip(rows, vectors)])
    _set_index_status(version, vectors)
    await db.execute(update(KnowledgeDocumentVersion).where(
        KnowledgeDocumentVersion.version_id == version.version_id,
        KnowledgeDocumentVersion.status == "PUBLISHED",
    ).values(index_status=version.index_status, embedding_model=version.embedding_model))
    await db.commit()


async def _enrichment(items: list[tuple[str, str]], version_id) -> tuple[list, list | None]:
    """(contextual_text, content) pairs -> rule labels, and vectors or None."""
    labels = await tag_chunks([(text.split("\n", 1)[0], content) for text, content in items])
    if not items or not embeddings_ready():
        return labels, None
    try:
        vectors = await embed_texts("embed_knowledge", [text for text, _ in items],
                                    "RETRIEVAL_DOCUMENT", dimensions=EMBEDDING_DIM)
    except ProviderFailure as exc:
        logger.warning("knowledge_embedding_failed category=%s version=%s", exc.category, version_id)
        return labels, None
    return labels, vectors


def _set_index_status(version, vectors) -> None:
    version.index_status = "READY" if vectors else "LEXICAL_ONLY"
    version.embedding_model = settings.GEMINI_EMBEDDING_MODEL if vectors else None
