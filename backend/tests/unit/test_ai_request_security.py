from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.services import ai_request_security as security


def security_session(monkeypatch, count):
    now = datetime.now(timezone.utc)
    db = SimpleNamespace(execute=AsyncMock(), add=Mock(), commit=AsyncMock())
    values = [None, None, None, now, count]
    if count >= 20:
        values.append(now - timedelta(seconds=10))
    db.execute.side_effect = [SimpleNamespace(scalar_one=lambda value=value: value) for value in values]
    session = AsyncMock()
    session.__aenter__.return_value = db
    monkeypatch.setattr(security, "AsyncSessionLocal", lambda: session)
    return db


@pytest.mark.asyncio
async def test_budget_reservation_is_committed_separately_and_contains_no_user_text(monkeypatch):
    db = security_session(monkeypatch, 19)
    await security.consume_budget(None, 42, "CHAT", "request-42")
    event = db.add.call_args.args[0]
    assert event.outcome == "ALLOWED" and event.actor_user_account_id == 42
    assert event.command is None
    db.commit.assert_awaited_once()
    assert "pg_advisory_xact_lock" in str(db.execute.call_args_list[2].args[0])


@pytest.mark.asyncio
async def test_exhausted_budget_commits_rejection_and_returns_retry_after(monkeypatch):
    db = security_session(monkeypatch, 20)
    with pytest.raises(HTTPException) as exc:
        await security.consume_budget(None, 42, "CHAT", "request-42")
    assert exc.value.status_code == 429 and exc.value.headers["Retry-After"] == "50"
    assert db.add.call_args.args[0].outcome == "RATE_LIMITED"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_rejects_free_text_commands_before_database_access(monkeypatch):
    session_factory = Mock()
    monkeypatch.setattr(security, "AsyncSessionLocal", session_factory)
    with pytest.raises(HTTPException):
        await security.record_event(None, 42, "CHAT", "CHAT", "SELF", "SUCCESS", "req42", command="reason: private user input")
    session_factory.assert_not_called()
