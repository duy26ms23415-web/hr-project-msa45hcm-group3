"""Rebuild hybrid-RAG chunks for published knowledge versions; dry run unless --apply.

Use after enabling embeddings/rule tagging or after upgrading from lexical-only
retrieval. Legacy text documents (no PDF version) are lexical-only and skipped.
"""

import argparse
import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentVersion
from app.services.knowledge_ingest.pipeline import index_version
from app.services.knowledge_storage import PDFValidationError, parse_pdf, resolve_storage_path


async def reindex(apply: bool, only_missing: bool):
    async with AsyncSessionLocal() as db:
        statement = select(KnowledgeDocumentVersion).join(
            KnowledgeDocument, KnowledgeDocument.current_version_id == KnowledgeDocumentVersion.version_id
        ).where(KnowledgeDocument.status == "PUBLISHED", KnowledgeDocumentVersion.status == "PUBLISHED")
        if only_missing:
            statement = statement.where(KnowledgeDocumentVersion.index_status != "READY")
        versions = (await db.scalars(statement.order_by(KnowledgeDocumentVersion.version_id))).all()
        for version in versions:
            if not apply:
                print(f"Would reindex version {version.version_id} ({version.index_status}): {version.title}")
                continue
            pages = None
            if version.storage_key:
                try:
                    raw = resolve_storage_path(version.storage_key).read_bytes()
                    pages = parse_pdf(raw, allow_textless=version.extraction_method == "GEMINI_OCR").pages
                except (FileNotFoundError, OSError, PDFValidationError):
                    print(f"Skipped version {version.version_id}: PDF file unavailable")
                    continue
            await index_version(db, version, version.title, pages, enrich=True)
            await db.commit()
            print(f"Reindexed version {version.version_id}: {version.index_status}")
        print(f"{'Processed' if apply else 'Found'} {len(versions)} published version(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only-missing", action="store_true", help="skip versions already indexed with embeddings")
    arguments = parser.parse_args()
    asyncio.run(reindex(arguments.apply, arguments.only_missing))
