"""Bounded asynchronous private export; ciphertext on disk, no token export."""
import asyncio
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.lifecycle import ExportJob
from app.models.models import Base, File, Note, User
from app.models.lesson_models import Lesson, LessonItem
from app.models.review_models import QuizItem, QuizSession
from app.services.account_lifecycle import assert_user_active
from app.services.content_crypto import MAX_BYTES, atomic_private_write, seal, unseal
from app.services.file_storage import FileStorage

# Secrets, service internals, and other organizations' records are never exported.
EXCLUDED = {"google_calendar_tokens", "processing_jobs", "calendar_sync_logs"}


def _value(value):
    if isinstance(value, (datetime, uuid.UUID)):
        return str(value)
    if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
        return value
    return str(value)


async def run_one(factory=SessionLocal):
    async with factory() as db:
        job = (await db.execute(select(ExportJob).where(ExportJob.state == "pending")
                    .order_by(ExportJob.created_at).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
        if not job:
            return False
        job_id = job.id
        try:
            await assert_user_active(db, job.user_id)
            data = {}
            for mapper in Base.registry.mappers:
                model = mapper.class_
                table = mapper.local_table.name
                if table in EXCLUDED or table.startswith("school_") or table in {"schools", "privacy_export_jobs", "reauthentication_grants", "security_events", "deletion_requests"}:
                    continue
                if model is User:
                    rows = [await db.get(User, job.user_id)]
                elif model is LessonItem:
                    rows = list((await db.execute(select(LessonItem).join(Lesson, Lesson.id == LessonItem.lesson_id)
                        .where(Lesson.user_id == job.user_id).limit(10001))).scalars())
                elif model is QuizItem:
                    rows = list((await db.execute(select(QuizItem).join(QuizSession, QuizSession.id == QuizItem.quiz_session_id)
                        .where(QuizSession.user_id == job.user_id).limit(10001))).scalars())
                elif hasattr(model, "user_id"):
                    rows = list((await db.execute(select(model).where(model.user_id == job.user_id).limit(10001))).scalars())
                else:
                    continue
                if len(rows) > 10000:
                    raise ValueError("export_too_large")
                data[table] = [{column.key: _value(getattr(row, column.key)) for column in mapper.columns
                                if column.key not in {"vault_path", "storage_path"}} for row in rows if row is not None]
            encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            if len(encoded) > MAX_BYTES:
                raise ValueError("export_too_large")
            archive = io.BytesIO()
            total = len(encoded)
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("account.json", encoded)
                for note in (await db.execute(select(Note).where(Note.user_id == job.user_id))).scalars():
                    markdown = f"# {note.title or 'Untitled note'}\n\n{note.content or ''}\n".encode()
                    total += len(markdown)
                    if total > MAX_BYTES:
                        raise ValueError("export_too_large")
                    bundle.writestr(f"notes/{note.id}.md", markdown)
                for item in (await db.execute(select(File).where(File.user_id == job.user_id))).scalars():
                    # Opaque paths prevent original-name traversal in archives.
                    content = await asyncio.to_thread(FileStorage.get_file_content, item.storage_path, user_id=job.user_id, resource_id=item.id)
                    total += len(content)
                    if total > MAX_BYTES:
                        raise ValueError("export_too_large")
                    bundle.writestr(f"uploads/{item.id}.bin", content)
            content = archive.getvalue()
            await assert_user_active(db, job.user_id, lock=True)
            relative = f"users/{job.user_id}/exports/{job.id}.pixie"
            ciphertext = await asyncio.to_thread(seal, content, domain="private", owner=str(job.user_id),
                                                resource=str(job.id), field="privacy_export")
            await asyncio.to_thread(atomic_private_write, FileStorage.get_file_path(relative), ciphertext.encode())
            job.artifact = relative
            job.state = "ready"
            await db.commit()
        except Exception:
            await db.rollback()
            # Refuse partial exports instead of silently dropping content.
            job = await db.get(ExportJob, job_id)
            if job:
                job.state = "failed"
                await db.commit()
    return True


async def download(job):
    raw = await asyncio.to_thread(FileStorage.get_file_path(job.artifact, user_id=job.user_id).read_text)
    return await asyncio.to_thread(unseal, raw, domain="private", owner=str(job.user_id),
                                   resource=str(job.id), field="privacy_export")
