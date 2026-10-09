# app/api/files.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Body, Query
from datetime import datetime, timezone
import asyncio
import threading
import uuid
from pydantic import BaseModel, Field

from app.core.db import async_session
from app.core.folder_colors import next_folder_color
from app.models.models import File as FileModel, Folder, Deadline, Note
from app.services.file_storage import FileStorage
from app.services.file_processor import FileProcessor
from app.services.file_classifier import FileClassifier
from app.services.note_generator import generate_smart_note
from app.services.ollama_client import embed_text
from app.services.vault_service import write_note_file
from app.api.deps import get_current_user
from app.core.utils import safe_uuid
from app.core.rate_limit import upload_limiter
from app.models.models import User
from sqlalchemy import func, select, text as sql_text

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.txt', '.png', '.jpg', '.jpeg', '.gif', '.webp'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_UPLOAD_CHUNK = 1024 * 1024  # 1MB chunks for streaming limit check

# Magic bytes for allowed file types
_MAGIC_BYTES = {
    b'%PDF': '.pdf',
    b'PK\x03\x04': '.docx',  # ZIP-based (docx)
    b'\xd0\xcf\x11\xe0': '.doc',  # OLE-based (doc)
    b'\x89PNG': '.png',
    b'\xff\xd8\xff': '.jpg',
    b'GIF8': '.gif',
}

# Per-user concurrent upload limit
_user_upload_counts: dict[str, int] = {}
MAX_CONCURRENT_UPLOADS_PER_USER = 3
# Hold references to background tasks so the loop doesn't garbage-collect
# them mid-processing ("Task was destroyed but it is pending").
_bg_tasks: set[asyncio.Task] = set()
_processing_slots_lock = threading.Lock()
_pending_processing_by_user: dict[str, int] = {}
_pending_processing_total = 0
MAX_PENDING_PROCESSING_TOTAL = 20
MAX_PENDING_PROCESSING_PER_USER = 3


def _reserve_processing_slot(user_id: str) -> bool:
    global _pending_processing_total
    with _processing_slots_lock:
        if _pending_processing_total >= MAX_PENDING_PROCESSING_TOTAL:
            return False
        if _pending_processing_by_user.get(user_id, 0) >= MAX_PENDING_PROCESSING_PER_USER:
            return False
        _pending_processing_total += 1
        _pending_processing_by_user[user_id] = _pending_processing_by_user.get(user_id, 0) + 1
        return True


def _release_processing_slot(user_id: str) -> None:
    global _pending_processing_total
    with _processing_slots_lock:
        count = _pending_processing_by_user.get(user_id, 0)
        if count <= 1:
            _pending_processing_by_user.pop(user_id, None)
        else:
            _pending_processing_by_user[user_id] = count - 1
        _pending_processing_total = max(0, _pending_processing_total - 1)

_DEADLINE_KINDS = {"assignment", "exam", "project"}


class FileMetadataInput(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    subject: str | None = Field(default=None, max_length=255)


class FolderInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class MoveFilesInput(BaseModel):
    file_ids: list[str] = Field(default_factory=list, max_length=100)
    folder_id: str | None = None


async def _read_upload_streaming(file: UploadFile) -> bytes:
    """Read upload in chunks with streaming byte limit enforcement.
    Raises 400 if file exceeds MAX_FILE_SIZE before full read."""
    from fastapi import HTTPException

    chunks = []
    total = 0
    while True:
        chunk = await file.read(MAX_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_magic_bytes(content: bytes, expected_ext: str) -> bool:
    """Check common signatures without rejecting valid text or images.

    Text files have no portable magic number, PDFs may contain a short BOM or
    whitespace before their header, and WebP identifies itself at byte 8.
    The old exact four-byte check rejected otherwise valid uploads in all of
    those cases.
    """
    if expected_ext == '.txt':
        # Plain text has no signature. Reject only known binary formats.
        return not any(content.startswith(magic) for magic in _MAGIC_BYTES)
    if expected_ext == '.pdf':
        return content[:1024].lstrip(b"\xef\xbb\xbf\x00 \t\r\n").startswith(b'%PDF')
    if expected_ext == '.webp':
        return len(content) >= 12 and content[:4] == b'RIFF' and content[8:12] == b'WEBP'
    for magic, ext in _MAGIC_BYTES.items():
        if content.startswith(magic):
            return ext == expected_ext
    return False


def _parse_due(value) -> datetime | None:
    """Tolerant date parse: ISO 8601, YYYY-MM-DD, or common day formats."""
    if not value:
        return None
    v = str(value).strip()
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    description: str = Form(default=""),
    subject: str = Form(default=""),
    folder_id: str | None = Form(default=None),
    note_mode: str = Form(default="full_text"),
    current_user = Depends(get_current_user)
):
    ext = file.filename.split('.')[-1].lower()
    if f'.{ext}' not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not supported")
    if note_mode not in {"summary", "full_text"}:
        raise HTTPException(status_code=400, detail="Choose summary or full-text notes")

    # MEDIUM-01: Rate limit check
    upload_limiter.check(f"upload:{current_user.id}")

    # HIGH-05: Per-user concurrent upload limit
    user_id_str = str(current_user.id)
    if not _reserve_processing_slot(user_id_str):
        raise HTTPException(status_code=429, detail="Too many files are already being processed. Please wait.")
    processing_reserved = True
    if _user_upload_counts.get(user_id_str, 0) >= MAX_CONCURRENT_UPLOADS_PER_USER:
        _release_processing_slot(user_id_str)
        raise HTTPException(status_code=429, detail="Too many concurrent uploads. Please wait.")
    _user_upload_counts[user_id_str] = _user_upload_counts.get(user_id_str, 0) + 1

    try:
        # HIGH-05: Streaming byte limit (reads in chunks, stops at limit)
        content = await _read_upload_streaming(file)
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty file")

        # Do not reject an upload solely because its first bytes do not match
        # the filename extension. Valid PDFs and office exports can contain
        # leading metadata, and text files have no reliable magic signature.
        # The processor remains responsible for extracting supported content;
        # unreadable content is reported as a processing failure after storage
        # instead of silently blocking the upload.

        # SECURITY (HIGH-04): Verify folder ownership before assigning.
        resolved_folder_id = safe_uuid(folder_id)
        if folder_id is not None and resolved_folder_id is None:
            raise HTTPException(status_code=400, detail="Invalid folder")
        if resolved_folder_id is not None:
            async with async_session() as db:
                from sqlalchemy import select as _sel
                folder_owner = (
                    await db.execute(
                        _sel(Folder.id).where(
                            Folder.id == resolved_folder_id,
                            Folder.user_id == current_user.id,
                        )
                    )
                ).scalar_one_or_none()
                if folder_owner is None:
                    raise HTTPException(status_code=400, detail="Folder not found or does not belong to you")

        file_id = uuid.uuid4()
        storage_path = await asyncio.to_thread(FileStorage.save_file, str(current_user.id), file.filename, content, resource_id=file_id)
        async with async_session() as db:
            file_record = FileModel(
                id=file_id,
                user_id=current_user.id,
                storage_path=storage_path,
                original_name=file.filename,
                file_type=ext,
                file_size=len(content),
                mime_type=file.content_type,
                status='pending',
                title=title or file.filename.rsplit('.', 1)[0],
                description=description or None,
                subject=subject or None,
                folder_id=resolved_folder_id,
                note_mode=note_mode,
            )
            db.add(file_record)
            await db.commit()
            await db.refresh(file_record)
        file_id = file_record.id

    except Exception:
        if processing_reserved:
            _release_processing_slot(user_id_str)
        raise
    finally:
        _user_upload_counts[user_id_str] = max(0, _user_upload_counts.get(user_id_str, 1) - 1)

    try:
        task = asyncio.create_task(process_file_background(str(file_id)))
    except Exception:
        _release_processing_slot(user_id_str)
        raise
    processing_reserved = False
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    task.add_done_callback(lambda _task, uid=user_id_str: _release_processing_slot(uid))

    return {"id": str(file_id), "filename": file.filename, "status": "pending"}

@router.get("/")
async def get_files(
    current_user = Depends(get_current_user),
    status: str = None,
    folder_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=100),
):
    async with async_session() as db:
        from sqlalchemy import select
        query = select(FileModel).where(FileModel.user_id == current_user.id)
        if status:
            query = query.where(FileModel.status == status)
        if folder_id:
            target = safe_uuid(folder_id)
            if target is None:
                raise HTTPException(status_code=400, detail="Invalid folder")
            query = query.where(FileModel.folder_id == target)
        query = query.order_by(FileModel.uploaded_at.desc()).limit(limit)
        
        result = await db.execute(query)
        files = result.scalars().all()
        
        return {"files": [{
            "id": str(f.id),
            "original_name": f.original_name,
            "title": f.title or f.original_name,
            "description": f.description,
            "subject": f.subject,
            "folder_id": str(f.folder_id) if f.folder_id else None,
            "file_type": f.file_type,
            "file_size": f.file_size,
            "status": f.status,
            "needs_ocr": f.needs_ocr,
            "classification": f.classification,
            "processed_note_id": str(f.processed_note_id) if f.processed_note_id else None,
            "note_mode": f.note_mode,
            "error_message": f.error_message,
            "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
        } for f in files]}


@router.put("/{file_id}")
async def update_file_metadata(file_id: str, body: FileMetadataInput, current_user=Depends(get_current_user)):
    async with async_session() as db:
        file = (await db.execute(select(FileModel).where(FileModel.id == file_id, FileModel.user_id == current_user.id))).scalar_one_or_none()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        if body.title is not None:
            file.title = body.title.strip() or file.original_name.rsplit('.', 1)[0]
        if body.description is not None:
            file.description = body.description.strip() or None
        if body.subject is not None:
            file.subject = body.subject.strip() or None
        await db.commit()
        await db.refresh(file)
        return {"id": str(file.id), "original_name": file.original_name, "title": file.title or file.original_name, "description": file.description, "subject": file.subject, "folder_id": str(file.folder_id) if file.folder_id else None, "file_type": file.file_type, "file_size": file.file_size, "status": file.status, "needs_ocr": file.needs_ocr, "classification": file.classification, "processed_note_id": str(file.processed_note_id) if file.processed_note_id else None, "note_mode": file.note_mode, "error_message": file.error_message, "uploaded_at": file.uploaded_at.isoformat() if file.uploaded_at else None}

@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    current_user = Depends(get_current_user)
):
    async with async_session() as db:
        from sqlalchemy import select
        stmt = select(FileModel).where(FileModel.id == file_id, FileModel.user_id == current_user.id)
        result = await db.execute(stmt)
        file = result.scalar_one_or_none()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")

        FileStorage.delete_file(file.storage_path, user_id=current_user.id, resource_id=file.id)
        await db.delete(file)
        await db.commit()
        return {"success": True}


@router.post("/{file_id}/process")
async def retry_file_processing(file_id: str, current_user=Depends(get_current_user)):
    """Retry a consent-blocked or failed transformation without reuploading the source."""
    user_id = str(current_user.id)
    if not _reserve_processing_slot(user_id):
        raise HTTPException(status_code=429, detail="Too many files are already being processed. Please wait.")
    try:
        async with async_session() as db:
            file = (await db.execute(select(FileModel).where(FileModel.id == file_id, FileModel.user_id == current_user.id))).scalar_one_or_none()
            if file is None:
                raise HTTPException(status_code=404, detail="File not found")
            if file.status not in {"pending_consent", "failed"}:
                raise HTTPException(status_code=409, detail="This file is not ready to retry")
            file.status = "pending"
            file.error_message = None
            await db.commit()
        task = asyncio.create_task(process_file_background(file_id))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
        task.add_done_callback(lambda _task, uid=user_id: _release_processing_slot(uid))
        return {"id": file_id, "status": "pending"}
    except Exception:
        _release_processing_slot(user_id)
        raise


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    current_user = Depends(get_current_user)
):
    """Serve the raw file for viewing in the browser."""
    from fastapi.responses import Response

    async with async_session() as db:
        from sqlalchemy import select
        stmt = select(FileModel).where(FileModel.id == file_id, FileModel.user_id == current_user.id)
        result = await db.execute(stmt)
        file = result.scalar_one_or_none()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")

    file_path = FileStorage.get_file_path(file.storage_path, user_id=current_user.id, resource_id=file.id)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    mime_map = {
        'pdf': 'application/pdf',
        'txt': 'text/plain',
        'doc': 'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
        'png': 'image/png', 'gif': 'image/gif',
    }
    mime = mime_map.get(file.file_type, 'application/octet-stream')
    from app.services.account_lifecycle import assert_user_active
    async with async_session() as db:
        await assert_user_active(db, current_user.id)
    data = await asyncio.to_thread(FileStorage.get_file_content, file.storage_path, user_id=current_user.id, resource_id=file.id)
    async with async_session() as db:
        await assert_user_active(db, current_user.id)
    from urllib.parse import quote
    return Response(content=data, media_type=mime, headers={"Cache-Control": "no-store",
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(file.original_name, safe="")})


# ─── Folder CRUD ──────────────────────────────────────────────────────────────

@router.post("/folders")
async def create_folder(
    body: FolderInput,
    current_user = Depends(get_current_user)
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name is required")
    async with async_session() as db:
        duplicate = (await db.execute(select(Folder.id).where(Folder.user_id == current_user.id, func.lower(func.trim(Folder.name)) == name[:255].lower()))).scalar_one_or_none()
        if duplicate:
            raise HTTPException(status_code=409, detail="A folder with that name already exists")
        await db.execute(select(User.id).where(User.id == current_user.id).with_for_update())
        existing_colors = (await db.execute(select(Folder.color).where(Folder.user_id == current_user.id))).scalars().all()
        folder = Folder(user_id=current_user.id, name=name[:255], color=next_folder_color(existing_colors))
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        return {"id": str(folder.id), "name": folder.name, "color": folder.color, "created_at": folder.created_at.isoformat()}


@router.get("/folders")
async def list_folders(current_user = Depends(get_current_user)):
    async with async_session() as db:
        from sqlalchemy import select
        folders = (await db.execute(
            select(Folder).where(Folder.user_id == current_user.id).order_by(Folder.name)
        )).scalars().all()
        return {"folders": [{"id": str(f.id), "name": f.name, "color": f.color, "created_at": f.created_at.isoformat() if f.created_at else None} for f in folders]}


@router.put("/folders/{folder_id}")
async def rename_folder(
    folder_id: str,
    body: FolderInput,
    current_user = Depends(get_current_user)
):
    async with async_session() as db:
        from sqlalchemy import select
        folder = (await db.execute(
            select(Folder).where(Folder.id == folder_id, Folder.user_id == current_user.id)
        )).scalar_one_or_none()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        name = body.name.strip()[:255]
        duplicate = (await db.execute(select(Folder.id).where(Folder.user_id == current_user.id, Folder.id != folder.id, func.lower(func.trim(Folder.name)) == name.lower()))).scalar_one_or_none()
        if duplicate:
            raise HTTPException(status_code=409, detail="A folder with that name already exists")
        folder.name = name
        await db.commit()
        return {"id": str(folder.id), "name": folder.name, "color": folder.color}


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    current_user = Depends(get_current_user)
):
    async with async_session() as db:
        from sqlalchemy import select
        folder = (await db.execute(
            select(Folder).where(Folder.id == folder_id, Folder.user_id == current_user.id)
        )).scalar_one_or_none()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        # Unset folder_id on files in this folder (SET NULL via FK)
        await db.delete(folder)
        await db.commit()
        return {"success": True}


@router.post("/move")
async def move_files_to_folder(
    body: MoveFilesInput,
    current_user = Depends(get_current_user)
):
    """Move one or more files to a folder (or unset folder if folder_id is null)."""
    async with async_session() as db:
        from sqlalchemy import select
        target = safe_uuid(body.folder_id)

        # SECURITY (HIGH-04): Verify destination folder belongs to the user.
        if target is not None:
            folder_owner = (
                await db.execute(
                    select(Folder.id).where(
                        Folder.id == target,
                        Folder.user_id == current_user.id,
                    )
                )
            ).scalar_one_or_none()
            if folder_owner is None:
                raise HTTPException(status_code=400, detail="Destination folder not found or does not belong to you")

        stmt = select(FileModel).where(
            FileModel.id.in_([safe_uuid(fid) for fid in body.file_ids if safe_uuid(fid)]),
            FileModel.user_id == current_user.id,
        )
        files = (await db.execute(stmt)).scalars().all()
        for f in files:
            f.folder_id = target
        await db.commit()
        return {"moved": len(files)}


async def process_file_background(file_id: str):
    from sqlalchemy import select
    from app.core.db import async_session
    
    async with async_session() as db:
        stmt = select(FileModel).where(FileModel.id == file_id)
        result = await db.execute(stmt)
        file = result.scalar_one_or_none()
        if not file:
            return
        from app.services.account_lifecycle import assert_user_active
        await assert_user_active(db, file.user_id)
        
        file.status = 'processing'
        await db.commit()
        
        try:
            content = await asyncio.to_thread(FileStorage.get_file_content, file.storage_path, user_id=file.user_id, resource_id=file.id)
            text, needs_vision = await asyncio.to_thread(
                FileProcessor.extract_text, file.file_type, content
            )

            preference_row = await db.execute(
                sql_text("SELECT review_preferences FROM users WHERE id = :user_id"),
                {"user_id": file.user_id},
            )
            preferences = preference_row.scalar_one_or_none() or {}
            external_processing_consent = bool(preferences.get("external_processing_consent"))

            # If text extraction yielded too little, try the vision model.
            # This covers images, scanned PDFs, and any file where pdfplumber
            # / docx2txt couldn't extract meaningful content.
            if needs_vision or not text or len(text.strip()) < 10:
                if not external_processing_consent:
                    file.status = 'pending_consent'
                    file.error_message = "External processing consent is required to extract this file"
                    await db.commit()
                    return
                vision_text = await FileProcessor.vision_extract(file.file_type, content)
                if vision_text and len(vision_text.strip()) >= 10:
                    text = vision_text
                else:
                    file.status = 'failed'
                    file.error_message = "Could not extract text from this file"
                    await db.commit()
                    return

            file.extracted_text = text
            await assert_user_active(db, file.user_id)
            classification = await FileClassifier.classify(text) if external_processing_consent else 'other'
            file.classification = classification

            # ── Smart note generation FIRST (all classifications) ────────
            # Create the note before deadlines so we can link them.
            user = (await db.execute(
                select(User).where(User.id == file.user_id)
            )).scalar_one_or_none()
            grade_level = user.grade_level if user else None

            note_title = file.original_name.rsplit('.', 1)[0][:500]
            if file.note_mode == "summary" and not external_processing_consent:
                file.status = 'pending_consent'
                file.error_message = "Enable external processing consent in Settings to create a summary. The original file is safe."
                await db.commit()
                return

            if file.note_mode == "summary":
                note_content = await generate_smart_note(
                    raw_text=text,
                    grade_level=grade_level,
                    require_generated=True,
                )
            else:
                note_content = f"# {note_title}\n\n{text.strip()}"

            if file.note_mode == "summary":
                first_heading = next((line.lstrip("# ").strip() for line in note_content.splitlines() if line.startswith("# ")), "")
                if first_heading:
                    note_title = first_heading[:500]

            try:
                embedding = await embed_text(f"{note_title}\n{note_content}")
            except Exception:
                embedding = None
            try:
                vault_path = await write_note_file(file.user, note_title, note_content)
            except Exception:
                vault_path = None
            note = Note(
                user_id=file.user_id,
                title=note_title,
                content=note_content,
                folder_id=file.folder_id,
                embedding=embedding,
                vault_path=vault_path,
            )
            db.add(note)
            await db.flush()  # get note.id

            # ── Deadline extraction (syllabus only) ────────────────────
            if classification == 'syllabus' and external_processing_consent:
                deadlines = await FileClassifier.extract_deadlines(text)
                for d in deadlines:
                    due = _parse_due(d.get('due_date') or d.get('due_at'))
                    if due is None:
                        continue
                    kind = d.get('kind', 'assignment')
                    if kind not in _DEADLINE_KINDS:
                        kind = 'assignment'
                    deadline = Deadline(
                        user_id=file.user_id,
                        title=str(d.get('title', 'Untitled'))[:500],
                        due_at=due,
                        kind=kind,
                        source='file_upload',
                        source_note_id=note.id,
                        confirmed=False,
                    )
                    db.add(deadline)

            file.processed_note_id = note.id
            file.status = 'processed'
            file.processed_at = datetime.now(timezone.utc)
            await assert_user_active(db, file.user_id, lock=True)
            await db.commit()

        except Exception as e:
            file.status = 'failed'
            file.error_message = "File processing is temporarily unavailable"
            await db.commit()
