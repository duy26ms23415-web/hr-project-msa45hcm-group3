import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ConfigDict

from app.ai.providers import gemini


def test_gemini_model_env_precedence(tmp_path, monkeypatch):
    """Runtime model comes from .env, with backend and deploy overrides."""
    from app.core.config import Settings

    monkeypatch.delenv("GEMINI_MODEL_NAME", raising=False)
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text("GEMINI_MODEL_NAME=gemini-root-test\n", encoding="utf-8")
    backend_env.write_text("GEMINI_MODEL_NAME=gemini-backend-test\n", encoding="utf-8")

    configured = Settings(_env_file=(root_env, backend_env))
    assert configured.GEMINI_MODEL_NAME == "gemini-backend-test"

    monkeypatch.setenv("GEMINI_MODEL_NAME", "gemini-deploy-test")
    assert Settings(_env_file=(root_env, backend_env)).GEMINI_MODEL_NAME == "gemini-deploy-test"


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


def test_provider_failure_diagnostic_is_visible_at_warning_level(caplog):
    caplog.set_level(logging.WARNING)
    gemini.record("interpret_chat_request", "CALLED_FAILED", category="PROVIDER_TIMEOUT")
    assert "PROVIDER_TIMEOUT" in caplog.text
    assert caplog.records[-1].levelno == logging.WARNING


class FakeAsyncClient:
    def __init__(self, response):
        self.models = SimpleNamespace(generate_content=AsyncMock(return_value=response))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


@pytest.mark.asyncio
async def test_structured_provider_uses_new_sdk_and_validates_output(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(gemini.settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini.settings, "GEMINI_MODEL_POOL", "")
    client = FakeAsyncClient(SimpleNamespace(text='{"ok":true}'))
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=client))
    assert (await gemini.generate_json("test", "safe prompt", "safe instruction", Answer,
                                       timeout=2, max_tokens=32)).ok
    call = client.models.generate_content.call_args
    assert call.kwargs["config"].response_schema is None
    assert call.kwargs["config"].response_json_schema == Answer.model_json_schema()
    assert call.kwargs["config"].response_json_schema["additionalProperties"] is False
    assert call.kwargs["config"].max_output_tokens == 32
    assert call.kwargs["model"] == gemini.settings.GEMINI_MODEL_NAME
    assert "test-key" not in caplog.text
    assert "CALLED_SUCCESS" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("response,category", [
    (SimpleNamespace(text='{"ok":"not a boolean"}'), "SCHEMA_VALIDATION_FAILED"),
    (SimpleNamespace(text='{"ok":true,"employee_id":99}'), "SCHEMA_VALIDATION_FAILED"),
    (SimpleNamespace(text=""), "INVALID_PROVIDER_RESPONSE"),
])
async def test_invalid_provider_output_is_categorized(monkeypatch, response, category):
    monkeypatch.setattr(gemini.settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_API_KEY", "test-key")
    client = FakeAsyncClient(response)
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=client))
    with pytest.raises(gemini.ProviderFailure) as error:
        await gemini.generate_json("test", "prompt", "instruction", Answer, timeout=2, max_tokens=32)
    assert error.value.category == category


@pytest.mark.asyncio
async def test_disabled_provider_makes_no_client(monkeypatch):
    monkeypatch.setattr(gemini.settings, "GEMINI_ENABLED", False)
    client = AsyncMock()
    monkeypatch.setattr(gemini.genai, "Client", client)
    with pytest.raises(gemini.ProviderFailure) as error:
        await gemini.generate_json("test", "prompt", "instruction", Answer, timeout=2, max_tokens=32)
    assert error.value.category == "PROVIDER_DISABLED"
    client.assert_not_called()


@pytest.mark.asyncio
async def test_provider_timeout_is_not_success(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(gemini.settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_API_KEY", "test-key")
    client = FakeAsyncClient(None)
    client.models.generate_content.side_effect = asyncio.TimeoutError()
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=client))
    with pytest.raises(gemini.ProviderFailure) as error:
        await gemini.generate_json("test", "prompt", "instruction", Answer, timeout=2, max_tokens=32)
    assert error.value.category == "PROVIDER_TIMEOUT"
    assert "CALLED_FAILED" in caplog.text


@pytest.mark.asyncio
async def test_public_search_uses_native_tool_without_json_schema(monkeypatch):
    monkeypatch.setattr(gemini.settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_PUBLIC_SEARCH_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_API_KEY", "test-key")
    response = SimpleNamespace(text="grounded text")
    client = FakeAsyncClient(response)
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=client))
    assert await gemini.generate_search_answer("public question", "instruction") is response
    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.tools[0].google_search is not None
    assert config.response_json_schema is None and config.response_schema is None


class QuotaThenOk:
    """Fake SDK client: the first listed model answers 429, the others succeed."""
    def __init__(self, exhausted):
        self.exhausted, self.models_called = exhausted, []

        async def generate_content(**kwargs):
            self.models_called.append(kwargs["model"])
            if kwargs["model"] in self.exhausted:
                raise gemini.errors.APIError(429, {"error": {"message": "quota"}})
            return SimpleNamespace(text='{"ok":true}')
        self.models = SimpleNamespace(generate_content=generate_content)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


@pytest.fixture
def pool(monkeypatch):
    monkeypatch.setattr(gemini.settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(gemini.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini.settings, "GEMINI_MODEL_POOL", "model-a, model-b,model-a")
    monkeypatch.setattr(gemini, "_cooldown_until", {})
    monkeypatch.setattr(gemini, "_sent", {})
    monkeypatch.setattr(gemini.settings, "GEMINI_MODEL_RPM", 15)
    monkeypatch.setattr(gemini, "_turn", iter(range(100)))


def test_model_pool_defaults_to_the_single_configured_model(monkeypatch):
    monkeypatch.setattr(gemini.settings, "GEMINI_MODEL_POOL", " ")
    assert gemini.model_pool() == [gemini.settings.GEMINI_MODEL_NAME]


@pytest.mark.asyncio
async def test_calls_rotate_across_the_model_pool(monkeypatch, pool):
    client = QuotaThenOk(exhausted=set())
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=client))
    for _ in range(4):
        await gemini.generate_json("test", "p", "i", Answer, timeout=2, max_tokens=8)
    assert client.models_called == ["model-a", "model-b", "model-a", "model-b"]


@pytest.mark.asyncio
async def test_quota_on_one_model_moves_the_request_to_the_next_and_rests_that_model(monkeypatch, pool):
    client = QuotaThenOk(exhausted={"model-a"})
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=client))
    assert (await gemini.generate_json("test", "p", "i", Answer, timeout=2, max_tokens=8)).ok
    assert client.models_called == ["model-a", "model-b"]
    # model-a is resting, so later requests skip it even when it is their turn.
    await gemini.generate_json("test", "p", "i", Answer, timeout=2, max_tokens=8)
    await gemini.generate_json("test", "p", "i", Answer, timeout=2, max_tokens=8)
    assert client.models_called[2:] == ["model-b", "model-b"]


@pytest.mark.asyncio
async def test_quota_on_every_model_is_reported_as_quota(monkeypatch, pool):
    client = QuotaThenOk(exhausted={"model-a", "model-b"})
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=client))
    with pytest.raises(gemini.ProviderFailure) as raised:
        await gemini.generate_json("test", "p", "i", Answer, timeout=2, max_tokens=8)
    assert raised.value.category == "QUOTA_EXCEEDED" and client.models_called == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_a_model_at_its_per_minute_budget_is_skipped_before_it_returns_429(monkeypatch, pool):
    monkeypatch.setattr(gemini.settings, "GEMINI_MODEL_RPM", 2)
    client = QuotaThenOk(exhausted=set())
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(aio=client))
    gemini._sent["model-a"] = gemini.deque([gemini.monotonic()] * 2)
    for _ in range(2):
        await gemini.generate_json("test", "p", "i", Answer, timeout=2, max_tokens=8)
    assert client.models_called == ["model-b", "model-b"]
