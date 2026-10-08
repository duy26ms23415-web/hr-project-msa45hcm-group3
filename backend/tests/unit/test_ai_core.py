from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import configure_mappers
from app.services.ai_access import allowed_knowledge_roles, user_roles
from app.services.knowledge_retrieval import retrieve
from app.models.knowledge import AIChatDraft, KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSection, ReportRun


def document(document_id=1, status="PUBLISHED", content="Giờ làm việc từ 08:00 đến 17:00. Nghỉ trưa từ 12:00 đến 13:00."):
    return SimpleNamespace(document_id=document_id, title="Giờ làm việc", content=content, source_url=None, status=status)


def test_employee_never_receives_privileged_knowledge_roles():
    assert allowed_knowledge_roles({"EMPLOYEE"}) == ["EMPLOYEE"]
    with pytest.raises(HTTPException) as missing:
        allowed_knowledge_roles(set())
    assert missing.value.status_code == 403
    with pytest.raises(HTTPException) as unknown:
        allowed_knowledge_roles({"UNKNOWN"})
    assert unknown.value.status_code == 403


def test_higher_roles_and_multiple_roles():
    assert allowed_knowledge_roles({"EMPLOYEE", "MANAGER"}) == ["EMPLOYEE", "MANAGER"]
    assert allowed_knowledge_roles({"HR"}) == ["EMPLOYEE", "MANAGER", "HR"]
    assert allowed_knowledge_roles({"ADMIN"}) == ["EMPLOYEE", "MANAGER", "HR", "ADMIN"]


def test_roles_are_read_from_server_assignments():
    user = SimpleNamespace(role_assignments=[SimpleNamespace(role=SimpleNamespace(role_code="EMPLOYEE"))], roles=["ADMIN"])
    assert user_roles(user) == {"EMPLOYEE"}


def test_retrieval_handles_vietnamese_accents():
    result = retrieve("gio lam viec va nghi trua", [document()])
    assert result and result[0].document_id == 1
    assert "08:00" in result[0].content


def test_draft_and_archived_documents_are_never_retrieved():
    assert retrieve("giờ làm việc", [document(status="DRAFT"), document(status="ARCHIVED")]) == []


def test_unrelated_question_and_empty_query_have_no_sources():
    assert retrieve("lập trình python thuật toán", [document()]) == []
    assert retrieve("", [document()]) == []


def test_retrieval_is_bounded_and_verbatim():
    docs = [document(i) for i in range(10)]
    result = retrieve("giờ làm việc", docs)
    assert len(result) == 3
    assert all(p.content in docs[p.document_id].content for p in result)


def test_copilot_state_models_preserve_legacy_knowledge_and_private_ownership_fields():
    configure_mappers()
    assert "content" in KnowledgeDocument.__table__.columns
    assert KnowledgeDocument.__table__.columns["document_code"].unique
    assert KnowledgeDocumentVersion.__table__.columns["storage_key"].nullable
    assert KnowledgeSection.__table__.columns["page_start"].nullable
    assert "owner_user_account_id" in AIChatDraft.__table__.columns
    assert "expires_at" in AIChatDraft.__table__.columns
    assert "scope_snapshot" in ReportRun.__table__.columns
    assert "storage_key" in ReportRun.__table__.columns



def test_retrieval_requires_matching_passage_content_not_only_title():
    assert retrieve("gio lam viec", [document(content="Quy trinh bao mat thong tin nhan vien.")]) == []
    content = "x" * 1200 + " Gio lam viec tu 08:00 den 17:00."
    result = retrieve("gio lam viec", [document(content=content)])
    assert result and all("08:00" in p.content for p in result)


def test_history_and_response_share_a_bounded_reply_limit():
    from pydantic import ValidationError
    from app.schemas.ai import AIChatMessage, AIChatResponse, MAX_AI_REPLY_CHARS
    reply = AIChatResponse(reply="x" * MAX_AI_REPLY_CHARS)
    assert AIChatMessage(role="assistant", content=reply.reply).content == reply.reply
    with pytest.raises(ValidationError):
        AIChatMessage(role="assistant", content="x" * (MAX_AI_REPLY_CHARS + 1))
    with pytest.raises(ValidationError):
        AIChatResponse(reply="x" * (MAX_AI_REPLY_CHARS + 1))
