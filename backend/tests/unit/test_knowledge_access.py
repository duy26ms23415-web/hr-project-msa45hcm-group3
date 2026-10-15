from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api.deps import get_current_user
from app.api.v1.endpoints import knowledge
from app.core.database import get_db
from app.schemas.knowledge import KnowledgeAccessWrite


def _user(role):
    return SimpleNamespace(
        user_account_id=41,
        role_assignments=[SimpleNamespace(role=SimpleNamespace(role_code=role))],
    )


def _document(**overrides):
    values = dict(
        document_id=16,
        document_code="DOC-16",
        title="Access policy",
        content="body",
        source_url=None,
        status="PUBLISHED",
        minimum_role="EMPLOYEE",
        current_version_id=10,
        updated_by_user_id=3,
        updated_at=datetime.now(timezone.utc),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _version(version_id, status, minimum_role):
    return SimpleNamespace(
        version_id=version_id,
        document_id=16,
        status=status,
        minimum_role=minimum_role,
    )


@pytest.fixture
def api_context(monkeypatch):
    app = FastAPI()
    app.include_router(knowledge.router, prefix="/ai/knowledge")
    user = _user("HR")
    db = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return app, user, db


@pytest.mark.asyncio
async def test_hr_access_change_updates_initial_draft_and_preserves_document_state(api_context):
    app, user, db = api_context
    user.role_assignments[0].role.role_code = "HR"
    document = _document(status="DRAFT", current_version_id=None)
    draft = _version(11, "DRAFT", "EMPLOYEE")
    historical = _version(9, "ARCHIVED", "MANAGER")
    db.scalar.return_value = document
    db.scalars.return_value = SimpleNamespace(all=lambda: [draft])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/ai/knowledge/16/access", json={"minimum_role": "MANAGER"})

    assert response.status_code == 200
    assert response.json()["minimum_role"] == "MANAGER"
    assert document.minimum_role == draft.minimum_role == "MANAGER"
    assert document.status == "DRAFT" and document.content == "body"
    assert document.current_version_id is None
    assert historical.minimum_role == "MANAGER"
    db.flush.assert_awaited_once()
    db.refresh.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_admin_access_change_syncs_current_and_drafts_but_not_history_or_archive_status(api_context):
    app, user, db = api_context
    user.role_assignments[0].role.role_code = "ADMIN"
    document = _document(status="ARCHIVED")
    current = _version(10, "PUBLISHED", "EMPLOYEE")
    draft = _version(12, "DRAFT", "MANAGER")
    historical = _version(8, "ARCHIVED", "HR")
    db.scalar.return_value = document
    db.scalars.return_value = SimpleNamespace(all=lambda: [current, draft])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/ai/knowledge/16/access", json={"minimum_role": "ADMIN"})

    assert response.status_code == 200
    assert document.minimum_role == current.minimum_role == draft.minimum_role == "ADMIN"
    assert document.status == "ARCHIVED" and current.status == "PUBLISHED" and draft.status == "DRAFT"
    assert historical.minimum_role == "HR"
    assert document.content == "body" and document.current_version_id == current.version_id


@pytest.mark.asyncio
async def test_hr_cannot_assign_admin_and_rejected_requests_do_not_mutate(api_context):
    app, user, db = api_context
    user.role_assignments[0].role.role_code = "HR"
    document = _document()
    db.scalar.return_value = document

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/ai/knowledge/16/access", json={"minimum_role": "ADMIN"})

    assert response.status_code == 403
    assert document.minimum_role == "EMPLOYEE" and document.updated_by_user_id == 3
    db.scalars.assert_not_awaited()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden_on", ["document", "current", "draft"])
async def test_hr_cannot_lower_permission_when_any_existing_scope_is_hidden(api_context, hidden_on):
    app, user, db = api_context
    user.role_assignments[0].role.role_code = "HR"
    document = _document(minimum_role="ADMIN" if hidden_on == "document" else "EMPLOYEE")
    current = _version(10, "PUBLISHED", "ADMIN" if hidden_on == "current" else "EMPLOYEE")
    draft = _version(12, "DRAFT", "ADMIN" if hidden_on == "draft" else "EMPLOYEE")
    db.scalar.return_value = document
    db.scalars.return_value = SimpleNamespace(all=lambda: [current, draft])
    before = (document.minimum_role, document.updated_by_user_id, current.minimum_role, draft.minimum_role)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/ai/knowledge/16/access", json={"minimum_role": "EMPLOYEE"})

    assert response.status_code == 404
    assert (document.minimum_role, document.updated_by_user_id, current.minimum_role, draft.minimum_role) == before
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_current_version_reference_fails_without_mutation(api_context):
    app, user, db = api_context
    user.role_assignments[0].role.role_code = "HR"
    document = _document(current_version_id=99)
    db.scalar.return_value = document
    db.scalars.return_value = SimpleNamespace(all=lambda: [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/ai/knowledge/16/access", json={"minimum_role": "HR"})

    assert response.status_code == 409
    assert document.minimum_role == "EMPLOYEE"
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["EMPLOYEE", "MANAGER"])
async def test_employee_and_manager_are_denied_by_route_role_dependency(api_context, role):
    app, user, db = api_context
    user.role_assignments[0].role.role_code = role

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/ai/knowledge/16/access", json={"minimum_role": "EMPLOYEE"})

    assert response.status_code == 403
    db.scalar.assert_not_awaited()
    db.flush.assert_not_awaited()


@pytest.mark.parametrize("payload", [
    {"minimum_role": "OWNER"},
    {"minimum_role": "HR", "unexpected": True},
])
def test_access_schema_rejects_invalid_roles_and_extra_fields(payload):
    with pytest.raises(ValidationError):
        KnowledgeAccessWrite.model_validate(payload)
