"""Review system API â€” quiz creation, attempts, rechecks, and reporting.

All endpoints resolve the user from JWT via get_current_user. No endpoint
trusts a client-supplied user_id.
"""

import uuid
import random as _random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.utils import safe_uuid, require_uuid
from app.core.db import get_db
from app.models.models import Note, User
from app.models.review_models import (
    Concept,
    ConceptMastery,
    Flashcard,
    QuizItem,
    QuizSession,
    QuizAttempt,
)
from app.services.grading import finalize_quiz_score, grade_attempt
from app.services.quiz_assembly import assemble_quiz
from app.services.concept_extraction import ensure_concepts_for_note
from app.services.cost_firewall import check_creation_budget
from app.services.recheck import start_recheck
from app.services.reporting import concept_report, course_mastery_summary

router = APIRouter(prefix="/review", tags=["review"])


# â”€â”€ Pydantic Request/Response Models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class CreateQuizRequest(BaseModel):
    course_id: Optional[str] = Field(None, description="Optional course filter")
    note_id: Optional[uuid.UUID] = None
    size: int = Field(10, ge=1, le=50, description="Number of quiz items")


class QuizSessionResponse(BaseModel):
    id: str
    user_id: str
    course_id: Optional[str]
    kind: str
    status: str
    score: Optional[float]
    created_at: Optional[str]
    completed_at: Optional[str]
    items: list["QuizItemResponse"] = []
    attempts: dict[str, dict] = Field(default_factory=dict)


class QuizItemResponse(BaseModel):
    id: str
    flashcard_id: str
    position: int
    stage: str = "mcq"
    question: Optional[str] = None
    format: Optional[str] = None
    options: Optional[list] = None


class AttemptRequest(BaseModel):
    response: str = Field(..., description="The user's answer")

class AttemptResponse(BaseModel):
    id: str
    score: float
    correct: bool
    feedback: Optional[str]


class ConceptResponse(BaseModel):
    id: str
    label: str
    course_id: Optional[str]
    source_note_id: Optional[str]
    created_at: Optional[str]


class ConceptMasteryResponse(BaseModel):
    confidence: float
    signal_count: int
    introduced_at: Optional[str]
    last_reviewed_at: Optional[str]
    last_signal_source: Optional[str]


class ConceptReportResponse(BaseModel):
    concept: dict
    mastery: dict
    history: list[dict]
    recent_feedback: list[dict]


class CourseSummaryResponse(BaseModel):
    avg_confidence: float
    stale_count: int
    weak_count: int
    total_concepts: int
    concepts: list[dict]


# â”€â”€ Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.post("/quizzes", response_model=QuizSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_quiz(
    request: CreateQuizRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new quiz session with priority-scored concept selection.

    Concepts are lazily extracted from all user notes if not already present.
    Flashcards are generated on demand. The quiz picks the highest-priority
    concepts based on staleness and low confidence.
    """
    # Creation budget: building burns generation calls with zero answers.
    if not await check_creation_budget(db, user):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Quiz building limit reached for today (20/day). Answer your review queue instead.",
        )
    course_id = safe_uuid(request.course_id)
    if request.note_id is not None:
        note = (await db.execute(select(Note.id).where(Note.id == request.note_id, Note.user_id == user.id))).scalar_one_or_none()
        if note is None: raise HTTPException(404, 'Study note not found')
    try:
        quiz = await assemble_quiz(db, user.id, course_id=course_id, size=request.size, note_id=request.note_id)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(422, str(exc)) from exc

    # Load items with flashcard details
    items = (
        await db.execute(
            select(QuizItem, Flashcard)
            .join(Flashcard, QuizItem.flashcard_id == Flashcard.id)
            .where(QuizItem.quiz_session_id == quiz.id)
            .order_by(QuizItem.position)
        )
    ).all()

    return QuizSessionResponse(
        id=str(quiz.id),
        user_id=str(quiz.user_id),
        course_id=str(quiz.course_id) if quiz.course_id else None,
        kind=quiz.kind,
        status=quiz.status,
        score=float(quiz.score) if quiz.score is not None else None,
        created_at=quiz.created_at.isoformat() if quiz.created_at else None,
        completed_at=quiz.completed_at.isoformat() if quiz.completed_at else None,
        items=[
            QuizItemResponse(
                id=str(item.id),
                flashcard_id=str(item.flashcard_id),
                position=item.position,
                question=card.question,
                format=card.format,
                options=card.options,
                stage=item.stage or card.format,
            )
            for item, card in items
        ],
    )


@router.get("/quizzes/{quiz_id}", response_model=QuizSessionResponse)
async def get_quiz(
    quiz_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a quiz session with all its items and flashcard details."""
    quiz_uuid = require_uuid(quiz_id, "quiz_id")
    quiz = (
        await db.execute(
            select(QuizSession).where(
                QuizSession.id == quiz_uuid,
                QuizSession.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")

    items = (
        await db.execute(
            select(QuizItem, Flashcard)
            .join(Flashcard, QuizItem.flashcard_id == Flashcard.id)
            .where(QuizItem.quiz_session_id == quiz.id)
            .order_by(QuizItem.position)
        )
    ).all()

    attempt_rows = (await db.execute(select(QuizAttempt).where(
        QuizAttempt.user_id == user.id,
        QuizAttempt.quiz_item_id.in_([item.id for item, _ in items]),
    ).order_by(QuizAttempt.attempted_at, QuizAttempt.id))).scalars().all()
    attempts = {}
    for a in attempt_rows:
        attempts.setdefault(str(a.quiz_item_id), {'id':str(a.id), 'score':float(a.score),
            'correct':a.correct, 'feedback':a.feedback, 'response':a.response})
    return QuizSessionResponse(
        id=str(quiz.id),
        attempts=attempts,
        user_id=str(quiz.user_id),
        course_id=str(quiz.course_id) if quiz.course_id else None,
        kind=quiz.kind,
        status=quiz.status,
        score=float(quiz.score) if quiz.score is not None else None,
        created_at=quiz.created_at.isoformat() if quiz.created_at else None,
        completed_at=quiz.completed_at.isoformat() if quiz.completed_at else None,
        items=[
            QuizItemResponse(
                id=str(item.id),
                flashcard_id=str(item.flashcard_id),
                position=item.position,
                question=card.question,
                format=card.format,
                options=card.options,
                stage=item.stage or card.format,
            )
            for item, card in items
        ],
    )


@router.post(
    "/quizzes/{quiz_id}/items/{item_id}/attempt",
    response_model=AttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_attempt(
    quiz_id: str,
    item_id: str,
    request: AttemptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a response for a quiz item. Grades instantly (MCQ) or via LLM (short_answer).

    Mastery is NOT updated here â€” call /complete to finalize.
    """
    # Verify quiz belongs to user and is active
    quiz_uuid = require_uuid(quiz_id, "quiz_id")
    quiz = (
        await db.execute(
            select(QuizSession).where(
                QuizSession.id == quiz_uuid,
                QuizSession.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    if quiz.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quiz is not active")

    # Verify item belongs to this quiz
    item_uuid = require_uuid(item_id, "item_id")
    quiz_item = (
        await db.execute(
            select(QuizItem).where(
                QuizItem.id == item_uuid,
                QuizItem.quiz_session_id == quiz.id,
            )
        )
    ).scalar_one_or_none()
    if quiz_item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz item not found in this quiz")

    try:
        attempt = await grade_attempt(db, user.id, item_uuid, request.response)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except HTTPException:
        raise
    except Exception as e:
        # Grading depends on a live provider call (short answers). After the
        # shared client's retries, a residual failure is a service problem,
        # not a student problem: 503 (retryable), never a 500, and nothing
        # is recorded so the student can simply retry the same item.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Grading temporarily unavailable, please retry this item: {type(e).__name__}",
        )

    return AttemptResponse(
        id=str(attempt.id),
        score=float(attempt.score),
        correct=attempt.correct,
        feedback=attempt.feedback,
    )


@router.post("/quizzes/{quiz_id}/complete", response_model=QuizSessionResponse)
async def complete_quiz(
    quiz_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Finalize a quiz â€” averages scores and updates mastery for all concepts.

    This is where confidence values are actually written to the database.
    """
    quiz_uuid = require_uuid(quiz_id, "quiz_id")
    try:
        quiz = await finalize_quiz_score(db, quiz_uuid, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))

    # Reload with items
    items = (
        await db.execute(
            select(QuizItem, Flashcard)
            .join(Flashcard, QuizItem.flashcard_id == Flashcard.id)
            .where(QuizItem.quiz_session_id == quiz.id)
            .order_by(QuizItem.position)
        )
    ).all()

    return QuizSessionResponse(
        id=str(quiz.id),
        user_id=str(quiz.user_id),
        course_id=str(quiz.course_id) if quiz.course_id else None,
        kind=quiz.kind,
        status=quiz.status,
        score=float(quiz.score) if quiz.score is not None else None,
        created_at=quiz.created_at.isoformat() if quiz.created_at else None,
        completed_at=quiz.completed_at.isoformat() if quiz.completed_at else None,
        items=[
            QuizItemResponse(
                id=str(item.id),
                flashcard_id=str(item.flashcard_id),
                position=item.position,
                question=card.question,
                format=card.format,
                options=card.options,
                stage=item.stage or card.format,
            )
            for item, card in items
        ],
    )


@router.get("/concepts", response_model=list[ConceptResponse])
async def list_concepts(
    course_id: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all concepts for the user, optionally filtered by course."""
    query = select(Concept).where(Concept.user_id == user.id)
    if course_id:
        query = query.where(Concept.course_id == safe_uuid(course_id))
    query = query.order_by(Concept.created_at.desc())

    concepts = (await db.execute(query)).scalars().all()
    return [
        ConceptResponse(
            id=str(c.id),
            label=c.label,
            course_id=str(c.course_id) if c.course_id else None,
            source_note_id=str(c.source_note_id) if c.source_note_id else None,
            created_at=c.created_at.isoformat() if c.created_at else None,
        )
        for c in concepts
    ]


@router.get("/concepts/{concept_id}/report", response_model=ConceptReportResponse)
async def get_concept_report(
    concept_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a detailed mastery report for a single concept."""
    try:
        report = await concept_report(db, user.id, require_uuid(concept_id, "concept_id"))
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return ConceptReportResponse(**report)


@router.post(
    "/concepts/{concept_id}/recheck",
    response_model=QuizSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_recheck(
    concept_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a single-item recheck session for a specific concept.

    Creates a minimal quiz with kind='recheck' containing one short_answer card.
    """
    try:
        quiz = await start_recheck(db, user.id, require_uuid(concept_id, "concept_id"))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    # Load item details
    items = (
        await db.execute(
            select(QuizItem, Flashcard)
            .join(Flashcard, QuizItem.flashcard_id == Flashcard.id)
            .where(QuizItem.quiz_session_id == quiz.id)
            .order_by(QuizItem.position)
        )
    ).all()

    return QuizSessionResponse(
        id=str(quiz.id),
        user_id=str(quiz.user_id),
        course_id=str(quiz.course_id) if quiz.course_id else None,
        kind=quiz.kind,
        status=quiz.status,
        score=float(quiz.score) if quiz.score is not None else None,
        created_at=quiz.created_at.isoformat() if quiz.created_at else None,
        completed_at=quiz.completed_at.isoformat() if quiz.completed_at else None,
        items=[
            QuizItemResponse(
                id=str(item.id),
                flashcard_id=str(item.flashcard_id),
                position=item.position,
                question=card.question,
                format=card.format,
                options=card.options,
                stage=item.stage or card.format,
            )
            for item, card in items
        ],
    )


@router.get(
    "/courses/{course_id}/summary",
    response_model=CourseSummaryResponse,
)
async def get_course_summary(
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a mastery summary for all concepts in a course."""
    try:
        summary = await course_mastery_summary(db, user.id, require_uuid(course_id, "course_id"))
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return CourseSummaryResponse(**summary)


class QuizletImportRequest(BaseModel):
    tsv: str = Field(..., description="Quizlet export: 'term\\tdefinition' per card, blank line between cards")
    title: str = Field(default="Imported set", max_length=500)


class QuizletImportResponse(BaseModel):
    notes: int
    concepts: int
    cards: int
    skipped: int


@router.post("/imports/quizlet", response_model=QuizletImportResponse, status_code=status.HTTP_201_CREATED)
async def import_quizlet_set(
    request: QuizletImportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a Quizlet study set pasted as TSV. Deterministic: card text
    comes from the TSV, never the LLM (one concept-extraction call only).
    MCQ distractors are sibling definitions, shuffled. Re-imports skip
    existing terms instead of doubling cards.

    Paste path in Quizlet: set -> â‹¯ -> Export -> copy text.
    """
    if not await check_creation_budget(db, user):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Quiz building limit reached for today (20/day). Answer your review queue instead.",
        )

    rows: list[tuple[str, str]] = []
    for block in request.tsv.split("\n\n"):
        block = block.strip()
        if not block or "\t" not in block:
            continue
        term, definition = block.split("\t", 1)
        term, definition = term.strip(), definition.strip()
        if term and definition:
            rows.append((term, definition))
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No term\\tdefinition rows found")
    if len(rows) > 500:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Set too large (max 500 rows)")

    # Concept extraction samples the head of the set: sending a 100-term
    # TSV to the LLM overflows max_tokens and returns truncated JSON (500).
    # Concepts are cluster labels â€” 15 rows sample the set faithfully.
    # Cards still cover every row; the note keeps the full text.
    sample = "\n\n".join(f"{t}\t{d}" for t, d in rows[:15])
    note = Note(
        user_id=user.id,
        title=request.title,
        content=f"{request.title}\n{sample}",
        tags="import,quizlet",
    )
    db.add(note)
    await db.flush()

    concepts = await ensure_concepts_for_note(db, user.id, note)
    if not concepts:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Concept extraction returned nothing")
    note.content = request.tsv[:20000]
    await db.flush()

    def _best_concept(term: str):
        words = {w.strip("?.,!").lower() for w in term.split() if len(w) > 2}
        best, best_hit = concepts[0], -1
        for c in concepts:
            label = (c.label or "").lower()
            hit = sum(1 for w in words if w in label)
            if hit > best_hit:
                best, best_hit = c, hit
        return best

    existing_qs = set(
        (await db.execute(
            select(Flashcard).where(Flashcard.user_id == user.id)
        )).scalars().all()
    )
    existing_norm = {card.question.strip().lower() for card in existing_qs if card.question}
    defs = [d for _, d in rows]

    cards = skipped = 0
    for term, definition in rows:
        # Dedup key is the deterministic short-answer question text: the
        # same TSV re-imported generates byte-identical questions, so an
        # exact match means "already imported". No false positives.
        expected_q = f"What does '{term}' mean?"
        if expected_q.strip().lower() in existing_norm:
            skipped += 1
            continue
        concept = _best_concept(term)
        # Short-answer card: exact term -> definition.
        db.add(Flashcard(
            id=uuid.uuid4(),
            user_id=user.id,
            concept_id=concept.id,
            note_id=note.id,
            format="short_answer",
            question=f"What does '{term}' mean?",
            answer=definition,
        ))
        cards += 1
        # MCQ card when distractors exist: correct + up to 3 siblings.
        others = [d for d in defs if d != definition]
        if others:
            options = [definition] + others[:3]
            _random.shuffle(options)
            db.add(Flashcard(
                id=uuid.uuid4(),
                user_id=user.id,
                concept_id=concept.id,
                note_id=note.id,
                format="mcq",
                question=f"Which definition matches '{term}'?",
                answer=definition,
                options=options,
            ))
            cards += 1
        existing_norm.add(expected_q.strip().lower())

    await db.commit()
    return QuizletImportResponse(
        notes=1, concepts=len(concepts), cards=cards, skipped=skipped,
    )
