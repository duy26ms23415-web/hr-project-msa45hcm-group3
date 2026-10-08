from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.ai_errors import install_ai_errors, MESSAGES
from app.schemas.ai import AIChatRequest
from app.services import ai_request_security as security


@pytest.mark.asyncio
@pytest.mark.parametrize("status,raw,expected", [(403, "AI_ACCESS_DENIED", "PERMISSION_DENIED"), (410, "AI_DRAFT_EXPIRED", "DRAFT_EXPIRED"), (429, "AI_RATE_LIMITED", "RATE_LIMITED"), (503, "AI_UNAVAILABLE", "AI_UNAVAILABLE")])
async def test_safe_error_envelope_matches_audit_and_keeps_retry_after(monkeypatch, status, raw, expected):
    app = FastAPI()
    install_ai_errors(app, ("/ai", "/reports"))
    monkeypatch.setattr(security, "consume_budget", AsyncMock())
    audit = AsyncMock()
    monkeypatch.setattr(security, "record_event", audit)

    @app.get("/ai/probe")
    async def probe():
        async with security.secured_operation(None, 7, "CHAT", "CHAT"):
            raise HTTPException(status, raw, headers={"Retry-After": "30"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ai/probe", headers={"X-Request-ID": "forged"})
    body = response.json()
    assert response.status_code == status and body["code"] == expected
    assert body["message"] == MESSAGES[expected] and body["action"] is None and body["sources"] == []
    assert body["request_id"] == response.headers["x-request-id"] == audit.await_args.args[6]
    assert body["request_id"] != "forged" and response.headers["retry-after"] == "30"
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_validation_and_unexpected_errors_do_not_echo_inputs_or_exceptions():
    app = FastAPI()
    install_ai_errors(app, ("/ai",))

    @app.post("/ai/chat")
    async def chat(req: AIChatRequest):
        raise RuntimeError("PRIVATE_DB_PATH_AND_REASON")

    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        invalid = await client.post("/ai/chat", json={"message": "PRIVATE_REASON", "employee_id": 99})
        failure = await client.post("/ai/chat", json={"message": "PRIVATE_REASON"})
    assert invalid.status_code == 422 and invalid.json()["code"] == "INVALID_INPUT"
    assert failure.status_code == 503 and failure.json()["code"] == "DATA_SERVICE_UNAVAILABLE"
    assert "PRIVATE" not in invalid.text + failure.text


def test_structured_chat_requires_operation_and_revision():
    assert AIChatRequest(suggestion_id="draft_leave").message == ""
    assert AIChatRequest(suggestion_id="draft_leave", inputs={"reason": "Việc gia đình"}).inputs == {"reason": "Việc gia đình"}
    req = AIChatRequest(draft_id="00000000-0000-4000-8000-000000000000", draft_revision=1, inputs={"scope": "SELF"})
    assert req.inputs == {"scope": "SELF"}
    with pytest.raises(ValidationError):
        AIChatRequest()
    with pytest.raises(ValidationError):
        AIChatRequest(message="next", draft_id=req.draft_id)
