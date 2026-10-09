"""Grading service — the single choke-point for confidence updates.

Every confidence mutation in the system flows through update_mastery().
This ensures consistency and auditability. MCQ grading is instant;
short_answer grading uses LLM evaluation.

Evaluation-integrity rules (shipped for the inclusion pilot):
- Blanks score zero. finalize() averages over ALL items, not just
  attempted ones. Skipping hard questions lowers the score.
- First attempt counts. Retries get feedback (practice) but only the
  earliest attempt per item moves the score and mastery. Answer farming
  is pointless.
- Mastery moves on attempted evidence only. A blank is absence of
  evidence, not evidence of ignorance, so it hits the quiz score but
  never the confidence model.
"""

import uuid
import math
import re as _re
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_models import (
    ConceptMastery,
    Flashcard,
    MasteryHistory,
    QuizAttempt,
    QuizItem,
    QuizSession,
)
from app.services.llm_client import llm_json
from app.models.models import User


def _norm(s: str) -> str:
    """Normalize for comparison: case, whitespace, and punctuation blind.

    A student who knows Paris should never fail for typing "paris.",
    "  Paris " or "PARIS". Factual strictness stays in the content, not
    the keystrokes.
    """
    s = s.strip().lower()
    s = _re.sub(r"\s+", " ", s)
    return s.rstrip(".!?")


async def _grade_mcq(
    flashcard: Flashcard,
    response: str,
) -> tuple[float, bool, str]:
    """Grade a multiple-choice response. Instant — no LLM needed.

    Returns (score, correct, feedback).
    """
    correct = _norm(response) == _norm(flashcard.answer)
    score = 1.0 if correct else 0.0
    feedback = "Correct!" if correct else f"The correct answer is: {flashcard.answer}"
    return score, correct, feedback


async def _grade_short_answer(
    flashcard: Flashcard,
    response: str,
) -> tuple[float, bool, str]:
    """Grade a short-answer response using LLM evaluation.

    Returns (score, correct, feedback).
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You grade student responses against a correct answer. "
                "Return a JSON object with:\n"
                "- 'score': float 0.0-1.0 (partial credit allowed)\n"
                "- 'correct': boolean (true if score >= 0.7)\n"
                "- 'feedback': 1-2 sentence explanation of what's right/wrong\n\n"
                "Be lenient on phrasing but strict on factual accuracy. "
                "Accept equivalent expressions and synonyms."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {flashcard.question}\n"
                f"Correct Answer: {flashcard.answer}\n"
                f"Student Response: {response}"
            ),
        },
    ]
    result = await llm_json(messages, max_tokens=256)
    score = float(result.get("score", 0.0))
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError("Invalid grading score")
    correct = result.get("correct", score >= 0.7)
    if type(correct) is not bool or correct != (score >= 0.7):
        raise ValueError("Inconsistent grading verdict")
    feedback = result.get("feedback", "")
    return score, correct, feedback


async def grade_attempt(
    session: AsyncSession,
    user_id: uuid.UUID,
    quiz_item_id: uuid.UUID,
    response: str,
) -> QuizAttempt:
    """Grade a user's response to a quiz item and record the attempt.

    MCQ is graded instantly; short_answer uses LLM grading.
    This does NOT update mastery — call update_mastery separately.
    """
    # Load quiz item
    quiz_item = (
        await session.execute(
            select(QuizItem).where(
                QuizItem.id == quiz_item_id,
            )
        )
    ).scalar_one_or_none()
    if quiz_item is None:
        raise ValueError(f"Quiz item {quiz_item_id} not found")

    # Lock the owning quiz through attempt persistence so finalization cannot
    # race with an in-flight grade or accept attempts after completion.
    owning_quiz = (await session.execute(select(QuizSession).where(
        QuizSession.id == quiz_item.quiz_session_id,
        QuizSession.user_id == user_id,
    ).with_for_update())).scalar_one_or_none()
    if owning_quiz is not None and owning_quiz.review_contract is not None:
        raise ValueError('Use the Review session action API for this quiz')
    if owning_quiz is None or owning_quiz.status != "active":
        raise ValueError("Quiz not active or access denied")

    # Quiz attempts are immutable. A network retry returns the saved verdict
    # instead of grading or persisting a second answer.
    existing = (await session.execute(select(QuizAttempt).where(
        QuizAttempt.quiz_item_id == quiz_item_id, QuizAttempt.user_id == user_id,
    ).order_by(QuizAttempt.attempted_at, QuizAttempt.id))).scalars().first()
    if existing is not None:
        if _norm(existing.response or '') != _norm(response):
            raise ValueError('This question has already been answered. Continue to the next question.')
        return existing

    # Load flashcard
    flashcard = (
        await session.execute(
            select(Flashcard).where(
                Flashcard.id == quiz_item.flashcard_id,
                Flashcard.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if flashcard is None:
        raise ValueError(f"Flashcard not found or access denied")

    # Grade based on format
    if flashcard.format == "mcq":
        score, correct, feedback = await _grade_mcq(flashcard, response)
    else:
        score, correct, feedback = await _grade_short_answer(flashcard, response)

    # Look up concept_id from flashcard
    concept_id = flashcard.concept_id

    # Determine source from quiz session kind
    quiz_session = (
        await session.execute(
            select(QuizSession).where(QuizSession.id == quiz_item.quiz_session_id)
        )
    ).scalar_one_or_none()
    source = "recheck" if (quiz_session and quiz_session.kind == "recheck") else "quiz_attempt"

    attempt = QuizAttempt(
        id=uuid.uuid4(),
        user_id=user_id,
        quiz_item_id=quiz_item_id,
        flashcard_id=flashcard.id,
        concept_id=flashcard.concept_id,
        response=response,
        score=score,
        correct=correct,
        feedback=feedback,
        attempted_at=datetime.now(timezone.utc),
    )
    session.add(attempt)
    await session.flush()
    await session.commit()
    return attempt


async def update_mastery(
    session: AsyncSession,
    user_id: uuid.UUID,
    concept_id: uuid.UUID,
    result: float,
    source: str,
    attempt_id: uuid.UUID | None = None,
) -> ConceptMastery:
    """Update concept mastery confidence using a shrinking K-factor.

    THIS IS THE ONLY FUNCTION THAT WRITES TO concept_mastery.confidence.

    K-factor shrinks as signal_count grows:
        K = max(0.1, 0.3 - 0.02 * signal_count)
    This means early signals move confidence a lot; later signals refine it.

    Args:
        session: Async DB session
        user_id: The user's ID
        concept_id: The concept to update
        result: The attempt score (0.0-1.0)
        source: 'quiz_attempt' or 'recheck'
        attempt_id: Optional reference to the QuizAttempt

    Returns:
        The updated ConceptMastery record.
    """
    # Load existing mastery
    mastery = (
        await session.execute(
            select(ConceptMastery).where(
                ConceptMastery.user_id == user_id,
                ConceptMastery.concept_id == concept_id,
            )
        )
    ).scalar_one_or_none()

    if mastery is None:
        # Create new mastery record
        mastery = ConceptMastery(
            id=uuid.uuid4(),
            user_id=user_id,
            concept_id=concept_id,
            confidence=0.5,
            signal_count=0,
            introduced_at=datetime.now(timezone.utc),
        )
        session.add(mastery)
        await session.flush()

    old_confidence = float(mastery.confidence) if mastery.confidence is not None else 0.5

    # Shrinking K-factor
    k = max(0.1, 0.3 - 0.02 * mastery.signal_count)

    # Update confidence
    new_confidence = old_confidence + k * (result - old_confidence)
    new_confidence = max(0.0, min(1.0, new_confidence))  # Clamp to [0, 1]

    # Record history BEFORE updating
    history = MasteryHistory(
        id=uuid.uuid4(),
        user_id=user_id,
        concept_id=concept_id,
        old_confidence=old_confidence,
        new_confidence=new_confidence,
        source=source,
        attempt_id=attempt_id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(history)

    # Update mastery
    mastery.confidence = new_confidence
    mastery.signal_count += 1
    mastery.last_reviewed_at = datetime.now(timezone.utc)
    mastery.last_signal_source = source

    # FSRS-lite scheduling. Correct (>= 0.7) extends the streak and doubles
    # the interval from a 3-day base (3/6/12/24, capped at 48d). Anything
    # else resets to tomorrow. Schedule lives here — the single choke-point —
    # so quiz and recheck paths schedule identically.
    now = datetime.now(timezone.utc)
    if result >= 0.7:
        mastery.streak = (mastery.streak or 0) + 1
        interval_days = min(3 * (2 ** (mastery.streak - 1)), 48)
    else:
        mastery.streak = 0
        interval_days = 1
    mastery.due_at = now + timedelta(days=interval_days)

    await session.flush()
    return mastery


async def finalize_quiz_score(
    session: AsyncSession,
    quiz_id: uuid.UUID,
    user_id: uuid.UUID,
) -> QuizSession:
    """Finalize a quiz by averaging attempt scores and updating mastery.

    Returns the completed QuizSession.
    """
    # Serialize completion and balance changes across all XP writers.
    from app.services.xp import lock_xp_user as _lock_xp_user

    _u = await _lock_xp_user(session, user_id)
    quiz = (
        await session.execute(
            select(QuizSession).where(
                QuizSession.id == quiz_id,
                QuizSession.user_id == user_id,
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if quiz is None:
        raise ValueError(f"Quiz {quiz_id} not found or access denied")
    if quiz.review_contract is not None:
        raise ValueError('Use the Review session action API for this quiz')

    # Idempotent completion: a finished quiz is a historical record.
    # Re-completing changes nothing — no score rewrite, no mastery replay.
    if quiz.status == "completed":
        return quiz

    # Get all quiz items for this session
    quiz_items = (
        await session.execute(
            select(QuizItem).where(QuizItem.quiz_session_id == quiz_id)
        )
    ).scalars().all()

    # Batch-fetch all attempts in one query (fixes N+1)
    item_ids = [item.id for item in quiz_items]
    attempts = (
        await session.execute(
            select(QuizAttempt).where(
                QuizAttempt.quiz_item_id.in_(item_ids),
                QuizAttempt.user_id == user_id,
            )
        )
    ).scalars().all()

    # Index the FIRST attempt per item (earliest wins). Retries are practice:
    # they get feedback but never move the score or mastery. Ordered by
    # attempted_at so farming an item wrong-then-right scores the wrong.
    ordered = sorted(attempts, key=lambda a: a.attempted_at or datetime.min.replace(tzinfo=timezone.utc))
    attempts_by_item: dict = {}
    for a in ordered:
        attempts_by_item.setdefault(a.quiz_item_id, a)

    total_score = 0.0

    for item in quiz_items:
        attempt = attempts_by_item.get(item.id)
        if attempt is not None:
            total_score += float(attempt.score)

            # Update mastery for each attempted concept
            cm = await update_mastery(
                session,
                user_id=user_id,
                concept_id=attempt.concept_id,
                result=float(attempt.score),
                source="recheck" if quiz.kind == "recheck" else "quiz_attempt",
                attempt_id=attempt.id,
            )
            # Graduation audit: a correct first attempt marks the stage
            # transition (MCQ -> written eligibility). Marker only — no
            # confidence change beyond what update_mastery already applied.
            if float(attempt.score) >= 0.7:
                session.add(MasteryHistory(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    concept_id=attempt.concept_id,
                    old_confidence=cm.confidence,
                    new_confidence=cm.confidence,
                    source="stage_up",
                    attempt_id=attempt.id,
                    created_at=datetime.now(timezone.utc),
                ))
                await session.flush()
            # Single shared evidence event; the reserved anchor is idempotent
            # and does not replace the learner-facing Review attempt.
            from app.services.learning_service import record_external_evidence
            from app.models.review_models import Concept as _Concept
            _concept = (await session.execute(select(_Concept).where(_Concept.id == attempt.concept_id))).scalar_one_or_none()
            if _concept is not None:
                await record_external_evidence(
                    session, user_id=user_id, source_type="review_concept",
                    source_id=attempt.id, surface="review", label=_concept.label,
                    response=attempt.response or "", judgment="correct" if float(attempt.score) >= 0.7 else "incorrect",
                    purpose="independent", independence="independent",
                    content_hash=str(attempt.flashcard_id), skill_id=attempt.concept_id,
                )
            # Mirror into the Learn mastery table so the transcript, profile
            # line, and teacher record show quiz-backed scores. Quiz-gated:
            # this mirror is the only path that raises Learn scores.
            try:
                from app.models.review_models import Concept
                from app.services.mastery_reconciliation import reconcile_quiz

                concept = (
                    await session.execute(
                        select(Concept).where(Concept.id == attempt.concept_id)
                    )
                ).scalar_one_or_none()
                await reconcile_quiz(session, user_id, attempt.concept_id,
                                     (concept.label if concept and concept.label else str(attempt.concept_id)),
                                     float(cm.confidence))
            except Exception as e:
                # Never break scoring on a mirror failure, but never hide it
                # either: a silent mirror means two mastery tables disagree.
                logger.warning("learn-mirror failed for %s: %s", attempt.concept_id, e)

    # Average over ALL items: blanks score zero. Skipping is never free.
    n_items = len(quiz_items)
    avg_score = total_score / n_items if n_items > 0 else 0.0

    # Update quiz session
    quiz.score = avg_score
    quiz.status = "completed"
    quiz.completed_at = datetime.now(timezone.utc)

    # XP for good grades — granted once, here on the first completion.
    # Replays return early at the top, so farming the same quiz pays nothing.
    from app.services.xp import quiz_xp_for as _quiz_xp
    _u.xp = (_u.xp or 0) + _quiz_xp(avg_score, n_items)

    await session.flush()
    await session.commit()
    return quiz
