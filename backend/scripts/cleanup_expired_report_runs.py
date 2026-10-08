"""Expire old report runs and remove only their server-generated artifacts."""
import asyncio
import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, or_, and_, delete

from app.core.database import AsyncSessionLocal, engine
from app.models.knowledge import ReportRun
from app.services.report_storage import delete_report, orphan_report_keys


async def cleanup(apply: bool = False) -> int:
    removed = 0
    expired_keys = []
    async with AsyncSessionLocal() as db:
        runs = (await db.scalars(select(ReportRun).where(
            ReportRun.expires_at <= datetime.now(timezone.utc),
            or_(ReportRun.status.in_(["READY", "GENERATING"]), and_(ReportRun.status == "FAILED", or_(ReportRun.storage_key.is_not(None), ReportRun.snapshot_storage_key.is_not(None)))),
        ).with_for_update())).all()
        for run in runs:
            removed += 1
            if not apply:
                continue
            expired_keys.extend((run.storage_key, run.snapshot_storage_key))
            run.storage_key = None
            run.snapshot_storage_key = None
            if run.status != "FAILED":
                run.status = "EXPIRED"
        if apply:
            await db.commit()
    for key in expired_keys:
        delete_report(key)
    async with AsyncSessionLocal() as db:
        # Read references from every owner/state before considering file orphans.
        referenced = {key for row in (await db.execute(select(ReportRun.storage_key, ReportRun.snapshot_storage_key))).all() for key in row if key}
        orphans = orphan_report_keys(referenced)
        if apply:
            for key in orphans:
                delete_report(key)
            await db.execute(delete(ReportRun).where(
                ReportRun.created_at < datetime.now(timezone.utc) - timedelta(days=30),
                ReportRun.expires_at <= datetime.now(timezone.utc),
                ReportRun.storage_key.is_(None), ReportRun.snapshot_storage_key.is_(None),
            ))
            await db.commit()
        print(f"{'Removed' if apply else 'Eligible'} orphan artifacts: {len(orphans)}.")
    return removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Remove expired artifacts; otherwise only count eligible runs.")
    args = parser.parse_args()

    async def main():
        try:
            count = await cleanup(apply=args.apply)
            print(f"{'Cleaned' if args.apply else 'Eligible'}: {count} report runs.")
        finally:
            await engine.dispose()

    asyncio.run(main())
