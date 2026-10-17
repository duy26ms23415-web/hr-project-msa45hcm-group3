"""Hybrid retrieval: permission filters in every branch, RRF fusion, fallbacks."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.ai.providers.gemini import ProviderFailure
from app.services import ai_knowledge_tool, knowledge_search
from app.services.ai_knowledge_tool import AIKnowledgeTool

TODAY = date(2026, 10, 16)


def row(chunk_id, section_id, content, heading="Nghỉ phép", rule_type="INFO"):
    return {"chunk_id": chunk_id, "section_id": section_id, "version_id": 2, "document_id": 1, "title": "Nội quy",
            "content": content, "normalized_text": knowledge_search.normalize(heading + "\n" + content),
            "page_start": 3, "page_end": 3, "rule_type": rule_type, "applies_to": ["LEAVE"],
            "section_code": f"S{section_id}", "heading": heading, "score": 1.0}


def result(rows):
    return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))


def compiled(statement):
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class Branches:
    """Route each SQL branch to its own rows, recording every statement."""
    def __init__(self, fts=(), trgm=(), vec=()):
        self.rows = {"fts": list(fts), "trgm": list(trgm), "vec": list(vec)}
        self.statements = []
        self.settings = []

    async def __call__(self, statement):
        sql = compiled(statement)
        if "set_config" in sql:
            self.settings.append(sql)
            return result([])
        self.statements.append(statement)
        if "ts_rank_cd" in sql:
            return result(self.rows["fts"])
        if "word_similarity" in sql:
            return result(self.rows["trgm"])
        return result(self.rows["vec"])


@pytest.mark.asyncio
async def test_every_branch_filters_permissions_and_publication_in_sql(monkeypatch):
    monkeypatch.setattr(knowledge_search, "embeddings_ready", lambda: True)
    monkeypatch.setattr(knowledge_search, "embed_texts", AsyncMock(return_value=[[0.1] * 768]))
    db = AsyncMock()
    branches = Branches()
    db.execute.side_effect = branches.__call__
    await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, ["nghỉ phép năm"], embed_queries=["nghỉ phép năm"])
    assert len(branches.statements) == 3  # fts, trigram, vector
    for statement in branches.statements:
        sql = compiled(statement)
        assert "hr_ai_knowledge_documents.minimum_role IN ('EMPLOYEE')" in sql
        assert "hr_ai_knowledge_document_versions.minimum_role IN ('EMPLOYEE')" in sql
        assert "hr_ai_knowledge_documents.status = 'PUBLISHED'" in sql
        assert "hr_ai_knowledge_document_versions.status = 'PUBLISHED'" in sql
        assert "is_answerable IS true" in sql
        assert "current_version_id" in sql


@pytest.mark.asyncio
async def test_rrf_prefers_chunks_found_by_several_branches_and_cites_each_section_once():
    annual = row(10, 100, "Nhân viên được nghỉ phép năm 12 ngày.")
    annual_tail = row(11, 100, "Nghỉ phép năm phải báo trước 3 ngày.")
    remote = row(20, 200, "Làm việc từ xa tối đa 2 ngày mỗi tuần.", heading="Làm việc từ xa")
    db = AsyncMock()
    db.execute.side_effect = Branches(fts=[remote, annual, annual_tail], trgm=[annual]).__call__
    passages = await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, ["nghỉ phép năm bao nhiêu ngày"])
    assert passages[0].chunk_id == 10
    assert [p.section_id for p in passages].count(100) == 1


@pytest.mark.asyncio
async def test_full_text_only_hit_needs_real_word_overlap():
    noise = row(30, 300, "Nhân viên mặc đồng phục khi làm việc.", heading="Trang phục")
    db = AsyncMock()
    db.execute.side_effect = Branches(fts=[noise]).__call__
    assert await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, ["nhân viên được nghỉ phép năm bao nhiêu ngày"]) == []


@pytest.mark.asyncio
async def test_follow_up_and_rule_preferences_boost_ranking():
    first = row(10, 100, "Nghỉ phép năm được tính theo năm làm việc.")
    second = row(20, 200, "Không được nghỉ phép năm quá 5 ngày liên tục.", rule_type="PROHIBITION")
    db = AsyncMock()
    db.execute.side_effect = Branches(fts=[first, second], trgm=[first, second]).__call__
    plain = await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, ["nghỉ phép năm"])
    assert plain[0].section_id == 100
    db.execute.side_effect = Branches(fts=[first, second], trgm=[first, second]).__call__
    preferred = await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, ["nghỉ phép năm"],
                                                     prefer_rule_types=("PROHIBITION",))
    assert preferred[0].section_id == 200
    db.execute.side_effect = Branches(fts=[first, second], trgm=[first, second]).__call__
    boosted = await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, ["nghỉ phép năm"], boost_section_ids=[200])
    assert boosted[0].section_id == 200


@pytest.mark.asyncio
async def test_vector_branch_finds_paraphrases_and_embeds_only_masked_queries(monkeypatch):
    monkeypatch.setattr(knowledge_search, "embeddings_ready", lambda: True)
    embed = AsyncMock(return_value=[[0.2] * 768])
    monkeypatch.setattr(knowledge_search, "embed_texts", embed)
    wedding = row(40, 400, "Người lao động kết hôn được nghỉ việc riêng 3 ngày hưởng nguyên lương.", heading="Nghỉ việc riêng")
    db = AsyncMock()
    db.execute.side_effect = Branches(vec=[wedding]).__call__
    passages = await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, ["cuoi vo dc nghi may hom"],
                                                    embed_queries=["[người] cưới vợ được nghỉ mấy hôm"])
    assert [p.chunk_id for p in passages] == [40]
    assert embed.await_args.args[1] == ["[người] cưới vợ được nghỉ mấy hôm"]
    assert embed.await_args.args[2] == "RETRIEVAL_QUERY"


@pytest.mark.asyncio
async def test_embedding_failure_keeps_lexical_results(monkeypatch):
    monkeypatch.setattr(knowledge_search, "embeddings_ready", lambda: True)
    monkeypatch.setattr(knowledge_search, "embed_texts", AsyncMock(side_effect=ProviderFailure("QUOTA_EXCEEDED")))
    annual = row(10, 100, "Nhân viên được nghỉ phép năm 12 ngày.")
    db = AsyncMock()
    branches = Branches(fts=[annual], trgm=[annual])
    db.execute.side_effect = branches.__call__
    passages = await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, ["nghỉ phép năm"], embed_queries=["nghỉ phép năm"])
    assert [p.chunk_id for p in passages] == [10]
    assert len(branches.statements) == 2


@pytest.mark.asyncio
async def test_disabled_embeddings_make_no_provider_call(monkeypatch):
    embed = AsyncMock()
    monkeypatch.setattr(knowledge_search, "embed_texts", embed)
    db = AsyncMock()
    db.execute.side_effect = Branches().__call__
    await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, ["nghỉ phép"], embed_queries=["nghỉ phép"])
    embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_merges_unindexed_documents_but_not_for_rule_filters(monkeypatch):
    chunk_passage = knowledge_search._passage(row(10, 100, "Nghỉ phép năm 12 ngày."))
    monkeypatch.setattr(ai_knowledge_tool, "hybrid_search", AsyncMock(return_value=[chunk_passage]))
    legacy = [{"document_id": 5, "title": "Quy định cũ", "content": "Nghỉ phép năm được duyệt bởi quản lý.",
               "status": "PUBLISHED", "is_answerable": True, "version_id": None, "section_id": None}]
    documents = AsyncMock(return_value=legacy)
    monkeypatch.setattr(AIKnowledgeTool, "documents", documents)
    merged = await AIKnowledgeTool.search(AsyncMock(), {"EMPLOYEE"}, TODAY, ["nghỉ phép năm"], limit=3)
    assert [p.document_id for p in merged] == [1, 5]
    assert documents.await_args.kwargs == {"unindexed_only": True}
    filtered = await AIKnowledgeTool.search(AsyncMock(), {"EMPLOYEE"}, TODAY, ["nghỉ phép năm"], limit=3,
                                            rule_types=("PROHIBITION",))
    assert [p.document_id for p in filtered] == [1]


@pytest.mark.asyncio
async def test_unindexed_documents_query_excludes_chunked_versions():
    db = AsyncMock()
    db.execute.return_value = result([])
    await AIKnowledgeTool.documents(db, {"EMPLOYEE"}, TODAY, unindexed_only=True)
    sql = compiled(db.execute.await_args.args[0])
    assert "NOT (EXISTS" in sql and "hr_ai_knowledge_chunks" in sql


@pytest.mark.asyncio
async def test_trigram_branch_keeps_the_users_own_question_and_uses_the_index_operator(monkeypatch):
    monkeypatch.setattr(knowledge_search, "embeddings_ready", lambda: False)
    db = AsyncMock()
    branches = Branches()
    db.execute.side_effect = branches.__call__
    rewrites = ["nghỉ phép năm", "số ngày phép", "phép tồn", "em còn mấy ngày phép"]
    await knowledge_search.hybrid_search(db, {"EMPLOYEE"}, TODAY, rewrites)
    trigram = [compiled(s) for s in branches.statements if "word_similarity" in compiled(s)]
    assert len(trigram) == 3
    assert any("'em con may ngay phep' <%" in sql for sql in trigram)
    assert all("<%" in sql for sql in trigram)
    assert branches.settings and "pg_trgm.word_similarity_threshold" in branches.settings[0]
