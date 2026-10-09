"""Post-turn worker for Learn mode (Chunk 5).

Fire-and-forget: the hot path already answered. This worker opens its own
DB session and does the slow learning afterwards, best-effort, in order:

1. Deadline extraction from the turn text (cheap prefilter, one LLM call).
2. Honcho message signal so the person-model learns from the exchange.
3. Full intelligence pipeline (insights, profile, facts, archival).

Nothing here may raise. A failed worker logs and dies silently; the
student already has their answer.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)
_EVIDENCE_NAMESPACE = uuid.UUID("6d6f2a62-6ee4-4d8d-bf07-07f6ac2f7e40")


def launch_lesson_post_turn(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    student_text: str,
    assistant_text: str,
    grade_level: str = "",
) -> None:
    """Enqueue background learning. Returns immediately, never blocks."""
    asyncio.create_task(
        _work(user_id, session_id, student_text, assistant_text, grade_level)
    )


async def _work(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    student_text: str,
    assistant_text: str,
    grade_level: str,
) -> None:
    from app.core.db import SessionLocal

    try:
        async with SessionLocal() as db:
            # Canonical shared evidence for a judged Learn check. This uses
            # the persisted lesson/chunk identity, never the free-form topic.
            try:
                from sqlalchemy import select
                from app.models.lesson_models import Lesson, LessonItem, TurnEvent
                from app.services.learning_service import record_external_evidence
                lesson = (await db.execute(select(Lesson).where(
                    Lesson.session_id == session_id, Lesson.user_id == user_id
                ).order_by(Lesson.updated_at.desc()))).scalars().first()
                if lesson:
                    event = (await db.execute(select(TurnEvent).where(
                        TurnEvent.lesson_id == lesson.id, TurnEvent.user_id == user_id,
                        TurnEvent.understood.is_not(None)
                    ).order_by(TurnEvent.created_at.desc(), TurnEvent.id.desc()))).scalars().first()
                    if event and event.understood is not None:
                        item = (await db.execute(select(LessonItem).where(
                            LessonItem.lesson_id == lesson.id, LessonItem.idx == lesson.chunk_index,
                            LessonItem.kind.in_(("hook", "chunk", "alt"))
                        ).order_by(LessonItem.created_at.desc()))).scalars().first()
                        chunk_id = uuid.uuid5(_EVIDENCE_NAMESPACE, f"learn:{lesson.id}:{lesson.chunk_index}")
                        await record_external_evidence(
                            db, user_id=user_id, source_type="learn_chunk", source_id=event.id,
                            skill_id=chunk_id, surface="chat_learn",
                            label=(item.title if item and item.title else lesson.topic),
                            response=student_text, judgment="correct" if event.understood else "incorrect",
                            purpose="independent" if event.model_move != "alt" else "practice",
                            independence="supported" if event.model_move == "alt" else "independent",
                            content_hash=str(item.id if item else lesson.id),
                        )
            except Exception as e:
                logger.warning("shared Learn evidence bridge failed: %s", e)

            # 1. Deadlines (has its own cheap keyword prefilter inside).
            try:
                from app.api.chat import _post_turn_tasks

                await _post_turn_tasks(
                    db, user_id, student_text + "\n" + assistant_text
                )
            except Exception as e:
                logger.warning("v2 deadline extract failed: %s", e)

            # 2. Honcho signal.
            try:
                from sqlalchemy import select

                from app.models.models import User
                from app.services.honcho_client import HonchoClient

                user = (
                    await db.execute(select(User).where(User.id == user_id))
                ).scalar_one_or_none()
                if user is not None:
                    await HonchoClient().add_message(
                        str(session_id), student_text, user.honcho_peer_id
                    )
            except Exception as e:
                logger.warning("v2 honcho signal failed: %s", e)

            # 3. Intelligence pipeline.
            try:
                from app.services.post_turn import run_post_turn_analysis

                await run_post_turn_analysis(
                    db, session_id, user_id, grade_level=grade_level
                )
            except Exception as e:
                logger.warning("v2 intelligence pipeline failed: %s", e)

            # Flush-only steps above roll back on close without this.
            try:
                await db.commit()
            except Exception as e:
                logger.warning("v2 post-turn commit failed: %s", e)
    except Exception as e:
        logger.error("v2 post-turn worker died: %s", e, exc_info=True)
