"""One Gemini SDK boundary with safe operational diagnostics."""

import asyncio
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from collections import deque
from itertools import count
from time import monotonic
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.services.ai_request_security import current_request_id

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


# Monotonic deadline for the current request; provider calls never outlive it.
_deadline: ContextVar[float | None] = ContextVar("ai_provider_deadline", default=None)
_DEADLINE_MARGIN_SECONDS = 1.0
_MIN_CALL_SECONDS = 2.0


@contextmanager
def request_deadline(seconds: float):
    """Share one time budget across every provider call made by a request."""
    token = _deadline.set(monotonic() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


def budgeted_timeout(requested: float) -> float | None:
    """Return the timeout a call may use, or None when the budget is spent."""
    deadline = _deadline.get()
    if deadline is None:
        return requested
    remaining = deadline - monotonic() - _DEADLINE_MARGIN_SECONDS
    if remaining < _MIN_CALL_SECONDS:
        return None
    return min(requested, remaining)


class ProviderFailure(Exception):
    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


def readiness() -> dict:
    key = settings.GEMINI_API_KEY.strip()
    configured = bool(key and not key.startswith("your_"))
    return {
        "enabled": settings.GEMINI_ENABLED,
        "semantic_enabled": settings.GEMINI_SEMANTIC_ENABLED,
        "public_search_enabled": settings.GEMINI_PUBLIC_SEARCH_ENABLED,
        "embeddings_enabled": settings.GEMINI_EMBEDDINGS_ENABLED,
        "pdf_structure_enabled": settings.GEMINI_PDF_STRUCTURE_ENABLED,
        "knowledge_tagging_enabled": settings.GEMINI_KNOWLEDGE_TAGGING_ENABLED,
        "key_configured": configured,
        "model": settings.GEMINI_MODEL_NAME,
        "model_pool": model_pool(),
        "backend": "google-genai/Gemini Developer API",
        "environment": settings.ENVIRONMENT,
        "state": "READY_TO_CHECK" if settings.GEMINI_ENABLED and configured else "DISABLED" if not settings.GEMINI_ENABLED else "KEY_MISSING",
    }


def record(operation: str, outcome: str, elapsed_ms: int = 0, category: str | None = None,
           model: str | None = None) -> None:
    emit = logger.warning if outcome in {"CALLED_FAILED", "OUTPUT_REJECTED"} else logger.info
    emit(json.dumps({
        "event": "ai_provider", "request_id": current_request_id(), "operation": operation,
        "model": model or settings.GEMINI_MODEL_NAME, "elapsed_ms": elapsed_ms,
        "outcome": outcome, "category": category,
    }))


# Text models share the load so each model's own per-minute quota is used:
# a model at GEMINI_MODEL_RPM sends in the last minute is skipped, and one that answers 429 rests for a while and the same request moves on to
# the next model; process-local state, embeddings keep their own model.
QUOTA_COOLDOWN_SECONDS = 60.0
_cooldown_until: dict[str, float] = {}
_sent: dict[str, deque] = {}  # Send times per model over the last minute.
_turn = count()
_SWITCH_MODEL = {"QUOTA_EXCEEDED", "MODEL_UNAVAILABLE", "NETWORK_ERROR"}


def model_pool() -> list[str]:
    names = [name.strip() for name in settings.GEMINI_MODEL_POOL.split(",") if name.strip()]
    return list(dict.fromkeys(names)) or [settings.GEMINI_MODEL_NAME]


def _recent_calls(model: str, now: float) -> int:
    window = _sent.setdefault(model, deque())
    while window and window[0] <= now - 60:
        window.popleft()
    return len(window)


def _rotation() -> list[str]:
    """Models to try, best first: not resting, under its per-minute budget, least used.

    Round-robin breaks ties, so an idle pool still alternates models.
    """
    pool = model_pool()
    start = next(_turn) % len(pool)
    ordered = pool[start:] + pool[:start]
    now = monotonic()
    limit = settings.GEMINI_MODEL_RPM

    def rank(model):
        used = _recent_calls(model, now)
        resting = _cooldown_until.get(model, 0.0) > now
        return (resting, bool(limit) and used >= limit, used if limit else 0, _cooldown_until.get(model, 0.0))
    # Everything busy or resting: still try (least loaded first) rather than refuse without asking.
    return sorted(ordered, key=rank)


def _note_sent(model: str) -> None:
    _sent.setdefault(model, deque()).append(monotonic())


async def _across_models(call):
    """Run `call(model)` on the next model; on quota/model errors try the others."""
    failure = None
    for model in _rotation():
        for attempt in range(2):
            try:
                _note_sent(model)
                return await call(model)
            except ProviderFailure as exc:
                failure = exc
                if exc.category == "QUOTA_EXCEEDED":
                    _cooldown_until[model] = monotonic() + QUOTA_COOLDOWN_SECONDS
                if attempt or exc.category not in _RETRYABLE:
                    break
        if failure.category not in _SWITCH_MODEL:
            raise failure
    raise failure


def classify_error(exc: Exception) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return "PROVIDER_TIMEOUT"
    if isinstance(exc, (OSError, ConnectionError)):
        return "NETWORK_ERROR"
    if isinstance(exc, errors.APIError):
        code = exc.code if isinstance(exc.code, int) else 0
        if code in {401, 403}:
            return "AUTHENTICATION_FAILED"
        if code == 404:
            return "MODEL_UNAVAILABLE"
        if code == 429:
            return "QUOTA_EXCEEDED"
        if code in {408, 504}:
            return "PROVIDER_TIMEOUT"
        return "NETWORK_ERROR" if code >= 500 else "INVALID_PROVIDER_RESPONSE"
    if isinstance(exc, ValidationError):
        return "SCHEMA_VALIDATION_FAILED"
    return "INVALID_PROVIDER_RESPONSE"


# Transient failures worth one retry; timeouts are not retried because they
# already consumed most of the shared request budget.
_RETRYABLE = {"NETWORK_ERROR"}


async def generate_json(operation: str, prompt: str, instruction: str, schema: type[T],
                        *, timeout: float, max_tokens: int, pdf_bytes: bytes | None = None) -> T:
    state = readiness()
    if state["state"] != "READY_TO_CHECK":
        record(operation, "SKIPPED_DISABLED", category="PROVIDER_DISABLED")
        raise ProviderFailure("PROVIDER_DISABLED")
    # A PDF part lets the model read scanned pages; the prompt stays the text part.
    contents = prompt if pdf_bytes is None else [
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt]
    return await _across_models(lambda model: _generate_json_once(
        operation, contents, instruction, schema, timeout, max_tokens, model))


async def _generate_json_once(operation, contents, instruction, schema, timeout, max_tokens, model=None):
    model = model or settings.GEMINI_MODEL_NAME
    timeout = budgeted_timeout(timeout)
    if timeout is None:
        record(operation, "SKIPPED_BUDGET", category="PROVIDER_TIMEOUT", model=model)
        raise ProviderFailure("PROVIDER_TIMEOUT")
    started = monotonic()
    try:
        async with genai.Client(api_key=settings.GEMINI_API_KEY.strip()).aio as client:
            response = await asyncio.wait_for(client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    temperature=0,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                    # Preserve JSON Schema keys such as additionalProperties;
                    # the SDK's OpenAPI Schema path can send additional_properties
                    # for extra="forbid", which the Developer API rejects.
                    response_json_schema=schema.model_json_schema(),
                ),
            ), timeout=timeout)
        if not response.text:
            raise ProviderFailure("INVALID_PROVIDER_RESPONSE")
        try:
            result = schema.model_validate_json(response.text)
        except ValidationError as exc:
            raise ProviderFailure("SCHEMA_VALIDATION_FAILED") from exc
        record(operation, "CALLED_SUCCESS", int((monotonic() - started) * 1000), model=model)
        return result
    except ProviderFailure as exc:
        record(operation, "OUTPUT_REJECTED", int((monotonic() - started) * 1000), exc.category, model=model)
        raise
    except Exception as exc:
        category = classify_error(exc)
        record(operation, "CALLED_FAILED", int((monotonic() - started) * 1000), category, model=model)
        raise ProviderFailure(category) from exc


async def generate_function_calls(operation: str, prompt: str, instruction: str, declarations: list[dict],
                                  *, timeout: float, max_tokens: int) -> list[tuple[str, dict]]:
    """Ask the model to choose among declared functions; nothing is executed here.

    Mode ANY forces at least one call, so the answer is always a closed choice
    (name + JSON arguments) that the caller validates against its own catalog.
    """
    if readiness()["state"] != "READY_TO_CHECK":
        record(operation, "SKIPPED_DISABLED", category="PROVIDER_DISABLED")
        raise ProviderFailure("PROVIDER_DISABLED")
    tool = types.Tool(function_declarations=[
        types.FunctionDeclaration(name=item["name"], description=item["description"],
                                  parameters_json_schema=item["parameters"]) for item in declarations])
    config = types.GenerateContentConfig(
        system_instruction=instruction, temperature=0, max_output_tokens=max_tokens, tools=[tool],
        tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY")),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    return await _across_models(lambda model: _function_calls_once(operation, prompt, config, timeout, model))


async def _function_calls_once(operation, prompt, config, timeout, model):
    timeout = budgeted_timeout(timeout)
    if timeout is None:
        record(operation, "SKIPPED_BUDGET", category="PROVIDER_TIMEOUT", model=model)
        raise ProviderFailure("PROVIDER_TIMEOUT")
    started = monotonic()
    try:
        async with genai.Client(api_key=settings.GEMINI_API_KEY.strip()).aio as client:
            response = await asyncio.wait_for(client.models.generate_content(
                model=model, contents=prompt, config=config), timeout=timeout)
        calls = [(call.name, dict(call.args or {})) for call in (response.function_calls or []) if call.name]
        if not calls:
            raise ProviderFailure("INVALID_PROVIDER_RESPONSE")
        record(operation, "CALLED_SUCCESS", int((monotonic() - started) * 1000), model=model)
        return calls
    except ProviderFailure as exc:
        record(operation, "OUTPUT_REJECTED", int((monotonic() - started) * 1000), exc.category, model=model)
        raise
    except Exception as exc:
        category = classify_error(exc)
        record(operation, "CALLED_FAILED", int((monotonic() - started) * 1000), category, model=model)
        raise ProviderFailure(category) from exc


EMBED_BATCH_SIZE = 100


def embeddings_ready() -> bool:
    return settings.GEMINI_EMBEDDINGS_ENABLED and readiness()["state"] == "READY_TO_CHECK"


async def embed_texts(operation: str, texts: list[str], task_type: str, *, dimensions: int) -> list[list[float]]:
    """Embed knowledge text or a masked question; vectors are L2-normalized.

    Reduced-dimension Gemini embeddings are not normalized by the API, and
    cosine ranking in pgvector assumes comparable magnitudes.
    """
    if not embeddings_ready():
        record(operation, "SKIPPED_DISABLED", category="PROVIDER_DISABLED")
        raise ProviderFailure("PROVIDER_DISABLED")
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        for attempt in range(2):
            try:
                vectors.extend(await _embed_once(operation, batch, task_type, dimensions))
                break
            except ProviderFailure as exc:
                if attempt or exc.category not in _RETRYABLE:
                    raise
    return vectors


async def _embed_once(operation, batch, task_type, dimensions):
    timeout = budgeted_timeout(settings.GEMINI_EMBED_TIMEOUT_SECONDS)
    if timeout is None:
        record(operation, "SKIPPED_BUDGET", category="PROVIDER_TIMEOUT")
        raise ProviderFailure("PROVIDER_TIMEOUT")
    started = monotonic()
    try:
        async with genai.Client(api_key=settings.GEMINI_API_KEY.strip()).aio as client:
            response = await asyncio.wait_for(client.models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=batch,
                config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=dimensions),
            ), timeout=timeout)
        values = [list(item.values or []) for item in (response.embeddings or [])]
        if len(values) != len(batch) or any(len(vector) != dimensions for vector in values):
            raise ProviderFailure("INVALID_PROVIDER_RESPONSE")
        normalized = []
        for vector in values:
            norm = sum(value * value for value in vector) ** 0.5
            if not norm:
                raise ProviderFailure("INVALID_PROVIDER_RESPONSE")
            normalized.append([value / norm for value in vector])
        record(operation, "CALLED_SUCCESS", int((monotonic() - started) * 1000))
        return normalized
    except ProviderFailure as exc:
        record(operation, "OUTPUT_REJECTED", int((monotonic() - started) * 1000), exc.category)
        raise
    except Exception as exc:
        category = classify_error(exc)
        record(operation, "CALLED_FAILED", int((monotonic() - started) * 1000), category)
        raise ProviderFailure(category) from exc


async def generate_search_answer(prompt: str, instruction: str):
    """Native Google Search grounding; citations are validated by the caller."""
    if readiness()["state"] != "READY_TO_CHECK" or not settings.GEMINI_PUBLIC_SEARCH_ENABLED:
        raise ProviderFailure("PROVIDER_DISABLED")
    return await _across_models(lambda model: _search_once(prompt, instruction, model))


async def _search_once(prompt, instruction, model):
    timeout = budgeted_timeout(settings.GEMINI_PUBLIC_SEARCH_TIMEOUT_SECONDS)
    if timeout is None:
        record("public_policy_search", "SKIPPED_BUDGET", category="PROVIDER_TIMEOUT", model=model)
        raise ProviderFailure("PROVIDER_TIMEOUT")
    started = monotonic()
    try:
        async with genai.Client(api_key=settings.GEMINI_API_KEY.strip()).aio as client:
            response = await asyncio.wait_for(client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    temperature=0,
                    max_output_tokens=2048,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            ), timeout=timeout)
        record("public_policy_search", "CALLED_SUCCESS", int((monotonic() - started) * 1000), model=model)
        return response
    except Exception as exc:
        category = classify_error(exc)
        record("public_policy_search", "CALLED_FAILED", int((monotonic() - started) * 1000), category, model=model)
        raise ProviderFailure(category) from exc
