"""Conversation Intelligence models — Phase 5.

ConversationInsight: per-session extracted insights (topics, mood, difficulty).
StudentProfile: aggregated per-user learning profile, updated after each insight.
StudentFact: discrete facts extracted from conversations (preferences, confusions, etc.).
ConversationMessage: archived messages with embeddings for semantic search.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.models import Base, user_fk


class ConversationInsight(Base):
    """Extracted insight from a single chat session."""

    __tablename__ = "conversation_insights"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = user_fk()

    # Extracted data (JSON columns)
    topics: Mapped[list] = mapped_column(JSON, default=list)
    subjects: Mapped[list] = mapped_column(JSON, default=list)
    concepts_covered: Mapped[list] = mapped_column(JSON, default=list)
    difficulty_signals: Mapped[list] = mapped_column(JSON, default=list)
    tools_used: Mapped[list] = mapped_column(JSON, default=list)
    questions_asked: Mapped[int] = mapped_column(Integer, default=0)
    concepts_explained: Mapped[int] = mapped_column(Integer, default=0)
    mood: Mapped[str] = mapped_column(Text, default="neutral")
    summary: Mapped[str] = mapped_column(Text, default="")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StudentProfile(Base):
    """Aggregated student learning profile — one row per user."""

    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )

    # Academic profile
    grade_level: Mapped[str] = mapped_column(String(50), default="")
    subjects: Mapped[list] = mapped_column(JSON, default=list)
    weak_topics: Mapped[list] = mapped_column(JSON, default=list)
    strong_topics: Mapped[list] = mapped_column(JSON, default=list)

    # Learning patterns
    learning_style: Mapped[str] = mapped_column(Text, default="")
    session_frequency: Mapped[float] = mapped_column(Float, default=0.0)
    avg_session_length: Mapped[float] = mapped_column(Float, default=0.0)
    retention_score: Mapped[float] = mapped_column(Float, default=0.5)

    # Engagement metrics
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    total_notes_created: Mapped[int] = mapped_column(Integer, default=0)
    total_quizzes_taken: Mapped[int] = mapped_column(Integer, default=0)
    avg_quiz_score: Mapped[float] = mapped_column(Float, default=0.0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)

    # Behavioral
    preferred_tone: Mapped[str] = mapped_column(Text, default="friendly")
    common_confusions: Mapped[list] = mapped_column(JSON, default=list)
    avg_response_length: Mapped[float] = mapped_column(Float, default=0.0)

    # Metadata
    last_active: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_insight_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StudentFact(Base):
    """Discrete fact extracted from conversations — preferences, confusions, strengths, etc."""

    __tablename__ = "student_facts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    fact_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # preference, confusion, strength, weakness, pattern, milestone, context
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="general"
    )  # Biology, learning_style, behavior, general
    content: Mapped[str] = mapped_column(Text, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    mention_count: Mapped[int] = mapped_column(Integer, default=1)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConversationMessage(Base):
    """Archived conversation message with embedding for semantic search."""

    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(768), nullable=True)  # type: ignore[assignment]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
