import re
import hashlib
from datetime import date
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.auth import UserAccount
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSection
from app.schemas.knowledge import KnowledgeRead, KnowledgeWrite, KnowledgeSectionInput, KnowledgeSectionRead, KnowledgeVersionRead, KnowledgeSourceRead, KnowledgeVersionWrite, KnowledgeSectionsWrite
from app.core.config import settings
from app.services.ai_access import allowed_knowledge_roles, user_roles
from app.services.knowledge_storage import PDFValidationError, delete_pdf, parse_pdf, resolve_storage_path, store_pdf
from app.services.ai_request_security import secured_operation

router = APIRouter()
SECTION_INPUTS = TypeAdapter(list[KnowledgeSectionInput])


def _role_can_read(user: UserAccount, document: KnowledgeDocument, version: KnowledgeDocumentVersion) -> bool:
    roles = user_roles(user)
    allowed = allowed_knowledge_roles(roles)
    return document.minimum_role in allowed and version.minimum_role in allowed


def _version_readable(user, document, version, document_id, preview=False):
    if preview and not user_roles(user) & {"HR", "ADMIN"}:
        return False
    if not document or not version or version.document_id != document_id or not _role_can_read(user, document, version):
        return False
    if document.status == "PUBLISHED" and version.status == "PUBLISHED":
        return True
    return preview and document.status != "ARCHIVED" and version.status == "DRAFT" and bool(user_roles(user) & {"HR", "ADMIN"})


def _normalize_heading(value: str) -> str:
    return " ".join(re.sub(r"\s+", " ", value).strip().lower().split())


def _validate_sections(manifest: list[KnowledgeSectionInput], pages: list[str]):
    if not manifest or len(manifest) > 200:
        raise HTTPException(422, "PDF_SECTION_MANIFEST_INVALID")
    seen: set[str] = set()
    result = []
    for section in manifest:
        if (section.section_code in seen or section.page_end < section.page_start
                or section.page_end - section.page_start >= 10 or section.page_end > len(pages)):
            raise HTTPException(422, "PDF_SECTION_MANIFEST_INVALID")
        seen.add(section.section_code)
        page_text = "\n".join(pages[section.page_start - 1:section.page_end]).strip()
        if not page_text or _normalize_heading(section.heading) not in _normalize_heading(page_text):
            raise HTTPException(422, "PDF_SECTION_HEADING_MISMATCH")
        result.append((section, page_text))
    return result


def _editor_access(user: UserAccount, document: KnowledgeDocument):
    roles = user_roles(user)
    allowed = allowed_knowledge_roles(roles)
    if not roles & {"HR", "ADMIN"} or document.minimum_role not in allowed:
        raise HTTPException(404, "Không tìm thấy tài liệu")


@router.get("", response_model=list[KnowledgeRead])
async def list_documents(db: AsyncSession = Depends(get_db), user: UserAccount = Depends(require_roles(["HR"]))):
    return (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.minimum_role.in_(allowed_knowledge_roles(user_roles(user)))).order_by(KnowledgeDocument.document_id.desc()))).scalars().all()


def _automatic_sections(pages: list[str]) -> list[KnowledgeSectionInput]:
    return [KnowledgeSectionInput(
        section_code=f"PAGE_{number}", heading=next(line.strip() for line in page.splitlines() if line.strip())[:300],
        page_start=number, page_end=number,
    ) for number, page in enumerate(pages, 1) if page.strip()]


@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None, max_length=200),
    minimum_role: str = Form("EMPLOYEE"),
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_roles(["HR"])),
):
    async with secured_operation(db, user.user_account_id, "UPLOAD", "UPLOAD", command="KNOWLEDGE_VERSION", rate_limit=False):
        if minimum_role not in allowed_knowledge_roles(user_roles(user)):
            raise HTTPException(403, "PERMISSION_DENIED")
        # Validate before adding any document or storing files.
        raw = await file.read(settings.AI_KNOWLEDGE_MAX_UPLOAD_BYTES + 1)
        try:
            parsed = parse_pdf(raw)
        except PDFValidationError as exc:
            raise HTTPException(422, exc.code) from exc
        name = (title or Path((file.filename or "Tai lieu.pdf").replace("\\", "/")).stem).strip()[:200]
        if not name:
            raise HTTPException(422, "PDF_TITLE_INVALID")
        document = KnowledgeDocument(title=name, content="", minimum_role=minimum_role, status="DRAFT",
                                     document_code=f"DOC-{uuid4().hex}", updated_by_user_id=user.user_account_id)
        db.add(document)
        await db.flush()
        version = await _upload_version(document.document_id, file, name, minimum_role, None, None, None,
                                        db, user, parsed_pdf=parsed, raw_pdf=raw)
        await db.refresh(document)
        return {"document": KnowledgeRead.model_validate(document), "version": KnowledgeVersionRead.model_validate(version)}


@router.get("/{document_id}", response_model=KnowledgeRead)
async def read_document(document_id: int, db: AsyncSession = Depends(get_db), user: UserAccount = Depends(get_current_user)):
    document = await db.get(KnowledgeDocument, document_id)
    roles = user_roles(user)
    if not document or document.minimum_role not in allowed_knowledge_roles(roles) or (document.status != "PUBLISHED" and not roles & {"ADMIN", "HR"}):
        raise HTTPException(404, "Không tìm thấy tài liệu")
    return document


@router.post("", response_model=KnowledgeRead, status_code=201)
async def create_document(req: KnowledgeWrite, db: AsyncSession = Depends(get_db), user: UserAccount = Depends(require_roles(["HR"]))):
    if req.minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(403, "Không đủ quyền công bố tài liệu ở mức này")
    data = req.model_dump()
    data["source_url"] = str(req.source_url) if req.source_url else None
    document = KnowledgeDocument(
        **data,
        document_code=f"DOC-{uuid4().hex}",
        updated_by_user_id=user.user_account_id,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)
    return document


@router.put("/{document_id}", response_model=KnowledgeRead)
async def update_document(document_id: int, req: KnowledgeWrite, db: AsyncSession = Depends(get_db), user: UserAccount = Depends(require_roles(["HR"]))):
    document = await db.get(KnowledgeDocument, document_id)
    if not document or document.minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(404, "Không tìm thấy tài liệu")
    if req.minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(403, "Không đủ quyền công bố tài liệu ở mức này")
    if document.current_version_id or document.status == "PUBLISHED":
        raise HTTPException(409, "Tài liệu đã công bố không thể ghi đè; hãy tạo phiên bản mới hoặc lưu trữ tài liệu")
    for key, value in req.model_dump().items():
        setattr(document, key, str(value) if key == "source_url" and value else value)
    document.updated_by_user_id = user.user_account_id
    await db.flush()
    await db.refresh(document)
    return document


@router.post("/{document_id}/versions", response_model=KnowledgeVersionRead, status_code=201)
async def upload_version(
    document_id: int,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=200),
    minimum_role: str = Form(...),
    sections_json: str | None = Form(None, max_length=30000),
    effective_from: date | None = Form(None),
    effective_to: date | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_roles(["HR"])),
):
    async with secured_operation(db, user.user_account_id, "UPLOAD", "UPLOAD", command="KNOWLEDGE_VERSION", rate_limit=False):
        return await _upload_version(document_id, file, title, minimum_role, sections_json, effective_from, effective_to, db, user)


async def _upload_version(document_id, file, title, minimum_role, sections_json, effective_from, effective_to, db, user, *, parsed_pdf=None, raw_pdf=None):
    document = await db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id).with_for_update())
    if not document:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    _editor_access(user, document)
    if document.status == "ARCHIVED":
        raise HTTPException(409, "Tài liệu đã lưu trữ")
    allowed_roles = allowed_knowledge_roles(user_roles(user))
    if minimum_role not in allowed_roles:
        raise HTTPException(403, "Không đủ quyền công bố tài liệu ở mức này")
    if effective_from and effective_to and effective_to < effective_from:
        raise HTTPException(422, "PDF_EFFECTIVE_RANGE_INVALID")
    manifest = None
    if sections_json is not None:
        try:
            manifest = SECTION_INPUTS.validate_json(sections_json)
        except ValidationError as exc:
            raise HTTPException(422, "PDF_SECTION_MANIFEST_INVALID") from exc

    raw = raw_pdf if raw_pdf is not None else await file.read(settings.AI_KNOWLEDGE_MAX_UPLOAD_BYTES + 1)
    try:
        parsed = parsed_pdf if parsed_pdf is not None else parse_pdf(raw)
        verified_sections = _validate_sections(manifest if manifest is not None else _automatic_sections(parsed.pages), parsed.pages)
    except PDFValidationError as exc:
        raise HTTPException(422, exc.code) from exc

    max_version = await db.scalar(select(func.max(KnowledgeDocumentVersion.version_number)).where(
        KnowledgeDocumentVersion.document_id == document_id
    ))
    storage_key = store_pdf(raw, parsed)
    version = KnowledgeDocumentVersion(
        document_id=document_id,
        version_number=(max_version or 0) + 1,
        title=title.strip(),
        minimum_role=minimum_role,
        status="DRAFT",
        storage_key=storage_key,
        sha256=parsed.sha256,
        byte_size=parsed.byte_size,
        page_count=len(parsed.pages),
        mime_type=parsed.mime_type,
        effective_from=effective_from,
        effective_to=effective_to,
        created_by_user_id=user.user_account_id,
    )
    db.add(version)
    try:
        await db.flush()
        for section, content in verified_sections:
            db.add(KnowledgeSection(
                version_id=version.version_id,
                section_code=section.section_code,
                heading=section.heading.strip(),
                page_start=section.page_start,
                page_end=section.page_end,
                anchor=section.heading.strip(),
                content=content,
                is_answerable=section.is_answerable,
            ))
        await db.flush()
        await db.refresh(version)
        await db.commit()
    except Exception:
        delete_pdf(storage_key)
        raise
    return version


@router.get("/{document_id}/versions", response_model=list[KnowledgeVersionRead])
async def list_versions(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_roles(["HR"])),
):
    document = await db.get(KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    _editor_access(user, document)
    return (await db.scalars(select(KnowledgeDocumentVersion).where(
        KnowledgeDocumentVersion.document_id == document_id,
        KnowledgeDocumentVersion.minimum_role.in_(allowed_knowledge_roles(user_roles(user))),
    ).order_by(KnowledgeDocumentVersion.version_number.desc()))).all()


async def _locked_draft_version(db, user, document_id, version_id):
    document = await db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id).with_for_update())
    if not document or document.status == "ARCHIVED":
        raise HTTPException(404, "DOCUMENT_UNAVAILABLE")
    _editor_access(user, document)
    version = await db.scalar(select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.document_id == document_id, KnowledgeDocumentVersion.version_id == version_id).with_for_update())
    if not version or version.minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(404, "DOCUMENT_UNAVAILABLE")
    if version.status != "DRAFT":
        raise HTTPException(409, "PDF_VERSION_IMMUTABLE")
    return version


async def _replace_draft_sections(db, version, manifest):
    try:
        parsed = parse_pdf(resolve_storage_path(version.storage_key or "").read_bytes())
    except (FileNotFoundError, OSError, PDFValidationError) as exc:
        raise HTTPException(409, "PDF_FILE_UNAVAILABLE") from exc
    if parsed.sha256 != version.sha256 or len(parsed.pages) != version.page_count:
        raise HTTPException(409, "PDF_INTEGRITY_MISMATCH")
    verified = _validate_sections(manifest, parsed.pages)
    # Only DRAFT mappings are replaceable. Published section IDs stay immutable.
    await db.execute(delete(KnowledgeSection).where(KnowledgeSection.version_id == version.version_id))
    for section, content in verified:
        db.add(KnowledgeSection(version_id=version.version_id, section_code=section.section_code, heading=section.heading, page_start=section.page_start, page_end=section.page_end, anchor=section.heading, content=content, is_answerable=section.is_answerable))


@router.put("/{document_id}/versions/{version_id}", response_model=KnowledgeVersionRead)
async def update_draft_version(document_id: int, version_id: int, req: KnowledgeVersionWrite, db: AsyncSession = Depends(get_db), user: UserAccount = Depends(require_roles(["HR"]))):
    async with secured_operation(db, user.user_account_id, "KNOWLEDGE", "PUBLISH", command="EDIT_DRAFT", rate_limit=False):
        version = await _locked_draft_version(db, user, document_id, version_id)
        if req.minimum_role not in allowed_knowledge_roles(user_roles(user)):
            raise HTTPException(403, "PERMISSION_DENIED")
        if req.sections is not None:
            await _replace_draft_sections(db, version, req.sections)
        for key in ("title", "minimum_role", "effective_from", "effective_to"):
            setattr(version, key, getattr(req, key))
        await db.flush()
        await db.refresh(version)
        await db.commit()
        return version


@router.put("/{document_id}/versions/{version_id}/sections", response_model=list[KnowledgeSectionRead])
async def update_draft_sections(document_id: int, version_id: int, req: KnowledgeSectionsWrite, db: AsyncSession = Depends(get_db), user: UserAccount = Depends(require_roles(["HR"]))):
    async with secured_operation(db, user.user_account_id, "KNOWLEDGE", "PUBLISH", command="EDIT_DRAFT_SECTIONS", rate_limit=False):
        version = await _locked_draft_version(db, user, document_id, version_id)
        await _replace_draft_sections(db, version, req.sections)
        await db.flush()
        sections = list((await db.scalars(select(KnowledgeSection).where(KnowledgeSection.version_id == version_id).order_by(KnowledgeSection.page_start, KnowledgeSection.section_id))).all())
        await db.commit()
        return sections


@router.post("/{document_id}/versions/{version_id}/publish", response_model=KnowledgeVersionRead)
async def publish_version(
    document_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_roles(["HR"])),
):
    async with secured_operation(db, user.user_account_id, "KNOWLEDGE", "PUBLISH", command="KNOWLEDGE_VERSION", rate_limit=False):
        return await _publish_version(document_id, version_id, db, user)


async def _publish_version(document_id, version_id, db, user):
    document = await db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id).with_for_update())
    if not document or document.status == "ARCHIVED":
        raise HTTPException(404, "Không tìm thấy tài liệu")
    _editor_access(user, document)
    version = await db.scalar(select(KnowledgeDocumentVersion).where(
        KnowledgeDocumentVersion.version_id == version_id,
        KnowledgeDocumentVersion.document_id == document_id,
    ).with_for_update())
    if not version or version.status != "DRAFT" or not version.storage_key:
        raise HTTPException(404, "Không tìm thấy phiên bản")
    if version.minimum_role not in allowed_knowledge_roles(user_roles(user)):
        raise HTTPException(403, "Không đủ quyền công bố tài liệu ở mức này")
    try:
        path = resolve_storage_path(version.storage_key)
        parsed = parse_pdf(path.read_bytes())
    except (FileNotFoundError, PDFValidationError, OSError) as exc:
        raise HTTPException(409, "PDF_FILE_UNAVAILABLE") from exc
    if parsed.sha256 != version.sha256 or len(parsed.pages) != version.page_count:
        raise HTTPException(409, "PDF_INTEGRITY_MISMATCH")
    sections = (await db.scalars(select(KnowledgeSection).where(
        KnowledgeSection.version_id == version_id
    ).order_by(KnowledgeSection.page_start, KnowledgeSection.section_id))).all()
    if not sections:
        raise HTTPException(422, "PDF_SECTION_MANIFEST_INVALID")
    for section in sections:
        if not section.page_start or not section.page_end or section.page_end > len(parsed.pages):
            raise HTTPException(422, "PDF_SECTION_MANIFEST_INVALID")
        excerpt = "\n".join(parsed.pages[section.page_start - 1:section.page_end])
        if not excerpt.strip() or _normalize_heading(section.heading) not in _normalize_heading(excerpt):
            raise HTTPException(422, "PDF_SECTION_HEADING_MISMATCH")
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
    await db.refresh(version)
    await db.commit()
    return version


@router.post("/{document_id}/archive", response_model=KnowledgeRead)
async def archive_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_roles(["HR"])),
):
    document = await db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id).with_for_update())
    if not document:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    _editor_access(user, document)
    document.status = "ARCHIVED"
    document.updated_by_user_id = user.user_account_id
    if document.current_version_id:
        versions = (await db.scalars(select(KnowledgeDocumentVersion).where(
            KnowledgeDocumentVersion.document_id == document_id
        ))).all()
        for version in versions:
            version.status = "ARCHIVED"
    await db.flush()
    await db.refresh(document)
    return document


@router.get("/{document_id}/versions/{version_id}/sections", response_model=list[KnowledgeSectionRead])
async def read_version_sections(
    document_id: int,
    version_id: int,
    preview: bool = False,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(get_current_user),
):
    document = await db.get(KnowledgeDocument, document_id)
    version = await db.get(KnowledgeDocumentVersion, version_id)
    if not _version_readable(user, document, version, document_id, preview):
        raise HTTPException(404, "Không tìm thấy nguồn tài liệu")
    statement = select(KnowledgeSection).where(KnowledgeSection.version_id == version_id)
    if not preview:
        statement = statement.where(KnowledgeSection.is_answerable.is_(True))
    return (await db.scalars(statement.order_by(KnowledgeSection.page_start, KnowledgeSection.section_id))).all()


@router.get("/{document_id}/versions/{version_id}/sections/{section_id}", response_model=KnowledgeSourceRead)
async def read_source_reference(
    document_id: int,
    version_id: int,
    section_id: int,
    preview: bool = False,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(get_current_user),
):
    roles = user_roles(user)
    allowed = allowed_knowledge_roles(roles)
    if preview and not roles & {"HR", "ADMIN"}:
        raise HTTPException(404, "DOCUMENT_UNAVAILABLE")
    stmt = select(KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSection).join(
        KnowledgeDocumentVersion, KnowledgeDocumentVersion.document_id == KnowledgeDocument.document_id
    ).join(KnowledgeSection, KnowledgeSection.version_id == KnowledgeDocumentVersion.version_id).where(
        KnowledgeDocument.document_id == document_id,
        KnowledgeDocumentVersion.version_id == version_id,
        KnowledgeSection.section_id == section_id,
        KnowledgeDocument.minimum_role.in_(allowed),
        KnowledgeDocumentVersion.minimum_role.in_(allowed),
    )
    if not preview:
        stmt = stmt.where(KnowledgeDocument.status == "PUBLISHED", KnowledgeDocumentVersion.status == "PUBLISHED", KnowledgeSection.is_answerable.is_(True))
    result = (await db.execute(stmt)).one_or_none()
    if not result:
        raise HTTPException(404, "Không tìm thấy nguồn tài liệu")
    document, version, section = result
    if not _version_readable(user, document, version, document_id, preview):
        raise HTTPException(404, "Không tìm thấy nguồn tài liệu")
    if not section.page_start or not section.page_end:
        raise HTTPException(404, "Không tìm thấy nguồn PDF")
    return KnowledgeSourceRead(
        document_id=document_id,
        version_id=version_id,
        section_id=section_id,
        title=version.title,
        section_code=section.section_code,
        heading=section.heading,
        page_start=section.page_start,
        page_end=section.page_end,
        anchor=section.anchor,
    )


@router.get("/{document_id}/versions/{version_id}/file")
async def read_version_file(
    document_id: int,
    version_id: int,
    preview: bool = False,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(get_current_user),
):
    document = await db.get(KnowledgeDocument, document_id)
    version = await db.get(KnowledgeDocumentVersion, version_id)
    if not _version_readable(user, document, version, document_id, preview) or not version.storage_key:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    try:
        path = resolve_storage_path(version.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(404, "PDF_FILE_UNAVAILABLE") from exc
    if not path.is_file():
        raise HTTPException(404, "PDF_FILE_UNAVAILABLE")
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest() != version.sha256:
            raise HTTPException(404, "PDF_FILE_UNAVAILABLE")
    except OSError as exc:
        raise HTTPException(404, "PDF_FILE_UNAVAILABLE") from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="reference.pdf",
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )
