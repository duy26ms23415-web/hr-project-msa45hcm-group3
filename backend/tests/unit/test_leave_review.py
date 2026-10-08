"""Review races with simulated row locks, without writing to a real database."""
import asyncio
from copy import copy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.leave import LeaveRequest
from app.models.organization import Employee
from app.schemas.leave import LeaveRequestReview
from app.services.leave_service import LeaveService


@pytest.mark.asyncio
@pytest.mark.parametrize("second_status", ["APPROVED", "REJECTED"])
async def test_concurrent_reviews_only_apply_first_decision(second_status):
    request = SimpleNamespace(
        leave_request_id=1, employee_id=7, status="PENDING",
        leave_date=date(2026, 10, 12), leave_days=Decimal("1.00"),
        leave_type=SimpleNamespace(is_paid=True),
    )
    balance = SimpleNamespace(
        used_days=Decimal("0.00"), remaining_days=Decimal("12.00"),
        total_entitled_days=Decimal("12.00"),
    )
    request_lock = asyncio.Lock()
    first_loaded = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()
    queries = []

    async def review(first, decision):
        local_request = None
        locked = False

        async def execute(statement):
            nonlocal local_request, locked
            entity = statement.column_descriptions[0]["entity"]
            if entity is LeaveRequest:
                if not first:
                    second_started.set()
                sql = str(statement.compile(dialect=postgresql.dialect()))
                queries.append((sql, statement.get_execution_options()))
                if "FOR UPDATE" in sql:
                    await request_lock.acquire()
                    locked = True
                local_request = copy(request)
                return SimpleNamespace(scalar_one_or_none=lambda: local_request)
            if entity is Employee:
                if first:
                    first_loaded.set()
                    await release_first.wait()
                return SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(manager_employee_id=9))
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        db = SimpleNamespace(execute=execute, flush=AsyncMock(), add=Mock())
        try:
            result = await LeaveService.review_leave_request(
                db, 1, 9, LeaveRequestReview(status=decision),
            )
            # Simulate transaction commit before releasing the row lock.
            request.status = local_request.status
            return result.status
        except HTTPException as exc:
            return exc.status_code, exc.detail
        finally:
            if locked:
                request_lock.release()

    # Both reviews use the same paid balance, as separate DB transactions do.
    from unittest.mock import patch
    with patch.object(LeaveService, "get_or_create_balance", AsyncMock(return_value=balance)):
        first = asyncio.create_task(review(True, "APPROVED"))
        await asyncio.wait_for(first_loaded.wait(), timeout=2)
        second = asyncio.create_task(review(False, second_status))
        await asyncio.wait_for(second_started.wait(), timeout=2)
        release_first.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=2)

    assert results == ["APPROVED", (400, "Request is already APPROVED")]
    assert request.status == "APPROVED"
    assert balance.used_days == Decimal("1.00")
    assert balance.remaining_days == Decimal("11.00")
    assert all("FOR UPDATE" in sql and options["populate_existing"] for sql, options in queries)
