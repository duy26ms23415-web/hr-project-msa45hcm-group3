"""Regression tests for the PR #9 review follow-ups."""
import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from app.ai.providers import gemini
from app.core.authorization import has_hr_role
from app.core.config import Settings
from app.services.ai_public_knowledge import public_question
from app.services.report_service import ReportService


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


def fake_client(response):
    client = SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock(return_value=response)))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    class Ctx:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *exc):
            return False
    return client, Ctx()


def enable(monkeypatch):
    monkeypatch.setattr(gemini.settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_PUBLIC_SEARCH_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_API_KEY", "test-key")


def declared_default(name):
    # Read the declared default, not Settings(), which also reads .env and the
    # process environment and would make this test depend on a developer's setup.
    return Settings.model_fields[name].default


def test_google_egress_features_are_opt_in_by_default():
    assert declared_default("GEMINI_SEMANTIC_ENABLED") is False
    assert declared_default("GEMINI_PUBLIC_SEARCH_ENABLED") is False
    # A single fallback call must fit well inside the whole chat budget.
    assert declared_default("GEMINI_PUBLIC_SEARCH_TIMEOUT_SECONDS") < declared_default("AI_CHAT_TIMEOUT_SECONDS")


@pytest.mark.parametrize("value", ["10", "30", "45"])
def test_existing_public_search_timeout_values_still_start(monkeypatch, value):
    monkeypatch.setenv("GEMINI_PUBLIC_SEARCH_TIMEOUT_SECONDS", value)
    assert Settings().GEMINI_PUBLIC_SEARCH_TIMEOUT_SECONDS == float(value)


def test_budget_caps_each_call_to_remaining_time():
    assert gemini.budgeted_timeout(15) == 15  # no request deadline: unchanged
    with gemini.request_deadline(6):
        capped = gemini.budgeted_timeout(15)
        assert capped is not None and capped <= 5
    with gemini.request_deadline(1.5):
        assert gemini.budgeted_timeout(15) is None


@pytest.mark.asyncio
async def test_exhausted_budget_skips_provider_call(monkeypatch):
    enable(monkeypatch)
    client, ctx = fake_client(SimpleNamespace(text='{"ok": true}'))
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=ctx))
    with gemini.request_deadline(0.5):
        with pytest.raises(gemini.ProviderFailure) as json_error:
            await gemini.generate_json("t", "p", "i", Answer, timeout=15, max_tokens=8)
        with pytest.raises(gemini.ProviderFailure) as search_error:
            await gemini.generate_search_answer("p", "i")
    assert json_error.value.category == search_error.value.category == "PROVIDER_TIMEOUT"
    client.models.generate_content.assert_not_called()


@pytest.mark.asyncio
async def test_sequential_calls_share_one_budget(monkeypatch):
    enable(monkeypatch)
    seen = []

    async def fake_wait_for(coro, timeout):
        seen.append(timeout)
        coro.close()
        await asyncio.sleep(0)
        raise asyncio.TimeoutError()

    client, ctx = fake_client(None)
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=ctx))
    monkeypatch.setattr(gemini.asyncio, "wait_for", fake_wait_for)
    with gemini.request_deadline(8):
        for _ in range(2):
            with pytest.raises(gemini.ProviderFailure):
                await gemini.generate_json("t", "p", "i", Answer, timeout=15, max_tokens=8)
    assert all(timeout <= 7 for timeout in seen)


@pytest.mark.parametrize("message", [
    "Nguyen Van A nghỉ phép bao nhiêu ngày?",
    "Trần Thị Bình được nghỉ mấy ngày",
    "chị Le Thi Hoa xin nghỉ thai sản",
])
def test_public_search_masks_accented_and_unaccented_names(message):
    masked = public_question(message)
    assert "[person]" in masked
    assert not any(name in masked for name in ("Nguyen Van", "Trần Thị", "Le Thi"))


@pytest.mark.parametrize("message", [
    "Ngày lễ Tết được nghỉ mấy ngày?",
    "Do Bộ luật Lao động quy định thời giờ làm việc thế nào?",
])
def test_public_search_keeps_ordinary_legal_wording(message):
    assert public_question(message) == message


def test_general_rbac_does_not_raise_ai_errors_for_non_ai_roles():
    # KIOSK accounts are valid HR users but have no AI capabilities.
    assert has_hr_role({"KIOSK"}, {"HR", "ADMIN"}) is False
    assert has_hr_role({"KIOSK", "HR"}, {"HR"}) is True
    assert has_hr_role({"ADMIN"}, {"HR"}) is True


def actor(*roles):
    return SimpleNamespace(employee_id=7, role_assignments=[
        SimpleNamespace(role=SimpleNamespace(role_code=role)) for role in roles])


@pytest.mark.asyncio
async def test_approval_queue_report_requires_direct_report_capability():
    with pytest.raises(HTTPException) as error:
        await ReportService.visible_employee_ids(None, actor("EMPLOYEE"), "APPROVAL_QUEUE", None, None)
    assert error.value.status_code == 403


# --- Name masking: casing variants and false positives (review of 4b433d1) ---

@pytest.mark.parametrize("message,kept", [
    ("nguyen van a nghi phep", "nghi phep"),
    ("Nguyen van a", ""),
    ("Nguyễn văn an", ""),
    ("NGUYEN VAN A", ""),
    ("pham thi lan", ""),
    ("Nguyễn Văn An xin nghỉ", "xin nghỉ"),
    ("Nguyễn Thị Thu Hà nghỉ thai sản", "nghỉ thai sản"),
    ("huynh minh tuan co duoc nghi", "co duoc nghi"),
])
def test_names_masked_in_any_case_without_eating_the_question(message, kept):
    masked = public_question(message)
    assert masked.startswith("[person]")
    assert masked.removeprefix("[person]").strip() == kept


@pytest.mark.parametrize("message", [
    "đang thanh toán lương", "dang thanh toan luong",
    "phân công công việc", "phan cong cong viec", "phân vân nên nghỉ",
    "ngay le tet", "hồ sơ nghỉ việc", "ho so nghi viec",
    "mức trần đóng bảo hiểm", "muc tran dong bao hiem",
    "định kỳ khám sức khỏe", "vụ việc tranh chấp", "thời gian thử việc của Nguyễn",
])
def test_ordinary_hr_and_legal_wording_is_not_masked(message):
    assert public_question(message) == message


# --- Grounding URL lookups stay inside the shared chat budget ---

from app.services import ai_public_knowledge as public_module  # noqa: E402

REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"


def grounded_response(url):
    text = "Điều kiện được quy định trong văn bản hiện hành."
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason="STOP", grounding_metadata=SimpleNamespace(
        grounding_chunks=[SimpleNamespace(web=SimpleNamespace(uri=url, title="Văn bản"))],
        grounding_supports=[SimpleNamespace(segment=SimpleNamespace(text=text), grounding_chunk_indices=[0])],
        search_entry_point=None))])


@pytest.fixture
def fast_budget(monkeypatch):
    # Shrink the safety margins so budget behaviour is testable in well under a second.
    monkeypatch.setattr(gemini, "_DEADLINE_MARGIN_SECONDS", 0.05)
    monkeypatch.setattr(gemini, "_MIN_CALL_SECONDS", 0.1)
    monkeypatch.setattr(public_module.settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(public_module.settings, "GEMINI_PUBLIC_SEARCH_ENABLED", True)


def slow_redirect(monkeypatch, delay):
    calls = []

    async def slow_get(self, url, *args, **kwargs):
        calls.append(url)
        await asyncio.sleep(delay)
        raise AssertionError("redirect lookup should have been cut off by the budget")
    monkeypatch.setattr(public_module.httpx.AsyncClient, "get", slow_get)
    return calls


@pytest.mark.asyncio
async def test_slow_redirect_is_cut_off_at_remaining_budget(monkeypatch, fast_budget):
    calls = slow_redirect(monkeypatch, delay=10)

    async def slow_gemini(*args):
        await asyncio.sleep(0.2)  # a slow but successful search answer
        return grounded_response(REDIRECT)
    monkeypatch.setattr(public_module, "generate_search_answer", slow_gemini)
    loop = asyncio.get_running_loop()
    started = loop.time()
    with gemini.request_deadline(0.6):
        answer = await public_module.answer_public_question("quy định thai sản", date(2026, 10, 15))
    # Budget 0.6s; allow slack for one-off TLS setup on slow CI, far below the 10s redirect.
    assert loop.time() - started < 1.0
    assert calls == [REDIRECT]
    assert answer is None  # unverifiable citation -> normal internal fallback, not a 503


@pytest.mark.asyncio
async def test_spent_budget_skips_redirect_lookup_but_keeps_official_links(monkeypatch, fast_budget):
    calls = slow_redirect(monkeypatch, delay=10)

    async def gemini_uses_whole_budget(*args):
        await asyncio.sleep(0.3)
        return grounded_response("https://vanban.chinhphu.vn/law")
    monkeypatch.setattr(public_module, "generate_search_answer", gemini_uses_whole_budget)
    with gemini.request_deadline(0.35):
        answer = await public_module.answer_public_question("quy định thai sản", date(2026, 10, 15))
    assert calls == []  # no network once the budget is gone
    assert answer.external_sources[0].url == "https://vanban.chinhphu.vn/law"


@pytest.mark.asyncio
async def test_many_slow_redirects_share_one_deadline(monkeypatch):
    slow_redirect(monkeypatch, delay=10)
    clients = []
    real_client = public_module.httpx.AsyncClient

    def counting_client(**kwargs):
        clients.append(kwargs)
        return real_client(**kwargs)
    monkeypatch.setattr(public_module.httpx, "AsyncClient", counting_client)
    loop = asyncio.get_running_loop()
    started = loop.time()
    links = await public_module.resolve_source_urls([f"{REDIRECT}{i}" for i in range(8)] + ["https://moj.gov.vn/x"], 0.3)
    assert loop.time() - started < 0.8  # one shared 0.3s deadline, not 8 x 0.3s
    assert links == [None] * 8 + ["https://moj.gov.vn/x"]
    assert len(clients) == 1
