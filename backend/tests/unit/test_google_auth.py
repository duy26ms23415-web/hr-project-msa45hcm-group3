"""Google SSO contract checks with local provider/DB doubles."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from google.auth.exceptions import GoogleAuthError
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import auth
from app.core.database import get_db


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_error", [ValueError("invalid"), GoogleAuthError("provider failed")])
async def test_google_provider_errors_return_401_without_database(monkeypatch, provider_error):
    db = AsyncMock()
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(auth.settings, "GOOGLE_CLIENT_ID", "local-test-client")
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", Mock(side_effect=provider_error))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login/google", json={"id_token": "test-token"})
    assert response.status_code == 401
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("active, expected", [(True, 200), (False, 403), (None, 403)])
async def test_verified_google_identity_requires_existing_active_account(monkeypatch, active, expected):
    user = None if active is None else SimpleNamespace(user_account_id=7, is_active=active)
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: user)
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(auth.settings, "GOOGLE_CLIENT_ID", "local-test-client")
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", Mock(return_value={"email": "staff@fsb.edu.vn", "email_verified": True}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login/google", json={"id_token": "test-token"})
    assert response.status_code == expected
    if active:
        assert response.json()["token_type"] == "bearer"
        assert response.json()["access_token"] and response.json()["refresh_token"]
        db.commit.assert_awaited_once()
    else:
        db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("client_id, verified, expected", [("", True, 500), ("local-test-client", False, 400)])
async def test_google_configuration_and_verified_email_are_required(monkeypatch, client_id, verified, expected):
    db = AsyncMock()
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(auth.settings, "GOOGLE_CLIENT_ID", client_id)
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", Mock(return_value={"email": "staff@example.test", "email_verified": verified}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login/google", json={"id_token": "test-token"})
    assert response.status_code == expected
    db.execute.assert_not_awaited()
