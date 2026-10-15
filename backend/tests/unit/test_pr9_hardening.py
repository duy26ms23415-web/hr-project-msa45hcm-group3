"""Regression tests for the PR #9 review follow-ups."""
import asyncio
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


def test_google_egress_features_are_opt_in_by_default():
    defaults = Settings()
    assert defaults.GEMINI_SEMANTIC_ENABLED is False
    assert defaults.GEMINI_PUBLIC_SEARCH_ENABLED is False
    # A single fallback call must fit well inside the whole chat budget.
    assert defaults.GEMINI_PUBLIC_SEARCH_TIMEOUT_SECONDS < defaults.AI_CHAT_TIMEOUT_SECONDS


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
