"""Document-only rules warn on drafts (never block); rule tags; embeddings; indexing."""
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.ai.providers import gemini
from app.ai.providers.gemini import ProviderFailure
from app.services import ai_policy_guard
from app.services.ai_policy_guard import _Finding, _Verdict, action_facts, check_action
from app.services.knowledge_ingest import pipeline, rule_tagger
from app.services.knowledge_ingest.rule_tagger import _Label, _Labels, tag_chunks
from app.services.knowledge_retrieval import Passage

TODAY = date(2026, 10, 16)
RULE = Passage(document_id=1, title="Nội quy", content="Nghỉ phép năm phải báo trước ít nhất 3 ngày làm việc.",
               source_url=None, version_id=2, section_id=3, heading="Điều 3", page_start=4, page_end=4,
               rule_type="OBLIGATION")
LEAVE = {"leave_date": "2026-10-17", "session": "FULL_DAY", "leave_type_id": 1, "reason": "Việc riêng của Nguyễn Văn An"}


def session(events=None):
    """AsyncSession stand-in whose begin_nested() is an async context manager that records its outcome."""
    events = [] if events is None else events

    class Savepoint:
        async def __aenter__(self):
            events.append("savepoint")

        async def __aexit__(self, exc_type, exc, tb):
            events.append("rollback" if exc_type else "release")
            return False
    db = AsyncMock()
    db.begin_nested = Mock(side_effect=lambda: Savepoint())
    return db


@pytest.fixture
def guard(monkeypatch):
    monkeypatch.setattr(ai_policy_guard, "tagging_ready", lambda: True)
    search = AsyncMock(return_value=[RULE])
    monkeypatch.setattr(ai_policy_guard.AIKnowledgeTool, "search", search)
    generate = AsyncMock()
    monkeypatch.setattr(ai_policy_guard, "generate_json", generate)
    return search, generate


def test_action_facts_are_enums_and_numbers_only():
    facts, domains, _ = action_facts("DRAFT_LEAVE", LEAVE, TODAY, "ANNUAL")
    assert facts == {"action": "LEAVE_REQUEST", "leave_type": "ANNUAL", "session": "FULL_DAY",
                     "duration_days": 1, "lead_days": 1, "weekday": "SATURDAY"}
    assert domains == ["LEAVE"]
    assert action_facts("DRAFT_LEAVE", LEAVE, TODAY, "REMOTE")[1] == ["REMOTE"]


@pytest.mark.asyncio
async def test_conflict_becomes_cited_warning_and_provider_never_sees_reason(guard):
    search, generate = guard
    generate.return_value = _Verdict(verdict="CONFLICT", findings=[_Finding(
        source=1, rule="Phải báo trước ít nhất 3 ngày làm việc",
        evidence="phải báo trước ít nhất 3 ngày làm việc", reason="Đơn chỉ báo trước 1 ngày")])
    warnings = await check_action(session(), {"EMPLOYEE"}, TODAY, "DRAFT_LEAVE", LEAVE, "ANNUAL")
    assert [w.severity for w in warnings] == ["CONFLICT"]
    assert warnings[0].source.viewer_path == "/knowledge/view/1?version=2&section=3"
    assert warnings[0].source.excerpt == "phải báo trước ít nhất 3 ngày làm việc"
    prompt = generate.await_args.args[1]
    assert "Nguyễn Văn An" not in prompt and "Việc riêng" not in prompt and "leave_type_id" not in prompt
    assert search.await_args.kwargs["rule_types"] == ("PROHIBITION", "OBLIGATION")
    assert search.await_args.kwargs["domains"] == ["LEAVE"]


@pytest.mark.asyncio
@pytest.mark.parametrize("finding", [
    _Finding(source=1, rule="Phải báo trước 3 ngày", evidence="câu không có trong quy định", reason="x"),
    _Finding(source=1, rule="Phải báo trước 7 ngày", evidence="báo trước ít nhất 3 ngày", reason="x"),
    _Finding(source=1, rule="Phải báo trước 3 ngày", evidence="báo trước ít nhất 3 ngày", reason="Thiếu 9 ngày"),
])
async def test_forged_evidence_or_invented_numbers_are_dropped(guard, finding):
    _, generate = guard
    generate.return_value = _Verdict(verdict="CONFLICT", findings=[finding])
    assert await check_action(session(), {"EMPLOYEE"}, TODAY, "DRAFT_LEAVE", LEAVE, "ANNUAL") == []


@pytest.mark.asyncio
async def test_provider_failure_marks_draft_unchecked_but_does_not_block(guard):
    _, generate = guard
    generate.side_effect = ProviderFailure("PROVIDER_TIMEOUT")
    warnings = await check_action(session(), {"EMPLOYEE"}, TODAY, "DRAFT_FIX",
                                  {"work_date": "2026-10-15", "event_type": "CHECK_OUT", "requested_time": "17:30", "reason": "x"})
    assert [w.severity for w in warnings] == ["UNCHECKED"]


@pytest.mark.asyncio
async def test_guard_is_off_without_rule_tagging(monkeypatch):
    monkeypatch.setattr(ai_policy_guard, "tagging_ready", lambda: False)
    search = AsyncMock()
    monkeypatch.setattr(ai_policy_guard.AIKnowledgeTool, "search", search)
    assert await check_action(session(), {"EMPLOYEE"}, TODAY, "DRAFT_LEAVE", LEAVE, "ANNUAL") == []
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_ready_leave_draft_carries_warnings_and_is_still_returned(monkeypatch):
    from app.services.ai_draft_service import AIDraftService
    from app.services.ai_service import AIService
    from app.schemas.ai import AIPolicyWarning
    draft = SimpleNamespace(draft_id="d1", command="DRAFT_LEAVE", typed_params=LEAVE, missing_fields=[], revision=1, status="COLLECTING")
    monkeypatch.setattr(AIDraftService, "get_draft", AsyncMock(return_value=draft))
    monkeypatch.setattr(AIDraftService, "mark_ready", AsyncMock())
    monkeypatch.setattr(AIService, "_leave_preflight", AsyncMock(return_value=None))
    monkeypatch.setattr(AIService, "get_employee_context", AsyncMock(return_value={
        "leave_types": [{"id": 1, "code": "ANNUAL", "name": "Phép năm"}], "remaining_leave_days": "5"}))
    warning = AIPolicyWarning(severity="CONFLICT", message="Phải báo trước 3 ngày — Đơn chỉ báo trước 1 ngày")
    check = AsyncMock(return_value=[warning])
    monkeypatch.setattr("app.services.ai_service.check_action", check)
    response = await AIService._continue_draft(AsyncMock(), 9, "d1", "", 7)
    assert response.action.action_type == "DRAFT_LEAVE"
    assert response.policy_warnings == [warning]
    assert "quản lý trực tiếp là người quyết định" in response.reply
    assert check.await_args.args[1] == {"EMPLOYEE"}


@pytest.mark.asyncio
async def test_guard_sql_runs_in_a_savepoint_and_the_provider_call_outside_it(guard, monkeypatch):
    from app.services.ai_service import AIService
    search, generate = guard
    events = []
    generate.side_effect = lambda *a, **k: events.append("provider") or _Verdict(verdict="OK", findings=[])
    assert await check_action(session(events), {"EMPLOYEE"}, TODAY, "DRAFT_LEAVE", LEAVE, "ANNUAL") == []
    assert events == ["savepoint", "release", "provider"]
    events.clear()
    search.side_effect = RuntimeError("SQL failed")
    warnings = await AIService._policy_warnings(session(events), None, "DRAFT_LEAVE", LEAVE, "ANNUAL", today=TODAY)
    assert events == ["savepoint", "rollback"]  # The draft's transaction stays usable for mark_ready.
    assert [warning.severity for warning in warnings] == ["UNCHECKED"]


@pytest.mark.asyncio
async def test_rule_tags_are_closed_and_default_when_tagging_is_off(monkeypatch):
    assert await tag_chunks([("Điều 3", "Nghiêm cấm chấm công hộ.")]) == [("INFO", ["GENERAL"])]
    monkeypatch.setattr(rule_tagger, "tagging_ready", lambda: True)
    monkeypatch.setattr(rule_tagger, "generate_json", AsyncMock(return_value=_Labels(items=[
        _Label(id=0, rule_type="PROHIBITION", applies_to=["ATTENDANCE", "CONDUCT"]),
        _Label(id=7, rule_type="PERMISSION", applies_to=["LEAVE"]),  # unknown id ignored
    ])))
    labels = await tag_chunks([("Điều 3", "Nghiêm cấm chấm công hộ."), ("Điều 4", "Thông tin chung.")])
    assert labels == [("PROHIBITION", ["ATTENDANCE", "CONDUCT"]), ("INFO", ["GENERAL"])]
    with pytest.raises(ValueError):
        _Label(id=0, rule_type="ALLOW_EVERYTHING", applies_to=["LEAVE"])


@pytest.mark.asyncio
async def test_embed_texts_batches_normalizes_and_validates(monkeypatch):
    monkeypatch.setattr(gemini.settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_API_KEY", "test-key")
    calls = []

    async def embed_content(model, contents, config):
        calls.append((model, len(contents), config.task_type, config.output_dimensionality))
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0]) for _ in contents])

    client = SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))

    class Aio:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_):
            return None

    monkeypatch.setattr(gemini.genai, "Client", lambda **kw: SimpleNamespace(aio=Aio()))
    vectors = await gemini.embed_texts("test", ["x"] * 150, "RETRIEVAL_DOCUMENT", dimensions=2)
    assert len(vectors) == 150 and vectors[0] == [0.6, 0.8]
    assert [call[1] for call in calls] == [100, 50]
    assert calls[0][2:] == ("RETRIEVAL_DOCUMENT", 2)
    with pytest.raises(ProviderFailure) as error:
        await gemini.embed_texts("test", ["x"], "RETRIEVAL_QUERY", dimensions=3)
    assert error.value.category == "INVALID_PROVIDER_RESPONSE"


@pytest.mark.asyncio
async def test_embeddings_are_opt_in(monkeypatch):
    monkeypatch.setattr(gemini.settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini.settings, "GEMINI_EMBEDDINGS_ENABLED", False)
    with pytest.raises(ProviderFailure) as error:
        await gemini.embed_texts("test", ["x"], "RETRIEVAL_QUERY", dimensions=768)
    assert error.value.category == "PROVIDER_DISABLED"


@pytest.mark.asyncio
async def test_index_version_chunks_tags_and_embeds_on_publish(monkeypatch):
    from app.models.knowledge import KnowledgeChunk
    section = SimpleNamespace(section_id=3, heading="Điều 3. Nghỉ phép", heading_path="Chương II > Điều 3. Nghỉ phép",
                              content="Điều 3. Nghỉ phép\n" + "Nhân viên được nghỉ 12 ngày phép năm. " * 40,
                              page_start=4, page_end=4)
    empty = SimpleNamespace(section_id=4, heading="Chương III", heading_path="Chương III", content="Chương III",
                            page_start=5, page_end=5)
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(all=lambda: [section, empty])
    db.add = Mock()
    monkeypatch.setattr(pipeline, "tag_chunks", AsyncMock(side_effect=lambda items: [("PERMISSION", ["LEAVE"])] * len(items)))
    monkeypatch.setattr(pipeline, "embeddings_ready", lambda: True)
    embed = AsyncMock(side_effect=lambda op, texts, task, dimensions: [[0.0] * dimensions for _ in texts])
    monkeypatch.setattr(pipeline, "embed_texts", embed)
    version = SimpleNamespace(version_id=2, index_status="PENDING", embedding_model=None)
    await pipeline.index_version(db, version, "Nội quy", None, enrich=True)
    chunks = [call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], KnowledgeChunk)]
    assert chunks and {chunk.section_id for chunk in chunks} == {3}  # bare chapter title skipped
    assert chunks[0].contextual_text.startswith("Nội quy > Chương II > Điều 3. Nghỉ phép\n")
    assert all(chunk.rule_type == "PERMISSION" and chunk.embedding for chunk in chunks)
    assert version.index_status == "READY"
    assert embed.await_args.args[2] == "RETRIEVAL_DOCUMENT"
    embed.side_effect = ProviderFailure("QUOTA_EXCEEDED")
    await pipeline.index_version(db, version, "Nội quy", None, enrich=True)
    assert version.index_status == "LEXICAL_ONLY"
    await pipeline.index_version(db, version, "Nội quy", None, enrich=False)
    assert version.index_status == "PENDING"
    assert json.dumps(chunks[0].applies_to) == '["LEAVE"]'
