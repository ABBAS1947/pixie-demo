"""Read-only reporting services for concept mastery and course summaries.

All functions are pure queries — they never write to the database.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_models import (
    Concept,
    ConceptMastery,
    Flashcard,
    MasteryHistory,
    QuizAttempt,
)


async def concept_report(
    session: AsyncSession,
    user_id: uuid.UUID,
    concept_id: uuid.UUID,
) -> dict:
    """Generate a detailed report for a single concept.

    Returns:
        {
            "concept": {id, label, course_id, source_note_id},
            "mastery": {confidence, signal_count, introduced_at, last_reviewed_at, last_signal_source},
            "history": [{old_confidence, new_confidence, source, created_at}, ...],
            "recent_feedback": [{feedback, score, correct, attempted_at}, ...],
        }
    """
    # Load concept
    concept = (
        await session.execute(
            select(Concept).where(
                Concept.id == concept_id,
                Concept.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if concept is None:
        raise ValueError(f"Concept {concept_id} not found or access denied")

    # Load mastery
    mastery = (
        await session.execute(
            select(ConceptMastery).where(
                ConceptMastery.user_id == user_id,
                ConceptMastery.concept_id == concept_id,
            )
        )
    ).scalar_one_or_none()

    # Load history (last 20 entries)
    history = (
        await session.execute(
            select(MasteryHistory)
            .where(
                MasteryHistory.user_id == user_id,
                MasteryHistory.concept_id == concept_id,
            )
            .order_by(MasteryHistory.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    # Load recent feedback (last 5 attempts)
    recent_feedback = (
        await session.execute(
            select(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.concept_id == concept_id,
            )
            .order_by(QuizAttempt.attempted_at.desc())
            .limit(5)
        )
    ).scalars().all()

    return {
        "concept": {
            "id": str(concept.id),
            "label": concept.label,
            "course_id": str(concept.course_id) if concept.course_id else None,
            "source_note_id": str(concept.source_note_id) if concept.source_note_id else None,
        },
        "mastery": {
            "confidence": float(mastery.confidence) if mastery else 0.5,
            "signal_count": mastery.signal_count if mastery else 0,
            "streak": mastery.streak if mastery else 0,
            "due_at": mastery.due_at.isoformat() if mastery and mastery.due_at else None,
            "introduced_at": mastery.introduced_at.isoformat() if mastery and mastery.introduced_at else None,
            "last_reviewed_at": mastery.last_reviewed_at.isoformat() if mastery and mastery.last_reviewed_at else None,
            "last_signal_source": mastery.last_signal_source if mastery else None,
        },
        "history": [
            {
                "old_confidence": float(h.old_confidence),
                "new_confidence": float(h.new_confidence),
                "source": h.source,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in history
        ],
        "recent_feedback": [
            {
                "feedback": a.feedback,
                "score": float(a.score),
                "correct": a.correct,
                "attempted_at": a.attempted_at.isoformat() if a.attempted_at else None,
            }
            for a in recent_feedback
        ],
    }


async def course_mastery_summary(
    session: AsyncSession,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> dict:
    """Generate a summary of mastery for all concepts in a course.

    Returns:
        {
            "avg_confidence": float,
            "stale_count": int,      # concepts not reviewed in 7+ days
            "weak_count": int,       # concepts with confidence < 0.5
            "total_concepts": int,
            "concepts": [{id, label, confidence, last_reviewed_at}, ...],
        }
    """
    # Get all concepts in the course
    concepts = (
        await session.execute(
            select(Concept).where(
                Concept.user_id == user_id,
                Concept.course_id == course_id,
            )
        )
    ).scalars().all()

    if not concepts:
        return {
            "avg_confidence": 0.0,
            "stale_count": 0,
            "weak_count": 0,
            "total_concepts": 0,
            "concepts": [],
        }

    concept_ids = [c.id for c in concepts]

    # Get mastery records for all concepts
    mastery_records = (
        await session.execute(
            select(ConceptMastery).where(
                ConceptMastery.user_id == user_id,
                ConceptMastery.concept_id.in_(concept_ids),
            )
        )
    ).scalars().all()

    # Build concept_id -> mastery map
    mastery_map = {m.concept_id: m for m in mastery_records}

    now = datetime.now(timezone.utc)
    stale_threshold_days = 7

    total_confidence = 0.0
    stale_count = 0
    weak_count = 0
    concepts_with_mastery = []

    for concept in concepts:
        mastery = mastery_map.get(concept.id)
        confidence = float(mastery.confidence) if mastery and mastery.confidence is not None else 0.5
        total_confidence += confidence

        if confidence < 0.5:
            weak_count += 1

        if mastery and mastery.last_reviewed_at:
            days_since = (now - mastery.last_reviewed_at).days
            if days_since >= stale_threshold_days:
                stale_count += 1
        else:
            # Never reviewed = stale
            stale_count += 1

        concepts_with_mastery.append({
            "id": str(concept.id),
            "label": concept.label,
            "confidence": confidence,
            "last_reviewed_at": (
                mastery.last_reviewed_at.isoformat() if mastery and mastery.last_reviewed_at else None
            ),
        })

    avg_confidence = total_confidence / len(concepts) if concepts else 0.0

    return {
        "avg_confidence": round(avg_confidence, 2),
        "stale_count": stale_count,
        "weak_count": weak_count,
        "total_concepts": len(concepts),
        "concepts": concepts_with_mastery,
    }
