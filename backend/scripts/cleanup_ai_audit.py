"""Retain structured AI audit events for 90 days; dry run unless --apply."""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models.ai_security import AIRequestEvent


async def cleanup(apply: bool):
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    async with AsyncSessionLocal() as db:
        predicate = AIRequestEvent.created_at < cutoff
        count = await db.scalar(select(func.count()).select_from(AIRequestEvent).where(predicate))
        if apply:
            await db.execute(delete(AIRequestEvent).where(predicate))
            await db.commit()
        print(f"{'Deleted' if apply else 'Would delete'} {count} audit events older than 90 days.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(cleanup(parser.parse_args().apply))
