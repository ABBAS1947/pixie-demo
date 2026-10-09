"""Notes API — canonical database CRUD + pgvector search, user-scoped.

Every endpoint resolves the user from the JWT (never client-supplied
user_id). Readable Markdown is generated only through authorized exports.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.folder_colors import next_folder_color
from app.core.rate_limit import note_search_limiter
from app.models.models import File as FileModel, Folder, Note, User
from app.services.ollama_client import embed_text
from app.services.vault_service import (
    delete_note_file,
    overwrite_note_file,
    vault_path_for,
    write_note_file,
)

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteCreate(BaseModel):
    """Blank drafts are allowed (title/content empty) — the editor creates a
    blank note on "New note" and autosave fills it in."""

    title: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=20000)
    tags: str | None = Field(default=None, max_length=500)
    folder_id: uuid.UUID | None = None


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    content: str | None = Field(default=None, max_length=20000)
    tags: str | None = Field(default=None, max_length=500)
    folder_id: uuid.UUID | None = None


class FolderInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)


async def _embed_text(title: str, content: str) -> list[float]:
    """Embed non-empty text; blank drafts fall back to 'untitled'."""
    text = f"{title}\n{content}".strip() or "untitled"
    return await embed_text(text)


def _note_out(n: Note) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "title": n.title,
        "content": n.content,
        "excerpt": n.content[:220],
        "tags": [t for t in (n.tags or "").split(",") if t],
        "folder_id": str(n.folder_id) if n.folder_id else None,
        "vault_path": None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


@router.get("")
async def list_notes(
    folder_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    query = select(Note).where(Note.user_id == user.id)
    if folder_id is not None:
        query = query.where(Note.folder_id == folder_id)
    rows = (await db.execute(query.order_by(Note.updated_at.desc()).offset(offset).limit(limit))).scalars().all()
    return [_note_out(n) for n in rows]


@router.get("/folders")
async def list_note_folders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    folders = (await db.execute(select(Folder).where(Folder.user_id == user.id).order_by(Folder.name))).scalars().all()
    note_counts = dict((await db.execute(
        select(Note.folder_id, func.count(Note.id)).where(Note.user_id == user.id, Note.folder_id.is_not(None)).group_by(Note.folder_id)
    )).all())
    file_counts = dict((await db.execute(
        select(FileModel.folder_id, func.count(FileModel.id)).where(FileModel.user_id == user.id, FileModel.folder_id.is_not(None)).group_by(FileModel.folder_id)
    )).all())
    return [{"id": str(folder.id), "name": folder.name, "color": folder.color, "created_at": folder.created_at.isoformat() if folder.created_at else None, "note_count": note_counts.get(folder.id, 0), "file_count": file_counts.get(folder.id, 0)} for folder in folders]


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def create_note_folder(body: FolderInput, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Folder name cannot be blank")
    duplicate = (await db.execute(select(Folder.id).where(Folder.user_id == user.id, func.lower(func.trim(Folder.name)) == name.lower()))).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "A folder with that name already exists")
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing_colors = (await db.execute(select(Folder.color).where(Folder.user_id == user.id))).scalars().all()
    folder = Folder(user_id=user.id, name=name, color=next_folder_color(existing_colors))
    db.add(folder)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A folder with that name already exists")
    await db.refresh(folder)
    return {"id": str(folder.id), "name": folder.name, "color": folder.color, "created_at": folder.created_at.isoformat() if folder.created_at else None, "note_count": 0, "file_count": 0}


@router.put("/folders/{folder_id}")
async def rename_note_folder(folder_id: uuid.UUID, body: FolderInput, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    folder = (await db.execute(select(Folder).where(Folder.id == folder_id, Folder.user_id == user.id))).scalar_one_or_none()
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Folder name cannot be blank")
    duplicate = (await db.execute(select(Folder.id).where(Folder.user_id == user.id, Folder.id != folder_id, func.lower(func.trim(Folder.name)) == name.lower()))).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "A folder with that name already exists")
    folder.name = name
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A folder with that name already exists")
    await db.refresh(folder)
    return {"id": str(folder.id), "name": folder.name, "color": folder.color, "created_at": folder.created_at.isoformat() if folder.created_at else None}


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note_folder(folder_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    folder = (await db.execute(select(Folder).where(Folder.id == folder_id, Folder.user_id == user.id))).scalar_one_or_none()
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
    await db.execute(Note.__table__.update().where(Note.folder_id == folder_id, Note.user_id == user.id).values(folder_id=None))
    await db.delete(folder)
    await db.commit()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.folder_id is not None:
        folder_exists = (await db.execute(select(Folder.id).where(Folder.id == body.folder_id, Folder.user_id == user.id))).scalar_one_or_none()
        if folder_exists is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
    # Embed first (the fallible network call), then write the vault file,
    # then insert. If the DB insert fails, remove the orphan file.
    embedding = await _embed_text(body.title, body.content)
    vault_path = await write_note_file(user, body.title, body.content)
    try:
        note = Note(
            user_id=user.id,
            title=body.title,
            content=body.content,
            tags=body.tags,
            folder_id=body.folder_id,
            embedding=embedding,
            vault_path=vault_path,
        )
        db.add(note)
        await db.commit()
        await db.refresh(note)
    except Exception:
        delete_note_file(vault_path)
        raise
    return _note_out(note)


@router.get("/search")
async def search_notes(
    q: str = Query(min_length=1, max_length=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Semantic search over the user's notes via pgvector cosine distance."""
    note_search_limiter.check(f"notes-search:{user.id}")
    embedding = await embed_text(q)
    rows = (
        await db.execute(
            select(Note)
            .where(Note.user_id == user.id)
            .order_by(Note.embedding.cosine_distance(embedding))
            .limit(10)
        )
    ).scalars().all()
    return [_note_out(n) for n in rows]


@router.put("/{note_id}")
async def update_note(
    note_id: uuid.UUID,
    body: NoteUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update title/content/tags; re-embed and keep the vault mirror in sync."""
    note = (
        await db.execute(select(Note).where(Note.id == note_id, Note.user_id == user.id))
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")

    if body.title is not None:
        note.title = body.title
    if body.content is not None:
        note.content = body.content
    if body.tags is not None:
        note.tags = body.tags
    if "folder_id" in body.model_fields_set:
        if body.folder_id is None:
            note.folder_id = None
        else:
            belongs = (await db.execute(select(Folder.id).where(Folder.id == body.folder_id, Folder.user_id == user.id))).scalar_one_or_none()
            if belongs is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
            note.folder_id = body.folder_id

    note.embedding = await _embed_text(note.title, note.content)

    # Vault mirror: same title -> overwrite own file; new title -> fresh slug
    # (collision-safe) and remove the old file.
    # DB is canonical; legacy mirrors are removed during approved migration,
    # not before the transaction commits or through silent best-effort writes.

    await db.commit()
    await db.refresh(note)
    return _note_out(note)


@router.get("/{note_id}")
async def get_note(
    note_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    note = (
        await db.execute(select(Note).where(Note.id == note_id, Note.user_id == user.id))
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    return _note_out(note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    note = (
        await db.execute(select(Note).where(Note.id == note_id, Note.user_id == user.id))
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    delete_note_file(note.vault_path)
    await db.delete(note)
    await db.commit()
    return None
