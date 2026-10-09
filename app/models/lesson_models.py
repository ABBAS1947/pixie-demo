"""Lesson state tables — event-sourced teaching state in Postgres.

Replaces the in-memory LessonCache dict (lost on restart, wrong lesson on
multi-topic). Three tables:

- Lesson: the pointer (topic, phase, chunk index). One row per
  (user_id, topic_norm) so control words can never spawn fake lessons.
- LessonItem: content rows (hook, chunk, alt, quiz) with clothing tags.
- TurnEvent: evidence rows. One per turn: student signal, model move,
  latency, understood flag. Teachers read this table. Mastery reads it too.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.models import Base, user_fk, uuid_pk


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True, index=True
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    topic_norm: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    # Pinned meaning of the topic, set at hook time (e.g. "iron oxidation,
    # not the programming language"). Sent on every turn so ambiguous topics
    # can never drift mid-lesson.
    about: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    grade_level: Mapped[str | None] = mapped_column(String(20))
    # hook | build | probe | complete
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="hook")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "topic_norm", name="uq_lessons_user_topic"),
    )


class LessonItem(Base):
    __tablename__ = "lesson_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lessons.id"), nullable=False, index=True
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # hook | chunk | alt | quiz
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="chunk")
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # analogy_fun | analogy_rational | analogy_imag | plain
    clothing: Mapped[str | None] = mapped_column(String(30))
    check_question: Mapped[str | None] = mapped_column(Text)
    # words | analogy | logic | idea (alts only)
    failure_mode: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TurnEvent(Base):
    __tablename__ = "turn_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lessons.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = user_fk()
    turn_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # new_topic | advance | probe | question | off_topic
    student_signal: Mapped[str] = mapped_column(String(20), nullable=False)
    # hook | chunk | probe_question | alt | quiz | done
    model_move: Mapped[str | None] = mapped_column(String(20))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    understood: Mapped[bool | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_turn_events_user_created",
            "user_id",
            "created_at",
        ),
        UniqueConstraint("lesson_id", "turn_no", name="uq_turn_events_lesson_turn"),
    )
