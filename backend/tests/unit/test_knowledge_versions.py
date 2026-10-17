"""Only one published version per document: publish, re-activate, unpublish."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.api.deps import get_current_user
from app.api.v1.endpoints import knowledge
from app.services import knowledge_versions
from app.core.database import get_db

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


@pytest.fixture
def api(monkeypatch):
    from app.services import ai_request_security
    monkeypatch.setattr(ai_request_security, "consume_budget", AsyncMock())
    monkeypatch.setattr(ai_request_security, "record_event", AsyncMock())
    app = FastAPI()
    app.include_router(knowledge.router, prefix="/ai/knowledge")
    user = SimpleNamespace(employee_id=7, user_account_id=9, role_assignments=[SimpleNamespace(role=SimpleNamespace(role_code="HR"))])
    db = AsyncMock()
    db.add = Mock()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return app, db


def document(status="PUBLISHED", current=2):
    return SimpleNamespace(document_id=1, document_code="DOC-1", title="Nội quy", content="x", source_url=None,
                           status=status, minimum_role="EMPLOYEE", current_version_id=current, updated_at=NOW)


def version(version_id, status, published_by=None):
    return SimpleNamespace(version_id=version_id, document_id=1, version_number=version_id, title=f"Nội quy v{version_id}",
                           minimum_role="EMPLOYEE", status=status, storage_key="a" * 32 + ".pdf", sha256="hash",
                           byte_size=10, page_count=1, mime_type="application/pdf", effective_from=None,
                           effective_to=None, created_at=NOW, extraction_method="LAYOUT", index_status="READY",
                           embedding_model=None, published_by_user_id=published_by)


def sql(call):
    return str(call.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.fixture
def verified_pdf(monkeypatch):
    monkeypatch.setattr(knowledge_versions, "read_version_pdf", lambda v: (b"pdf", SimpleNamespace(pages=["Điều 1. Nghỉ phép\nNội dung"])))
    monkeypatch.setattr(knowledge_versions, "write_lexical_chunks", AsyncMock())
    monkeypatch.setattr(knowledge_versions, "enrich_in_background", AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,source_status", [("publish", "DRAFT"), ("activate", "ARCHIVED")])
async def test_publishing_any_version_archives_the_other_published_one(api, verified_pdf, endpoint, source_status):
    app, db = api
    doc, target = document(current=2), version(1, source_status, published_by=9 if source_status == "ARCHIVED" else None)
    db.scalar.side_effect = [doc, target]
    section = SimpleNamespace(heading="Điều 1. Nghỉ phép", page_start=1, page_end=1, content="Điều 1. Nghỉ phép\nNội dung")
    db.scalars.return_value = SimpleNamespace(all=lambda: [section])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/ai/knowledge/1/versions/1/{endpoint}")
    assert response.status_code == 200, response.text
    assert target.status == "PUBLISHED" and doc.current_version_id == 1 and doc.status == "PUBLISHED"
    archive = next(sql(call) for call in db.execute.await_args_list if "UPDATE" in sql(call))
    assert "SET status='ARCHIVED'" in archive
    assert "document_id = 1" in archive and "status = 'PUBLISHED'" in archive and "version_id != 1" in archive


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,wrong_status", [("publish", "ARCHIVED"), ("activate", "DRAFT"), ("activate", "PUBLISHED")])
async def test_each_endpoint_only_accepts_its_own_source_status(api, verified_pdf, endpoint, wrong_status):
    app, db = api
    db.scalar.side_effect = [document(), version(1, wrong_status)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/ai/knowledge/1/versions/1/{endpoint}")
    assert response.status_code == 404
    assert not any("UPDATE" in sql(call) for call in db.execute.await_args_list)


@pytest.mark.asyncio
async def test_reactivation_rechecks_the_stored_file(api, monkeypatch):
    from fastapi import HTTPException
    app, db = api
    target = version(1, "ARCHIVED", published_by=9)
    db.scalar.side_effect = [document(), target]

    def tampered(_):
        raise HTTPException(409, "PDF_INTEGRITY_MISMATCH")

    monkeypatch.setattr(knowledge_versions, "read_version_pdf", tampered)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ai/knowledge/1/versions/1/activate")
    assert response.status_code == 409 and target.status == "ARCHIVED"


@pytest.mark.asyncio
async def test_unpublish_stops_ai_use_and_keeps_versions_for_later(api):
    app, db = api
    doc = document()
    db.scalar.return_value = doc
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ai/knowledge/1/unpublish")
        assert response.status_code == 200
        assert doc.status == "DRAFT" and doc.current_version_id is None
        assert "SET status='ARCHIVED'" in sql(db.execute.await_args_list[-1])
        doc.status = "DRAFT"
        assert (await client.post("/ai/knowledge/1/unpublish")).status_code == 404


def test_database_allows_only_one_published_version_per_document():
    from app.models.knowledge import KnowledgeDocumentVersion
    index = next(i for i in KnowledgeDocumentVersion.__table__.indexes if i.name == "uq_ai_knowledge_one_published_version")
    assert index.unique and [c.name for c in index.columns] == ["document_id"]
    assert "PUBLISHED" in str(index.dialect_options["postgresql"]["where"])


@pytest.mark.asyncio
async def test_activate_rejects_an_archived_version_that_was_never_published(api, verified_pdf):
    app, db = api
    target = version(1, "ARCHIVED")  # e.g. a draft archived by restore
    db.scalar.side_effect = [document(), target]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ai/knowledge/1/versions/1/activate")
    assert response.status_code == 404 and target.status == "ARCHIVED"


@pytest.mark.asyncio
async def test_publish_commits_before_slow_enrichment(api, monkeypatch):
    app, db = api
    order = []
    monkeypatch.setattr(knowledge_versions, "read_version_pdf", lambda v: (b"pdf", SimpleNamespace(pages=["Điều 1. Nghỉ phép\nNội dung"])))
    monkeypatch.setattr(knowledge_versions, "write_lexical_chunks", AsyncMock(side_effect=lambda *a: order.append("lexical")))
    db.commit.side_effect = lambda: order.append("commit")
    monkeypatch.setattr(knowledge_versions, "enrich_in_background", AsyncMock(side_effect=lambda *a: order.append("enrich")))
    db.scalar.side_effect = [document(), version(1, "DRAFT")]
    section = SimpleNamespace(heading="Điều 1. Nghỉ phép", page_start=1, page_end=1, content="Điều 1. Nghỉ phép\nNội dung")
    db.scalars.return_value = SimpleNamespace(all=lambda: [section])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/ai/knowledge/1/versions/1/publish")).status_code == 200
    # Provider work (tags/embeddings) starts only after the row locks are released,
    # in a background task so a large document cannot time out the request.
    assert order == ["lexical", "commit", "enrich"]


@pytest.mark.asyncio
async def test_background_enrichment_uses_its_own_session_and_never_raises(monkeypatch):
    from contextlib import asynccontextmanager
    import app.core.database as database
    published, draft = version(1, "PUBLISHED"), version(2, "DRAFT")
    session = AsyncMock()
    session.get.side_effect = lambda model, version_id: {1: published, 2: draft}.get(version_id)

    @asynccontextmanager
    async def factory():
        yield session
    monkeypatch.setattr(database, "AsyncSessionLocal", factory)
    enrich = AsyncMock()
    monkeypatch.setattr(knowledge_versions, "enrich_committed_version", enrich)
    await knowledge_versions.enrich_in_background(1)
    await knowledge_versions.enrich_in_background(2)  # no longer published: skipped
    assert [call.args for call in enrich.await_args_list] == [(session, published)]
    enrich.side_effect = RuntimeError("provider down")
    session.commit.reset_mock()
    await knowledge_versions.enrich_in_background(1)  # logged, not raised
    marked = sql(session.execute.await_args_list[-1])
    assert "index_status='FAILED'" in marked and "index_status = 'PENDING'" in marked
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_enrichment_leaves_a_newer_rebuild_alone(monkeypatch):
    from app.services.knowledge_ingest import pipeline
    rows = [SimpleNamespace(chunk_id=1, contextual_text="Nội quy\nx", content="x")]
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(all=lambda: rows)
    db.scalars.return_value = SimpleNamespace(all=lambda: [7])  # chunks rebuilt while the provider worked
    monkeypatch.setattr(pipeline, "_enrichment", AsyncMock(return_value=([("PERMISSION", ["LEAVE"])], [[0.0]])))
    target = SimpleNamespace(version_id=2, index_status="PENDING", embedding_model=None)
    await pipeline.enrich_committed_version(db, target)
    assert db.execute.await_count == 1 and target.index_status == "PENDING"  # no chunk or status writes
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


def _ocr_version():
    return SimpleNamespace(version_id=2, storage_key="k.pdf", sha256="hash", page_count=3,
                           extraction_method="GEMINI_OCR", title="Scan")


def _ocr_rows():
    return [SimpleNamespace(section_id=10 + i, section_code=f"S{i}", heading=f"H{i}", anchor=f"H{i}", is_answerable=True,
                            page_start=i, page_end=i, level=1, heading_path=f"H{i}") for i in (1, 2, 3)]


@pytest.mark.asyncio
async def test_ocr_draft_edit_removes_missing_sections_and_applies_pages(monkeypatch):
    from app.schemas.knowledge import KnowledgeSectionInput
    monkeypatch.setattr(knowledge_versions, "read_version_pdf", lambda v: (b"pdf", SimpleNamespace(pages=["a", "b", "c"])))
    monkeypatch.setattr(knowledge_versions, "index_version", AsyncMock())
    rows = _ocr_rows()
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(all=lambda: rows)
    await knowledge_versions.replace_draft_sections(db, _ocr_version(), [
        KnowledgeSectionInput(section_code="S1", heading="Điều 1", page_start=1, page_end=2),
        KnowledgeSectionInput(section_code="S3", heading="Điều 3", page_start=3, page_end=3, is_answerable=False),
    ])
    removed = sql(db.execute.await_args_list[0])
    assert "DELETE" in removed and "12" in removed and "11" not in removed and "13" not in removed
    assert (rows[0].heading, rows[0].page_end) == ("Điều 1", 2)
    assert rows[2].is_answerable is False


@pytest.mark.asyncio
@pytest.mark.parametrize("sections", [
    [("S1", 1, 1), ("S1", 2, 2)],      # duplicate codes
    [("S1", 2, 4)],                    # beyond the PDF
    [("S9", 1, 1)],                    # invented section on a scan
    [(f"S{i}", 1, 1) for i in range(201)],  # over the 200-section limit
])
async def test_ocr_draft_edit_rejects_invalid_manifests_before_writing(monkeypatch, sections):
    from fastapi import HTTPException
    from app.schemas.knowledge import KnowledgeSectionInput
    monkeypatch.setattr(knowledge_versions, "read_version_pdf", lambda v: (b"pdf", SimpleNamespace(pages=["a", "b", "c"])))
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(all=_ocr_rows)
    manifest = [KnowledgeSectionInput(section_code=code, heading="H", page_start=start, page_end=end)
                for code, start, end in sections]
    with pytest.raises(HTTPException) as exc:
        await knowledge_versions.replace_draft_sections(db, _ocr_version(), manifest)
    assert exc.value.status_code == 422
    db.execute.assert_not_called()
