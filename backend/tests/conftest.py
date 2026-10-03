import pytest
import pytest_asyncio
from app.core.database import engine


@pytest_asyncio.fixture(autouse=True)
async def cleanup_db_pool():
    yield
    await engine.dispose()
