"""Recheck service — quick single-concept review sessions.

A recheck picks one short_answer flashcard for a concept and creates
a minimal quiz session with kind='recheck'. Used for rapid confidence
updates on specific concepts.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_models import (
    Concept,
    ConceptMastery,
    Flashcard,
    QuizItem,
    QuizSession,
)
from app.services.flashcard_generation import ensure_flashcard_coverage


async def start_recheck(
    session: AsyncSession,
    user_id: uuid.UUID,
    concept_id: uuid.UUID,
) -> QuizSession:
    """Create a single-item recheck session for a concept.

    Picks one short_answer flashcard (generates if needed) and wraps it
    in a QuizSession with kind='recheck'.
    """
    # Verify concept exists and belongs to user
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

    # Ensure flashcard coverage
    cards = await ensure_flashcard_coverage(session, user_id, concept)

    # Prefer short_answer card
    sa_cards = [c for c in cards if c.format == "short_answer"]
    if not sa_cards:
        # If no short_answer cards, use any card
        if not cards:
            raise ValueError("No flashcards available for this concept")
        card = cards[0]
    else:
        card = sa_cards[0]

    # Create quiz session
    quiz = QuizSession(
        id=uuid.uuid4(),
        user_id=user_id,
        course_id=concept.course_id,
        kind="recheck",
        composition={"concept_id": str(concept_id)},
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    session.add(quiz)
    await session.flush()

    # Create single quiz item
    item = QuizItem(
        id=uuid.uuid4(),
        quiz_session_id=quiz.id,
        flashcard_id=card.id,
        position=0,
    )
    session.add(item)
    await session.flush()

    return quiz
