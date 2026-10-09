"""Teacher transcript — per-child teaching record.

GET /teach/v2/transcript answers the school's "what data" question with one
read-only call. No LLM, no writes. build_transcript() is shared with the
teacher dashboard endpoints.
"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.users import _auth_id_from_token
from app.core.db import get_db
from app.models.intelligence_models import ConversationInsight
from app.models.lesson_models import Lesson, LessonItem, TurnEvent
from app.models.mastery_models import LearnerProfile, Mastery
from app.models.models import User

router = APIRouter(tags=["teach-v2"])
bearer = HTTPBearer(auto_error=False)


async def build_transcript(db: AsyncSession, user: User) -> dict:
    lessons = list(
        (
            await db.execute(
                select(Lesson)
                .where(Lesson.user_id == user.id)
                .order_by(Lesson.updated_at.desc())
            )
        ).scalars().all()
    )

    out_lessons = []
    for les in lessons:
        items = list(
            (
                await db.execute(
                    select(LessonItem)
                    .where(LessonItem.lesson_id == les.id)
                    .order_by(LessonItem.created_at.asc())
                )
            ).scalars().all()
        )
        events = list(
            (
                await db.execute(
                    select(TurnEvent)
                    .where(TurnEvent.lesson_id == les.id)
                    .order_by(TurnEvent.turn_no.asc())
                )
            ).scalars().all()
        )
        mastery = list(
            (
                await db.execute(
                    select(Mastery).where(
                        Mastery.user_id == user.id,
                        Mastery.concept_key.like(les.topic_norm + "::%"),
                    )
                )
            ).scalars().all()
        )
        out_lessons.append({
            "topic": les.topic,
            "subject": les.subject,
            "phase": les.phase,
            "chunk_index": les.chunk_index,
            "total_chunks": les.total_chunks,
            "updated_at": les.updated_at.isoformat() if les.updated_at else None,
            "items": [
                {
                    "kind": it.kind,
                    "idx": it.idx,
                    "title": it.title,
                    "body": it.body,
                    "clothing": it.clothing,
                    "check_question": it.check_question,
                    "failure_mode": it.failure_mode,
                }
                for it in items
            ],
            "events": [
                {
                    "turn": ev.turn_no,
                    "signal": ev.student_signal,
                    "move": ev.model_move,
                    "latency_ms": ev.latency_ms,
                    "understood": ev.understood,
                }
                for ev in events
            ],
            "mastery": [
                {
                    "concept": m.concept_label,
                    "p_known": m.p_known,
                    "attempts": m.attempts,
                }
                for m in mastery
            ],
            "probes": sum(1 for ev in events if ev.student_signal == "probe"),
            "escalated": any(ev.model_move == "escalate" for ev in events),
        })

    prof = (
        await db.execute(
            select(LearnerProfile).where(LearnerProfile.user_id == user.id)
        )
    ).scalar_one_or_none()

    insights = list(
        (
            await db.execute(
                select(ConversationInsight)
                .where(ConversationInsight.user_id == user.id)
                .order_by(ConversationInsight.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
    )

    return {
        "student": user.name,
        "grade": user.grade_level,
        "lessons": out_lessons,
        "profile": (
            {
                "advances": prof.advances,
                "probes": prof.probes,
                "escalations": prof.escalations,
                "clothing_wins": prof.clothing_wins,
                "failure_counts": prof.failure_counts,
            }
            if prof
            else None
        ),
        "recent_insights": [
            {"topics": i.topics, "mood": i.mood, "summary": i.summary}
            for i in insights
        ],
    }


@router.get("/teach/v2/transcript")
async def get_transcript(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    auth_id = _auth_id_from_token(credentials)
    user = (
        await db.execute(select(User).where(User.auth_id == auth_id))
    ).scalar_one_or_none()
    if user is None:
        return {"error": "User not provisioned"}
    return await build_transcript(db, user)
