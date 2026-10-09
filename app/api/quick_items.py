"""Small user-owned notes and checklist items for the study dashboard."""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.models import QuickItem, User

router = APIRouter(prefix="/quick-items", tags=["quick items"])


class QuickItemCreate(BaseModel):
    kind: Literal["note", "task"]
    content: str = Field(min_length=1, max_length=500)


class QuickItemUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=500)
    completed: bool | None = None


def _item_out(item: QuickItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "kind": item.kind,
        "content": item.content,
        "completed": item.completed,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


async def _owned_item(db: AsyncSession, user: User, item_id: uuid.UUID) -> QuickItem:
    item = (await db.execute(
        select(QuickItem).where(QuickItem.id == item_id, QuickItem.user_id == user.id)
    )).scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quick item not found")
    return item


@router.get("")
async def list_quick_items(
    limit: int = Query(default=100, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    items = (await db.execute(
        select(QuickItem)
        .where(QuickItem.user_id == user.id)
        .order_by(QuickItem.completed.asc(), QuickItem.updated_at.desc())
        .limit(limit)
    )).scalars().all()
    return [_item_out(item) for item in items]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_quick_item(
    body: QuickItemCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = QuickItem(user_id=user.id, kind=body.kind, content=body.content.strip())
    if not item.content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a short note or task")
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item_out(item)


@router.patch("/{item_id}")
async def update_quick_item(
    item_id: uuid.UUID,
    body: QuickItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = await _owned_item(db, user, item_id)
    changes = body.model_dump(exclude_unset=True)
    if "content" in changes:
        item.content = (changes["content"] or "").strip()
        if not item.content:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a short note or task")
    if "completed" in changes and changes["completed"] is not None:
        item.completed = changes["completed"]
    await db.commit()
    await db.refresh(item)
    return _item_out(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quick_item(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    item = await _owned_item(db, user, item_id)
    await db.delete(item)
    await db.commit()
