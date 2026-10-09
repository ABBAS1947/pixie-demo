"""Feedback API — simple endpoint for beta testers to report bugs and feedback."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.models import Feedback, User
from app.api.deps import get_current_user

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    feedback_type: str = Field(pattern="^(bug|feedback|feature)$")
    message: str = Field(min_length=1, max_length=2000)
    page: str | None = Field(default=None, max_length=100)


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit feedback or bug report."""
    fb = Feedback(
        user_id=user.id,
        feedback_type=body.feedback_type,
        message=body.message,
        page=body.page,
    )
    db.add(fb)
    await db.commit()
    return {"submitted": True, "id": str(fb.id)}
