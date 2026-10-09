"""Expiry removes live artifacts; backup completion needs separate evidence."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import SessionLocal
from app.models.lifecycle import ExportJob, ReauthenticationGrant
from app.models.school import SchoolRecord
from app.services.file_storage import FileStorage

async def run_one(factory=SessionLocal):
    now = datetime.now(timezone.utc)
    async with factory() as db:
        jobs = list((await db.execute(select(ExportJob).where(ExportJob.expires_at <= now)
            .with_for_update(skip_locked=True).limit(100))).scalars())
        for job in jobs:
            if job.artifact:
                FileStorage.delete_file(job.artifact, user_id=job.user_id)
            await db.delete(job)
        await db.execute(ReauthenticationGrant.__table__.delete().where(ReauthenticationGrant.expires_at <= now))
        result = await db.execute(SchoolRecord.__table__.delete().where(SchoolRecord.expires_at <= now))
        await db.commit()
        return bool(jobs) or bool(result.rowcount)
