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


# Legacy upstream integration suites live under tests/unit for now. Exempt only
# these known DB-backed modules, rather than disabling the guard for future tests.
_LEGACY_DB_TEST_MODULES = frozenset({
    "test_attendance_and_payroll_half_day.py",
    "test_payroll_dependent_and_leave_rules.py",
    "test_role_and_leave_quota.py",
})


@pytest.fixture(autouse=True)
def forbid_unit_database_connections(request):
    if request.node.path.name in _LEGACY_DB_TEST_MODULES:
        yield
        return

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
