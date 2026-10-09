"""Mastery + learner profile tables (Chunk 4, BKT-lite).

Mastery: one row per (user, concept). Concept key is
"<topic_norm>::<idx>" so a chunk is the unit of knowledge. p_known moves
with counted evidence, clamped 0..1. No training, no black box.

LearnerProfile: one row per user. Counters only: clothing wins, failure
mode counts, advances, probes, escalations. Preferred clothing and top
failure mode are derived by majority vote, never guessed by an LLM.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.models import Base, user_fk, uuid_pk


class Mastery(Base):
    __tablename__ = "mastery"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    concept_key: Mapped[str] = mapped_column(String(600), nullable=False, index=True)
    concept_label: Mapped[str] = mapped_column(String(300), nullable=False)
    p_known: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "concept_key", name="uq_mastery_user_concept"),
    )


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    clothing_wins: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    failure_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    advances: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    probes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    escalations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
