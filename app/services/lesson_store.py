"""Lesson store — Postgres-backed lesson pointers.

Replaces the RAM LessonCache dict. Every function here is a thin query over
the lessons / lesson_items / turn_events tables. One row per
(user_id, topic_norm) so a student can never hold two lessons for one topic.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lesson_models import Lesson, LessonItem, TurnEvent

_WS_RE = re.compile(r"\s+")


def normalize_topic(topic: str) -> str:
    """Lowercase, trim, collapse whitespace. 'WHAT  is Mitosis? ' -> 'what is mitosis?'."""
    return _WS_RE.sub(" ", topic.strip().lower())


async def get_lesson(db: AsyncSession, user_id: uuid.UUID, topic: str) -> Lesson | None:
    norm = normalize_topic(topic)
    return (
        await db.execute(
            select(Lesson).where(Lesson.user_id == user_id, Lesson.topic_norm == norm)
        )
    ).scalar_one_or_none()


async def list_lessons(db: AsyncSession, user_id: uuid.UUID) -> list[Lesson]:
    return list(
        (
            await db.execute(
                select(Lesson)
                .where(Lesson.user_id == user_id)
                .order_by(Lesson.updated_at.desc())
            )
        ).scalars().all()
    )


async def get_or_create_lesson(
    db: AsyncSession,
    user_id: uuid.UUID,
    topic: str,
    session_id: uuid.UUID | None = None,
    grade_level: str | None = None,
) -> tuple[Lesson, bool]:
    """Return (lesson, created). Never raises on duplicates: re-reads on race."""
    norm = normalize_topic(topic)
    existing = (
        await db.execute(
            select(Lesson).where(Lesson.user_id == user_id, Lesson.topic_norm == norm)
        )
    ).scalar_one_or_none()
    if existing:
        return existing, False
    lesson = Lesson(
        user_id=user_id,
        session_id=session_id,
        topic=topic.strip(),
        topic_norm=norm,
        grade_level=grade_level,
        phase="hook",
        chunk_index=0,
        total_chunks=0,
    )
    db.add(lesson)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        existing = (
            await db.execute(
                select(Lesson).where(
                    Lesson.user_id == user_id, Lesson.topic_norm == norm
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing, False
        raise
    return lesson, True


async def get_items(db: AsyncSession, lesson_id: uuid.UUID) -> list[LessonItem]:
    return list(
        (
            await db.execute(
                select(LessonItem)
                .where(LessonItem.lesson_id == lesson_id)
                .order_by(LessonItem.idx.asc(), LessonItem.created_at.asc())
            )
        ).scalars().all()
    )


async def get_current_item(
    db: AsyncSession, lesson: Lesson
) -> LessonItem | None:
    """The item at the lesson pointer. Alts share idx; prefer latest alt on probe."""
    rows = (
        await db.execute(
            select(LessonItem)
            .where(
                LessonItem.lesson_id == lesson.id,
                LessonItem.idx == lesson.chunk_index,
            )
            .order_by(LessonItem.created_at.desc())
        )
    ).scalars().all()
    return rows[0] if rows else None


async def add_item(
    db: AsyncSession,
    lesson: Lesson,
    kind: str,
    body: str,
    idx: int | None = None,
    title: str | None = None,
    clothing: str | None = None,
    check_question: str | None = None,
    failure_mode: str | None = None,
) -> LessonItem:
    item = LessonItem(
        lesson_id=lesson.id,
        idx=lesson.chunk_index if idx is None else idx,
        kind=kind,
        title=title,
        body=body,
        clothing=clothing,
        check_question=check_question,
        failure_mode=failure_mode,
    )
    db.add(item)
    await db.flush()
    return item


async def advance(db: AsyncSession, lesson: Lesson) -> Lesson:
    """Move the pointer one step. Marks complete past the last chunk."""
    if lesson.phase != "build":
        lesson.phase = "build"
    if lesson.total_chunks and lesson.chunk_index >= lesson.total_chunks - 1:
        lesson.phase = "complete"
    else:
        lesson.chunk_index += 1
    await db.flush()
    return lesson


async def set_phase(db: AsyncSession, lesson: Lesson, phase: str) -> Lesson:
    lesson.phase = phase
    await db.flush()
    return lesson


async def record_event(
    db: AsyncSession,
    lesson: Lesson,
    user_id: uuid.UUID,
    student_signal: str,
    model_move: str | None = None,
    latency_ms: int | None = None,
    understood: bool | None = None,
) -> TurnEvent:
    await db.execute(select(Lesson.id).where(Lesson.id == lesson.id).with_for_update())
    turn_no = (
        await db.execute(
            select(func.coalesce(func.max(TurnEvent.turn_no), 0)).where(
                TurnEvent.lesson_id == lesson.id
            )
        )
    ).scalar_one() + 1
    ev = TurnEvent(
        lesson_id=lesson.id,
        user_id=user_id,
        turn_no=turn_no,
        student_signal=student_signal,
        model_move=model_move,
        latency_ms=latency_ms,
        understood=understood,
    )
    db.add(ev)
    await db.flush()
    return ev
