"""Knowledge document version lifecycle: upload, draft edits, publish, re-activate,
unpublish, restore and reindex.

Slow provider work (Gemini structure/OCR fallback, tagging, embeddings) never
runs while this module holds FOR UPDATE locks: uploads build sections before
locking the document, and publish/reindex commit lexical chunks first and
enrich them afterwards.
"""
from fastapi import HTTPException
from sqlalchemy import case, delete, func, select, update

from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSection
from app.services.ai_access import allowed_knowledge_roles, user_roles
from app.services.knowledge_ingest import heading_matches
from app.services.knowledge_ingest.gemini_fallback import pdf_structure_ready
from app.services.knowledge_ingest.pipeline import (
    build_sections, enrich_committed_version, index_version, sections_from_manifest, write_lexical_chunks,
)
from app.services.knowledge_storage import PDFValidationError, delete_pdf, parse_pdf, resolve_storage_path, store_pdf

MAX_SECTIONS = 200


def editor_access(user, document) -> None:
    roles = user_roles(user)
    if not roles & {"HR", "ADMIN"} or document.minimum_role not in allowed_knowledge_roles(roles):
        raise HTTPException(404, "Không tìm thấy tài liệu")


async def _document(db, document_id, *, lock: bool):
    statement = select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id)
    if lock:
        # Re-read after an unlocked pre-check so the locked row is current.
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(statement)


async def _version(db, document_id, version_id):
    return await db.scalar(select(KnowledgeDocumentVersion).where(
        KnowledgeDocumentVersion.version_id == version_id,
        KnowledgeDocumentVersion.document_id == document_id,
    ).with_for_update())


def read_version_pdf(version):
    try:
        raw = resolve_storage_path(version.storage_key or "").read_bytes()
        parsed = parse_pdf(raw, allow_textless=version.extraction_method == "GEMINI_OCR")
    except (FileNotFoundError, OSError, PDFValidationError) as exc:
        raise HTTPException(409, "PDF_FILE_UNAVAILABLE") from exc
    if parsed.sha256 != version.sha256 or len(parsed.pages) != version.page_count:
        raise HTTPException(409, "PDF_INTEGRITY_MISMATCH")
    return raw, parsed


def section_row(version_id: int, draft) -> KnowledgeSection:
    heading = draft.heading.strip()
    return KnowledgeSection(
        version_id=version_id, section_code=draft.section_code, heading=heading,
        page_start=draft.page_start, page_end=draft.page_end, anchor=heading, content=draft.content,
        is_answerable=draft.is_answerable, level=draft.level, heading_path=draft.heading_path or heading,
    )


async def archive_published_versions(db, document_id, keep_version_id=None) -> None:
    """At most one PUBLISHED version per document (also enforced by a unique index)."""
    statement = update(KnowledgeDocumentVersion).where(
        KnowledgeDocumentVersion.document_id == document_id,
        KnowledgeDocumentVersion.status == "PUBLISHED",
    )
    if keep_version_id is not None:
        statement = statement.where(KnowledgeDocumentVersion.version_id != keep_version_id)
    await db.execute(statement.values(status="ARCHIVED"))


# --- upload ---------------------------------------------------------------

def _check_upload_target(user, document, minimum_role, effective_from, effective_to) -> None:
    if not document:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    editor_access(user, document)
    if document.status == "ARCHIVED":
        raise HTTPException(409, "Tài liệu đã lưu trữ")
    if minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(403, "Không đủ quyền công bố tài liệu ở mức này")
    if effective_from and effective_to and effective_to < effective_from:
        raise HTTPException(422, "PDF_EFFECTIVE_RANGE_INVALID")


async def create_version(db, user, document_id, raw, title, minimum_role, manifest, effective_from, effective_to,
                         *, parsed=None):
    # Access is checked before any parsing or provider call, then re-checked under the lock.
    _check_upload_target(user, await _document(db, document_id, lock=False), minimum_role, effective_from, effective_to)
    try:
        parsed = parsed if parsed is not None else parse_pdf(raw, allow_textless=pdf_structure_ready())
        if manifest is not None:
            drafts, method = sections_from_manifest(raw, parsed.pages, manifest), "MANUAL"
        else:
            structure = await build_sections(raw, parsed.pages)
            drafts, method = structure.sections, structure.method
    except PDFValidationError as exc:
        raise HTTPException(422, exc.code) from exc

    _check_upload_target(user, await _document(db, document_id, lock=True), minimum_role, effective_from, effective_to)
    max_version = await db.scalar(select(func.max(KnowledgeDocumentVersion.version_number)).where(
        KnowledgeDocumentVersion.document_id == document_id
    ))
    storage_key = store_pdf(raw, parsed)
    version = KnowledgeDocumentVersion(
        document_id=document_id, version_number=(max_version or 0) + 1, title=title.strip(),
        minimum_role=minimum_role, status="DRAFT", storage_key=storage_key, sha256=parsed.sha256,
        byte_size=parsed.byte_size, page_count=len(parsed.pages), mime_type=parsed.mime_type,
        effective_from=effective_from, effective_to=effective_to, created_by_user_id=user.user_account_id,
        extraction_method=method,
    )
    db.add(version)
    try:
        await db.flush()
        for draft in drafts:
            db.add(section_row(version.version_id, draft))
        await db.flush()
        # Drafts get lexical chunks for preview; tags and vectors are added on publish.
        await index_version(db, version, version.title, parsed.pages, enrich=False)
        await db.refresh(version)
        await db.commit()
    except Exception:
        delete_pdf(storage_key)
        raise
    return version


# --- draft edits ----------------------------------------------------------

async def locked_draft_version(db, user, document_id, version_id):
    document = await _document(db, document_id, lock=True)
    if not document or document.status == "ARCHIVED":
        raise HTTPException(404, "DOCUMENT_UNAVAILABLE")
    editor_access(user, document)
    version = await _version(db, document_id, version_id)
    if not version or version.minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(404, "DOCUMENT_UNAVAILABLE")
    if version.status != "DRAFT":
        raise HTTPException(409, "PDF_VERSION_IMMUTABLE")
    return version


def _validate_manifest(manifest, page_count) -> None:
    if (not manifest or len(manifest) > MAX_SECTIONS
            or len({section.section_code for section in manifest}) != len(manifest)
            or any(section.page_end < section.page_start or section.page_end > page_count for section in manifest)):
        raise HTTPException(422, "PDF_SECTION_MANIFEST_INVALID")


async def replace_draft_sections(db, version, manifest) -> None:
    raw, parsed = read_version_pdf(version)
    _validate_manifest(manifest, len(parsed.pages))
    if version.extraction_method == "GEMINI_OCR":
        await _edit_ocr_sections(db, version, manifest)
        return
    try:
        drafts = sections_from_manifest(raw, parsed.pages, manifest)
    except PDFValidationError as exc:
        raise HTTPException(422, exc.code) from exc
    # Only DRAFT mappings are replaceable. Published section IDs stay immutable.
    await db.execute(delete(KnowledgeSection).where(KnowledgeSection.version_id == version.version_id))
    for draft in drafts:
        db.add(section_row(version.version_id, draft))
    version.extraction_method = "MANUAL"
    await db.flush()
    await index_version(db, version, version.title, parsed.pages, enrich=False)


async def _edit_ocr_sections(db, version, manifest) -> None:
    """Scanned PDFs have no text layer to re-cut: HR may rename, toggle, re-page or
    remove transcribed sections, but not invent new ones."""
    existing = {row.section_code: row for row in (await db.scalars(select(KnowledgeSection).where(
        KnowledgeSection.version_id == version.version_id))).all()}
    if {section.section_code for section in manifest} - existing.keys():
        raise HTTPException(422, "PDF_SECTION_MANIFEST_INVALID")
    kept = {section.section_code for section in manifest}
    removed = [row.section_id for code, row in existing.items() if code not in kept]
    if removed:
        await db.execute(delete(KnowledgeSection).where(KnowledgeSection.section_id.in_(removed)))
    for section in manifest:
        row = existing[section.section_code]
        heading = section.heading.strip()
        row.heading = row.anchor = heading
        row.is_answerable = section.is_answerable
        row.page_start, row.page_end = section.page_start, section.page_end
        if section.level is not None:
            row.level = section.level
        row.heading_path = section.heading_path or heading
    await db.flush()
    await index_version(db, version, version.title, None, enrich=False)


async def update_draft_version(db, user, document_id, version_id, req):
    version = await locked_draft_version(db, user, document_id, version_id)
    if req.minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(403, "PERMISSION_DENIED")
    if req.sections is not None:
        await replace_draft_sections(db, version, req.sections)
    for key in ("title", "minimum_role", "effective_from", "effective_to"):
        setattr(version, key, getattr(req, key))
    await db.flush()
    await db.refresh(version)
    await db.commit()
    return version


async def update_draft_sections(db, user, document_id, version_id, sections):
    version = await locked_draft_version(db, user, document_id, version_id)
    await replace_draft_sections(db, version, sections)
    await db.flush()
    rows = list((await db.scalars(select(KnowledgeSection).where(KnowledgeSection.version_id == version_id)
                                  .order_by(KnowledgeSection.page_start, KnowledgeSection.section_id))).all())
    await db.commit()
    return rows


# --- publish / activate / unpublish ---------------------------------------

async def publish_version(db, user, document_id, version_id, *, reactivate=False):
    """Publish a DRAFT, or re-activate an ARCHIVED version that was published before.

    A restore-archived draft (never published) cannot be activated; it must go
    through the draft → publish path.
    """
    document = await _document(db, document_id, lock=True)
    if not document or document.status == "ARCHIVED":
        raise HTTPException(404, "Không tìm thấy tài liệu")
    editor_access(user, document)
    version = await _version(db, document_id, version_id)
    expected = "ARCHIVED" if reactivate else "DRAFT"
    if (not version or version.status != expected or not version.storage_key
            or (reactivate and version.published_by_user_id is None)):
        raise HTTPException(404, "Không tìm thấy phiên bản")
    if version.minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(403, "Không đủ quyền công bố tài liệu ở mức này")
    # Re-activated versions are re-verified exactly like a first publication.
    _, parsed = read_version_pdf(version)
    sections = (await db.scalars(select(KnowledgeSection).where(
        KnowledgeSection.version_id == version_id
    ).order_by(KnowledgeSection.page_start, KnowledgeSection.section_id))).all()
    if not sections:
        raise HTTPException(422, "PDF_SECTION_MANIFEST_INVALID")
    for section in sections:
        if not section.page_start or not section.page_end or section.page_end > len(parsed.pages):
            raise HTTPException(422, "PDF_SECTION_MANIFEST_INVALID")
        # Scanned PDFs are checked against their transcription; others against the PDF text.
        excerpt = (section.content if version.extraction_method == "GEMINI_OCR"
                   else "\n".join(parsed.pages[section.page_start - 1:section.page_end]))
        if not excerpt.strip() or not heading_matches(section.heading, excerpt):
            raise HTTPException(422, "PDF_SECTION_HEADING_MISMATCH")
    await archive_published_versions(db, document_id, keep_version_id=version.version_id)
    version.status = "PUBLISHED"
    version.published_by_user_id = user.user_account_id
    document.current_version_id = version.version_id
    document.title = version.title
    document.content = "\n\n".join(section.content for section in sections)
    document.source_url = None
    document.minimum_role = version.minimum_role
    document.status = "PUBLISHED"
    document.updated_by_user_id = user.user_account_id
    await db.flush()
    # Searchable (lexically) as soon as the locks are released.
    await write_lexical_chunks(db, version, version.title, parsed.pages)
    await db.commit()
    await enrich_committed_version(db, version)
    return version


async def unpublish_document(db, user, document_id):
    """Stop using the published version; AI retrieval and viewers stop immediately."""
    document = await _document(db, document_id, lock=True)
    if not document or document.status != "PUBLISHED":
        raise HTTPException(404, "DOCUMENT_UNAVAILABLE")
    editor_access(user, document)
    await archive_published_versions(db, document_id)
    document.current_version_id = None
    document.status = "DRAFT"
    document.updated_by_user_id = user.user_account_id
    await db.flush()
    await db.refresh(document)
    await db.commit()
    return document


async def reindex_version(db, user, document_id, version_id):
    """Rebuild chunks; published versions also get tags and embeddings again."""
    document = await _document(db, document_id, lock=True)
    if not document or document.status == "ARCHIVED":
        raise HTTPException(404, "DOCUMENT_UNAVAILABLE")
    editor_access(user, document)
    version = await _version(db, document_id, version_id)
    if not version or version.status == "ARCHIVED" or version.minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(404, "DOCUMENT_UNAVAILABLE")
    pages = read_version_pdf(version)[1].pages if version.storage_key else None
    await write_lexical_chunks(db, version, version.title, pages)
    await db.refresh(version)
    await db.commit()
    if version.status == "PUBLISHED":
        await enrich_committed_version(db, version)
    return version


# --- archive / restore ----------------------------------------------------

async def archive_document(db, user, document_id):
    document = await _document(db, document_id, lock=True)
    if not document:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    editor_access(user, document)
    document.status = "ARCHIVED"
    document.updated_by_user_id = user.user_account_id
    for version in (await db.scalars(select(KnowledgeDocumentVersion).where(
            KnowledgeDocumentVersion.document_id == document_id))).all():
        version.status = "ARCHIVED"
    await db.flush()
    await db.refresh(document)
    return document


async def restore_document(db, user, document_id):
    document = await _document(db, document_id, lock=True)
    if not document:
        raise HTTPException(404, "DOCUMENT_UNAVAILABLE")
    editor_access(user, document)
    if document.status != "ARCHIVED":
        raise HTTPException(409, "Chỉ khôi phục tài liệu đã lưu trữ")
    source = await db.scalar(select(KnowledgeDocumentVersion).where(
        KnowledgeDocumentVersion.document_id == document_id,
        KnowledgeDocumentVersion.minimum_role.in_(allowed_knowledge_roles(user_roles(user))),
        KnowledgeDocumentVersion.storage_key.is_not(None),
    ).order_by(case((KnowledgeDocumentVersion.version_id == document.current_version_id, 0), else_=1),
               KnowledgeDocumentVersion.version_number.desc()))
    if source:
        max_number = await db.scalar(select(func.max(KnowledgeDocumentVersion.version_number)).where(
            KnowledgeDocumentVersion.document_id == document_id))
        sections = (await db.scalars(select(KnowledgeSection).where(KnowledgeSection.version_id == source.version_id))).all()
        draft = KnowledgeDocumentVersion(
            document_id=document_id, version_number=(max_number or 0) + 1, title=document.title,
            minimum_role=source.minimum_role, status="DRAFT", storage_key=source.storage_key,
            sha256=source.sha256, byte_size=source.byte_size, page_count=source.page_count,
            mime_type=source.mime_type, effective_from=source.effective_from, effective_to=source.effective_to,
            created_by_user_id=user.user_account_id, extraction_method=source.extraction_method,
        )
        db.add(draft)
        await db.flush()
        for section in sections:
            db.add(KnowledgeSection(version_id=draft.version_id, section_code=section.section_code,
                                   heading=section.heading, page_start=section.page_start, page_end=section.page_end,
                                   anchor=section.anchor, content=section.content, is_answerable=section.is_answerable,
                                   level=section.level, heading_path=section.heading_path))
        await db.flush()
        await index_version(db, draft, document.title, None, enrich=False)
        # Normalize historical drafts missed by earlier archive behavior.
        historical = (await db.scalars(select(KnowledgeDocumentVersion).where(
            KnowledgeDocumentVersion.document_id == document_id,
            KnowledgeDocumentVersion.version_id != draft.version_id))).all()
        for version in historical:
            version.status = "ARCHIVED"
    document.status = "DRAFT"
    document.current_version_id = None
    document.updated_by_user_id = user.user_account_id
    await db.flush()
    await db.refresh(document)
    return document
