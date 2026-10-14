"""Unit tests must mock provider calls instead of using developer credentials."""
import pytest
from sqlalchemy import event

from app.ai.providers import gemini
from app.core.database import engine


@pytest.fixture(autouse=True)
def forbid_unmocked_provider_client(monkeypatch):
    unexpected_calls = []

    def reject_client(*args, **kwargs):
        unexpected_calls.append(True)
        raise AssertionError("Unit tests must mock the provider boundary")

    monkeypatch.setattr(gemini.genai, "Client", reject_client)
    yield
    # Provider fallbacks can catch the exception; still fail the test so an
    # unmocked operation cannot silently pass through a fallback response.
    assert not unexpected_calls, "Unit test attempted an unmocked provider call"


@pytest.fixture(autouse=True)
def forbid_unit_database_connections():
    unexpected_calls = []

    def reject_connection(*args, **kwargs):
        unexpected_calls.append(True)
        raise AssertionError("Database-backed tests belong outside tests/unit")

    event.listen(engine.sync_engine, "do_connect", reject_connection)
    try:
        yield
    finally:
        event.remove(engine.sync_engine, "do_connect", reject_connection)
    assert not unexpected_calls, "Unit test attempted a real database connection"
