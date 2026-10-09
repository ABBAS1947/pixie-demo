"""Review system SQLAlchemy models.

Full-featured review tables (concepts, flashcards, quizzes, mastery tracking).
Concepts are extracted from notes via LLM, deduplicated by embedding similarity,
and used to generate flashcards and quizzes. Confidence is updated only through
the grading service (single choke-point design).

Shares table names with simpler models in models.py; uses extend_existing=True
so both mappings resolve to the same schema. The migration file handles the
schema evolution from the v1 columns to these v2 columns.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.models import Base, user_fk, uuid_pk


class Concept(Base):
    """A discrete learning concept extracted from a note via LLM."""

    __tablename__ = "concepts"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(768), nullable=False)  # type: ignore[assignment]
    source_note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConceptMastery(Base):
    """Per-user, per-concept mastery tracker — one row per concept per user.

    The confidence field is ONLY written by the grading service's update_mastery
    function. This is the single choke-point for all confidence mutations.
    """

    __tablename__ = "concept_mastery"
    __table_args__ = (
        CheckConstraint(
            "last_signal_source IN ('quiz_attempt','recheck')",
            name="ck_concept_mastery_source",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_concept_mastery_conf",
        ),
        UniqueConstraint("user_id", "concept_id", name="uq_concept_mastery_user_concept"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("concepts.id"), nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), default=0.5, nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # FSRS-lite scheduling: consecutive correct answers (streak) double the
    # interval (3d, 6d, 12d, 24d, cap 48d); any wrong resets to tomorrow.
    streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    introduced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_signal_source: Mapped[str | None] = mapped_column(Text)


class MasteryHistory(Base):
    """Immutable log of every confidence change for audit and trend analysis."""

    __tablename__ = "mastery_history"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("concepts.id"), nullable=False
    )
    old_confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    new_confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("source IN ('quiz_attempt','recheck','stage_up')", name="ck_mastery_history_source"),
        Index("ix_mastery_history_user_concept_created", "user_id", "concept_id", "created_at"),
    )


class Flashcard(Base):
    """A flashcard tied to a concept. Supports MCQ and short_answer formats."""

    __tablename__ = "flashcards"
    __table_args__ = (
        CheckConstraint(
            "format IN ('mcq','short_answer','true_false','reveal_card')", name="ck_flashcards_format"
        ),
        Index("ix_flashcards_user_concept", "user_id", "concept_id"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("concepts.id"), nullable=False
    )
    note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id"), nullable=True
    )
    format: Mapped[str] = mapped_column(Text, nullable=False, default="short_answer")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    review_content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuizSession(Base):
    """A quiz or recheck session containing ordered quiz items."""

    __tablename__ = "quiz_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, default="quiz"
    )
    composition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active"
    )
    score: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_contract: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    abandon_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("kind IN ('quiz','recheck')", name="ck_quiz_sessions_kind"),
        CheckConstraint(
            "status IN ('preparing','prepared','active','paused','completed','abandoned','failed')", name="ck_quiz_sessions_status"
        ),
    )


class QuizItem(Base):
    """A single item within a quiz session, linking to a flashcard."""

    __tablename__ = "quiz_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    quiz_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_sessions.id"), nullable=False, index=True
    )
    flashcard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flashcards.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Difficulty stage at ask time (Quizlet Learn staging): first exposure
    # is always "mcq"; concepts graduate to "written" after demonstrated
    # recall. Audit trail for the efficacy story.
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="mcq")
    review_content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    review_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default='{}')


class QuizAttempt(Base):
    """A user's attempt at a quiz item. Includes LLM-graded feedback."""

    __tablename__ = "quiz_attempts"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    quiz_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_items.id"), nullable=False
    )
    flashcard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flashcards.id"), nullable=False
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("concepts.id"), nullable=False
    )
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
