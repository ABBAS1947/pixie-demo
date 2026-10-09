"""Quiz assembly with priority-scored concept selection.

Assembles a quiz by:
1. Ensuring concepts exist for all user notes (lazy extraction)
2. Ranking concepts by priority (staleness + low confidence)
3. Selecting flashcards: short_answer for weakest concepts, MCQ for rest
4. Capping short_answer at 3 per quiz
"""

import uuid
import time
import logging
logger = logging.getLogger("uvicorn.error.pixie.review")
import string as _string
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Note
from app.models.lesson_models import Lesson
from app.models.review_models import (
    Concept,
    ConceptMastery,
    Flashcard,
    QuizItem,
    QuizSession,
)
from app.services.concept_extraction import ensure_concepts_for_note
from app.services.flashcard_generation import ensure_flashcard_coverage
from app.services.ollama_client import embed_text


def _norm_label(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


async def ensure_lesson_concepts(
    session: AsyncSession,
    user_id: uuid.UUID,
    course_id: uuid.UUID | None = None,
    max_new: int = 3,
) -> int:
    """Derive quiz-able concepts from lesson topics missing concept cover.

    Lessons teach; notes don't always exist. For each lesson topic with no
    matching concept, create Concept (label = topic, no source note) plus a
    fresh ConceptMastery row, then flashcard coverage generates cards.
    Dedup is normalized-label containment either way. Capped so one quiz
    build never fans out into an LLM storm. Returns concepts created.
    """
    lessons = (
        await session.execute(
            select(Lesson).where(Lesson.user_id == user_id)
        )
    ).scalars().all()
    if not lessons:
        return 0
    existing = (
        await session.execute(
            select(Concept).where(Concept.user_id == user_id)
        )
    ).scalars().all()
    have = {_norm_label(c.label) for c in existing}
    created = 0
    for topic in dict.fromkeys(lesson.topic for lesson in lessons):  # de-dup, keep order
        if created >= max_new or _topic_covered(topic, have):
            continue
        concept = Concept(
            id=uuid.uuid4(),
            user_id=user_id,
            course_id=course_id,
            label=topic.strip(),
            embedding=await embed_text(topic[:1000]),
            source_note_id=None,
            created_at=datetime.now(timezone.utc),
        )
        session.add(concept)
        await session.flush()
        session.add(ConceptMastery(
            id=uuid.uuid4(),
            user_id=user_id,
            concept_id=concept.id,
            confidence=0.5,
            signal_count=0,
            introduced_at=datetime.now(timezone.utc),
        ))
        await ensure_flashcard_coverage(session, user_id, concept)
        have.add(_norm_label(topic))
        created += 1
    await session.flush()
    return created

def _topic_covered(topic: str, have: set[str]) -> bool:
    # Token-overlap dedup (not substring containment: "cell" must not
    # swallow "cellular respiration"). Covered when normalized equal,
    # when a single token matches exactly, or when >= 60% of the
    # shorter side's tokens overlap (and it has 2+ tokens, so
    # "chapter 1" never swallows "chapter 2").
    t = _norm_label(topic)
    if not t:
        return True
    def _toks(s: str) -> list[str]:
        return [w.strip(_string.punctuation) for w in s.split() if w.strip(_string.punctuation)]
    _NUM_WORDS = {
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
        "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5",
    }
    def _numbers(tokens: list[str]) -> set[str]:
        out = set()
        for w in tokens:
            if w.isdigit():
                out.add(w.lstrip("0") or "0")
            elif w in _NUM_WORDS:
                out.add(_NUM_WORDS[w])
        return out
    for h in have:
        if not h:
            continue
        if t == h:
            return True
        tw, hw = _toks(t), _toks(h)
        # Numbered parts are distinct topics even when all other words
        # match: "type 1" vs "type 2", "chapter 1" vs "chapter 2".
        nt, nh = _numbers(tw), _numbers(hw)
        if nt and nh and nt != nh:
            continue
        if len(tw) == 1 and tw[0] in hw:
            return True
        if len(hw) == 1 and hw[0] in tw:
            return True
        short, long = (tw, hw) if len(tw) <= len(hw) else (hw, tw)
        if len(short) >= 2:
            hit = sum(1 for w in short if w in long) / len(short)
            if hit >= 0.6:
                return True
    return False


def priority_score(mastery: ConceptMastery) -> float:
    """Compute a review priority score for a concept.

    Higher = more urgent to review. Base formula:
        0.5 * staleness_norm + 0.5 * (1 - confidence)

    staleness_norm is 1.0 if never reviewed, decays with recency.

    Due-date adjustment (FSRS-lite): a concept not yet due sinks (-0.3)
    so fresh wins don't crowd out real work; an overdue concept rises
    (+0.2). Unscheduled concepts (due_at None) are untouched.
    """
    confidence = float(mastery.confidence) if mastery.confidence is not None else 0.5

    if mastery.last_reviewed_at is None:
        staleness_norm = 1.0  # Never reviewed — maximum priority
    else:
        days_since = (datetime.now(timezone.utc) - mastery.last_reviewed_at).days
        # Full staleness at 14+ days, linear decay
        staleness_norm = min(days_since / 14.0, 1.0)

    score = 0.5 * staleness_norm + 0.5 * (1.0 - confidence)

    due = getattr(mastery, "due_at", None)
    if due is not None:
        now = datetime.now(timezone.utc)
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due > now:
            score -= 0.3
        else:
            score += 0.2
    return score


async def assemble_quiz(
    session: AsyncSession,
    user_id: uuid.UUID,
    course_id: uuid.UUID | None = None,
    size: int = 10,
    note_id: uuid.UUID | None = None,
) -> QuizSession:
    """Create a quiz session with the highest-priority concepts.

    Steps:
    1. Ensure concepts exist for all user notes (lazy extraction)
    2. Get mastery records for all concepts, filtered by course if specified
    3. Rank by priority_score, pick top N
    4. For weakest concepts (bottom 30% by confidence): short_answer cards
    5. For the rest: MCQ cards
    6. Cap short_answer at 3 per quiz
    """
    preparation_started = time.perf_counter()
    # Step 1: scope extraction to the material selected by the learner.
    notes = (
        await session.execute(
            select(Note).where(Note.user_id == user_id, Note.id == note_id) if note_id is not None else select(Note).where(Note.user_id == user_id)
        )
    ).scalars().all()

    # AsyncSession cannot be shared across concurrent tasks. All database
    # extraction/dedup mutations stay sequential in this transaction.
    for note in notes:
        await ensure_concepts_for_note(session, user_id, note)
    extraction_seconds = time.perf_counter() - preparation_started
    # Raw chat titles are not assessment constructs. Chat evidence is mapped
    # through the shared learning contract, never fabricated from greetings.

    # Step 2: Get mastery records
    mastery_query = (
        select(ConceptMastery, Concept)
        .join(Concept, ConceptMastery.concept_id == Concept.id)
        .where(ConceptMastery.user_id == user_id)
    )
    if course_id is not None:
        mastery_query = mastery_query.where(Concept.course_id == course_id)

    mastery_query = mastery_query.where(Concept.source_note_id == note_id) if note_id is not None else mastery_query.where(Concept.source_note_id.is_not(None))
    mastery_results = (await session.execute(mastery_query)).all()
    if not mastery_results:
        raise ValueError('No testable concepts were found in these notes. Choose another note or add study content.')

    # Step 3: Rank by priority
    scored = [(priority_score(m), m, c) for m, c in mastery_results]
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[:size]

    # Step 4-5: Assign flashcard formats, weakest concepts first.
    # Weakest-first is deliberate-difficulty pedagogy: the exam attacks
    # what the student knows least, not what the scheduler listed first.
    # Within a concept, rotate to the least-recently-asked card so a quiz
    # can never be passed by memorizing three fixed answers.
    by_confidence = sorted(selected, key=lambda x: float(x[1].confidence or 0.5))

    # Recency rank: flashcard_id -> how recently asked (lower = longer ago).
    # Anything never asked ranks -1 and wins every tie.
    recent_cards = (
        await session.execute(
            select(QuizItem.flashcard_id)
            .join(QuizSession, QuizItem.quiz_session_id == QuizSession.id)
            .where(QuizSession.user_id == user_id)
            .order_by(QuizSession.created_at.desc())
            .limit(300)
        )
    ).scalars().all()
    recency: dict = {}
    for rank, fid in enumerate(reversed(recent_cards)):
        recency.setdefault(fid, rank)

    def _pick(cards: list, want: str, used: set) -> object:
        pool = [c for c in cards if c.format == want] or list(cards)
        # Least-recently-asked first; within this quiz, unused cards first
        # so one quiz never asks the same card twice.
        pool.sort(key=lambda c: (c.id in used, recency.get(c.id, -1)))
        pick = pool[0]
        used.add(pick.id)
        return pick

    short_answer_count = 0
    max_short_answer = min(3, len(selected))
    used: set = set()

    quiz_items: list[QuizItem] = []
    ordered_concept_ids: list[str] = []

    for idx, (score_val, mastery, concept) in enumerate(by_confidence):
        # Ensure flashcard coverage
        cards = await ensure_flashcard_coverage(session, user_id, concept)
        if not cards:
            continue

        # Weakest concepts earn short_answer (open response, LLM graded);
        # the rest get MCQ. Capped so no quiz is all-essay.
        # Staging rule (Quizlet Learn): written must be EARNED by evidence,
        # not exposure. A concept stays MCQ until its confidence reaches
        # 0.6 (one clean correct from the 0.5 start lands at 0.65; a wrong
        # lands at 0.35). Slips demote automatically: confidence below 0.6
        # drops back to MCQ. Failing students never face harder formats.
        conf = float(mastery.confidence) if mastery.confidence is not None else 0.5
        earned = (mastery.signal_count or 0) > 0 and conf >= 0.6
        if not earned:
            mcq = [c for c in cards if c.format == "mcq"]
            card = _pick(mcq, "mcq", used) if mcq else _pick(cards, "short_answer", used)
        elif short_answer_count < max_short_answer:
            card = _pick(cards, "short_answer", used)
            short_answer_count += 1
        else:
            # Prefer MCQ, but never silently collapse: if the concept has
            # no MCQ card at all, say so in the composition record.
            mcq = [c for c in cards if c.format == "mcq"]
            card = _pick(mcq, "mcq", used) if mcq else _pick(cards, "short_answer", used)

        quiz_items.append(
            QuizItem(
                id=uuid.uuid4(),
                quiz_session_id=uuid.uuid4(),  # Will be set below
                flashcard_id=card.id,
                position=idx,
            )
        )
        quiz_items[-1]._format = card.format  # transient, for composition only
        quiz_items[-1].stage = "written" if card.format == "short_answer" else "mcq"
        ordered_concept_ids.append(str(mastery.concept_id))

    if not quiz_items:
        raise ValueError("No questions are available for this material yet. Choose another note.")
    # Create quiz session
    quiz = QuizSession(
        id=uuid.uuid4(),
        user_id=user_id,
        course_id=course_id,
        kind="quiz",
        composition={
            "concept_ids": ordered_concept_ids,
            "size": len(quiz_items),
            "formats": [getattr(it, "_format", None) for it in quiz_items],
        },
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    session.add(quiz)
    await session.flush()

    # Link quiz items to session
    for item in quiz_items:
        item.quiz_session_id = quiz.id
        session.add(item)

    await session.flush()
    await session.commit()
    logger.info("quiz_preparation items=%d extraction_seconds=%.3f total_seconds=%.3f", len(quiz_items), extraction_seconds, time.perf_counter()-preparation_started)
    return quiz
