"""One user-owned sticky note for the study dashboard."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.models import QuickNote, User


router = APIRouter(prefix="/quick-note", tags=["quick note"])


class ChecklistLine(BaseModel):
    id: uuid.UUID
    text: str = Field(max_length=500)
    checked: bool = False


class QuickNoteSave(BaseModel):
    body: str = Field(max_length=100_000)
    checklist: list[ChecklistLine] = Field(max_length=500)
    revision: int = Field(ge=0)


def _note_out(note: QuickNote | None) -> dict[str, Any]:
    if note is None:
        return {"body": "", "checklist": [], "revision": 0, "updated_at": None}
    return {
        "body": note.body,
        "checklist": note.checklist,
        "revision": note.revision,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


@router.get("")
async def get_quick_note(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return _note_out(await db.get(QuickNote, user.id))


@router.put("")
async def save_quick_note(
    body: QuickNoteSave,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if len({line.id for line in body.checklist}) != len(body.checklist):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Checklist items must be unique")

    values = [line.model_dump(mode="json") for line in body.checklist]
    from app.services.account_lifecycle import assert_user_active
    await assert_user_active(db, user.id, lock=True)
    saved_body = body.body
    from app.core.config import settings
    if settings.content_encryption_mode == "required":
        from app.services.encrypted_orm import encrypt_value
        saved_body = encrypt_value(body.body, table="quick_notes", field="body", owner=str(user.id), resource=str(user.id))
        values = encrypt_value(values, table="quick_notes", field="checklist", owner=str(user.id), resource=str(user.id))
    statement = insert(QuickNote).values(
        user_id=user.id,
        body=saved_body,
        checklist=values,
        revision=1,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[QuickNote.user_id],
        set_={
            "body": saved_body,
            "checklist": values,
            "revision": QuickNote.revision + 1,
            "updated_at": func.now(),
        },
        where=QuickNote.revision == body.revision,
    ).returning(QuickNote)
    note = (await db.execute(statement.execution_options(populate_existing=True))).scalar_one_or_none()
    if note is None:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This note changed elsewhere. Copy your changes before refreshing.")
    await db.commit()
    return _note_out(note)
