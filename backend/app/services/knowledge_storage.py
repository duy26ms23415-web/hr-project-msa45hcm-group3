"""Validated PDF ingestion and private, server-generated file storage."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader

from app.core.config import settings


MAX_PDF_PAGES = 100
MAX_EXTRACTED_CHARS = 1_500_000
STORAGE_KEY_RE = re.compile(r"^[a-f0-9]{32}\.pdf$")
FORBIDDEN_PDF_ACTIONS = {"/JavaScript", "/Launch", "/GoToR", "/URI", "/SubmitForm", "/ImportData", "/RichMedia"}


class PDFValidationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ParsedPDF:
    pages: list[str]
    sha256: str
    byte_size: int
    mime_type: str = "application/pdf"


def _object(value):
    return value.get_object() if hasattr(value, "get_object") else value


def _contains_forbidden_action(value, seen: set[int] | None = None) -> bool:
    """Inspect the entire object graph, including forms and outline actions."""
    if seen is None:
        seen = set()
    pending = [value]
    while pending:
        value = _object(pending.pop())
        ident = id(value)
        if ident in seen:
            continue
        seen.add(ident)
        if hasattr(value, "get"):
            if str(_object(value.get("/S"))) in FORBIDDEN_PDF_ACTIONS:
                return True
            if any(key in value for key in ("/JavaScript", "/JS", "/EmbeddedFiles", "/EF", "/AF", "/RichMedia", "/XFA")):
                return True
            # Traverse all dictionary children: /AcroForm, /Fields, /Outlines,
            # event dictionaries and indirect references can hide active content.
            pending.extend(value.values())
        elif isinstance(value, (list, tuple)):
            pending.extend(value)
    return False


def parse_pdf(data: bytes, max_bytes: int | None = None) -> ParsedPDF:
    limit = max_bytes or settings.AI_KNOWLEDGE_MAX_UPLOAD_BYTES
    if not data or len(data) > limit:
        raise PDFValidationError("PDF_SIZE_INVALID")
    if not data.startswith(b"%PDF-"):
        raise PDFValidationError("PDF_MIME_INVALID")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise PDFValidationError("PDF_ENCRYPTED")
        root = _object(reader.trailer["/Root"])
        if _contains_forbidden_action(root) or any(_contains_forbidden_action(page) for page in reader.pages):
            raise PDFValidationError("PDF_ACTIVE_CONTENT")
        pages = reader.pages
        if not 1 <= len(pages) <= MAX_PDF_PAGES:
            raise PDFValidationError("PDF_PAGE_LIMIT")
        extracted = [(page.extract_text() or "").strip() for page in pages]
        if not any(extracted):
            raise PDFValidationError("PDF_TEXT_REQUIRED")
        if sum(map(len, extracted)) > MAX_EXTRACTED_CHARS:
            raise PDFValidationError("PDF_TEXT_LIMIT")
    except PDFValidationError:
        raise
    except Exception as exc:
        raise PDFValidationError("PDF_INVALID") from exc
    return ParsedPDF(extracted, hashlib.sha256(data).hexdigest(), len(data))


def _storage_root() -> Path:
    root = Path(settings.AI_KNOWLEDGE_STORAGE_DIR).expanduser().resolve()
    return root


def resolve_storage_path(storage_key: str) -> Path:
    if not STORAGE_KEY_RE.fullmatch(storage_key):
        raise FileNotFoundError("Invalid storage key")
    root = _storage_root()
    candidate = (root / storage_key).resolve()
    if candidate.parent != root:
        raise FileNotFoundError("Invalid storage key")
    return candidate


def store_pdf(data: bytes, parsed: ParsedPDF | None = None) -> str:
    if parsed is None:
        parse_pdf(data)
    root = _storage_root()
    root.mkdir(parents=True, exist_ok=True)
    storage_key = f"{uuid4().hex}.pdf"
    destination = resolve_storage_path(storage_key)
    descriptor, staging_name = tempfile.mkstemp(prefix=".staging-", suffix=".pdf", dir=root)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging_name, destination)
    except Exception:
        try:
            os.unlink(staging_name)
        except FileNotFoundError:
            pass
        raise
    return storage_key


def delete_pdf(storage_key: str) -> None:
    path = resolve_storage_path(storage_key)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
