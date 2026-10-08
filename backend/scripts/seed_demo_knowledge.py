"""Idempotently load local draft knowledge PDFs into the private storage/database."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models.auth import UserAccount
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSection
from app.services.knowledge_storage import delete_pdf, parse_pdf, store_pdf


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "storage" / "tmp" / "ai-knowledge-demo" / "manifest.json"


async def seed(creator_user_id: int) -> None:
    if settings.ENVIRONMENT.lower() not in {"development", "test"}:
        raise SystemExit("Demo seed is allowed only when ENVIRONMENT=development or test.")
    if not MANIFEST_PATH.is_file():
        raise SystemExit("Demo PDFs are missing; run generate_demo_knowledge.py first.")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("status") != "DRAFT_ONLY":
        raise SystemExit("Unexpected manifest status; refusing to seed.")
    created_storage_keys: list[str] = []
    try:
        async with AsyncSessionLocal() as db:
            user = await db.scalar(select(UserAccount).where(
                UserAccount.user_account_id == creator_user_id,
                UserAccount.is_active.is_(True),
            ))
            if not user:
                raise SystemExit("Creator user account was not found or is inactive.")

            for item in manifest["documents"]:
                pdf_path = MANIFEST_PATH.parent / item["file"]
                raw = pdf_path.read_bytes()
                parsed = parse_pdf(raw)
                if parsed.sha256 != item.get("sha256"):
                    raise SystemExit(f"PDF checksum mismatch: {item['file']}")
                document = await db.scalar(select(KnowledgeDocument).where(
                    KnowledgeDocument.document_code == item["document_code"]
                ).with_for_update())
                if document:
                    same_version = await db.scalar(select(KnowledgeDocumentVersion).where(
                        KnowledgeDocumentVersion.document_id == document.document_id,
                        KnowledgeDocumentVersion.sha256 == parsed.sha256,
                    ))
                    if same_version:
                        print(f"Already seeded: {item['document_code']}")
                        continue
                    raise SystemExit(f"Document exists with different content; refusing overwrite: {item['document_code']}")

                document = KnowledgeDocument(
                    document_code=item["document_code"],
                    title=item["title"],
                    content="Draft PDF awaits HR review and publication.",
                    source_url=item.get("source_url"),
                    status="DRAFT",
                    minimum_role="EMPLOYEE",
                    updated_by_user_id=creator_user_id,
                )
                db.add(document)
                await db.flush()
                storage_key = store_pdf(raw, parsed)
                created_storage_keys.append(storage_key)
                version = KnowledgeDocumentVersion(
                    document_id=document.document_id,
                    version_number=1,
                    title=item["title"],
                    minimum_role="EMPLOYEE",
                    status="DRAFT",
                    storage_key=storage_key,
                    sha256=parsed.sha256,
                    byte_size=parsed.byte_size,
                    page_count=len(parsed.pages),
                    mime_type=parsed.mime_type,
                    created_by_user_id=creator_user_id,
                )
                db.add(version)
                await db.flush()
                for section in item["sections"]:
                    page_text = "\n".join(parsed.pages[section["page_start"] - 1:section["page_end"]])
                    db.add(KnowledgeSection(
                        version_id=version.version_id,
                        section_code=section["section_code"],
                        heading=section["heading"],
                        page_start=section["page_start"],
                        page_end=section["page_end"],
                        anchor=section["heading"],
                        content=page_text,
                        is_answerable=True,
                    ))
                print(f"Added DRAFT: {item['document_code']} ({len(parsed.pages)} pages)")
            await db.commit()
    except BaseException:
        for storage_key in created_storage_keys:
            delete_pdf(storage_key)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--creator-user-id", type=int, required=True, help="Existing active user account ID for audit fields")
    parser.add_argument("--confirm-demo-seed", action="store_true", help="Required explicit confirmation; creates draft rows")
    args = parser.parse_args()
    if not args.confirm_demo_seed:
        parser.error("pass --confirm-demo-seed to create local draft knowledge records")
    try:
        asyncio.run(seed(args.creator_user_id))
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
