"""SQLAlchemy models for Study Partner.

Schema follows requirements v2 (raw/study-partner-requirements-v2.md):
every table carries user_id for isolation; notes.embedding is VECTOR(768)
matching our verified embeddinggemma dim.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    grade_level: Mapped[str | None] = mapped_column(Text)
    account_state: Mapped[str] = mapped_column(String(20), default="active", server_default="active", nullable=False)
    honcho_peer_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    vault_path: Mapped[str | None] = mapped_column(String(500))
    auth_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)  # Supabase user id
    is_teacher: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # teacher dashboard access
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # bypasses turn budget
    birth_year: Mapped[int | None] = mapped_column(Integer)  # age gate (self-reported, school-supervised pilot)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UTC")  # IANA name, student-local days
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")  # progression ledger
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persona: Mapped["UserPersona | None"] = relationship(back_populates="user", uselist=False)
    files: Mapped[list["File"]] = relationship("File", back_populates="user", cascade="all, delete-orphan")
    folders: Mapped[list["Folder"]] = relationship("Folder", back_populates="user", cascade="all, delete-orphan")


class TeacherStudentAssignment(Base):
    """Explicit authorization link for teacher access to a student's records."""

    __tablename__ = "teacher_student_assignments"

    id: Mapped[uuid.UUID] = uuid_pk()
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("teacher_id", "student_id", name="uq_teacher_student_assignment"),
        CheckConstraint("teacher_id <> student_id", name="ck_teacher_student_distinct"),
    )


class UserPersona(Base):
    __tablename__ = "user_persona"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    tone: Mapped[str | None] = mapped_column(String(50))  # playful_sarcastic | calm_steady | blunt
    resource_constraints: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="persona")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    subject: Mapped[str | None] = mapped_column(Text)
    honcho_session_id: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = user_fk()
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | pixie | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # markdown
    tags: Mapped[str | None] = mapped_column(Text)  # comma-separated
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    embedding: Mapped[list | None] = mapped_column(Vector(768))  # type: ignore[assignment]
    vault_path: Mapped[str | None] = mapped_column(String(500))  # mirror of vault file
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # vault is source of truth: one note per vault file, never two notes
        # claiming the same path (silent overwrite otherwise)
        UniqueConstraint("user_id", "vault_path", name="uq_notes_user_vault_path"),
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    term: Mapped[str | None] = mapped_column(String(100))


class Deadline(Base):
    __tablename__ = "deadlines"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(20))  # assignment | exam | project
    status: Mapped[str] = mapped_column(String(20), default="upcoming")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | file_upload | conversation | google_sync
    source_note_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("notes.id"))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    pace_plan: Mapped[str | None] = mapped_column(Text)
    # Google Calendar mirror (MASTER-CALENDAR)
    google_event_id: Mapped[str | None] = mapped_column(String(200))
    synced_to_google: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    google_last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("kind IN ('assignment','exam','project')", name="ck_deadlines_kind"),
        CheckConstraint(
            "source IN ('manual','file_upload','conversation','google_sync')",
            name="ck_deadlines_source",
        ),
    )


class QuickItem(Base):
    """A small, private dashboard reminder or checklist task."""

    __tablename__ = "quick_items"
    __table_args__ = (CheckConstraint("kind IN ('note','task')", name="ck_quick_items_kind"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class QuickNote(Base):
    """One private dashboard sticky note per user."""

    __tablename__ = "quick_notes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checklist: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GoogleCalendarToken(Base):
    """OAuth2 tokens for the user's Google Calendar connection (one per user)."""

    __tablename__ = "google_calendar_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calendar_id: Mapped[str] = mapped_column(String(100), default="primary")
    email: Mapped[str | None] = mapped_column(String(200))
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CalendarSyncLog(Base):
    """One row per sync attempt (pixie_to_google / google_to_pixie / full_sync)."""

    __tablename__ = "calendar_sync_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=text("gen_random_uuid()"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = user_fk()
    sync_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # pending | success | failed
    items_synced: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StudyPlan(Base):
    __tablename__ = "study_plans"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    deadline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deadlines.id"))
    plan_content: Mapped[str] = mapped_column(Text)  # LLM pace plan, markdown
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#2674AB", server_default="#2674AB")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="folders")


class File(Base):
    __tablename__ = "files"
    __table_args__ = (CheckConstraint("note_mode IN ('summary','full_text')", name="ck_files_note_mode"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="full_text", server_default="full_text")
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    needs_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(50))
    processed_note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    processing_cost: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship("User", back_populates="files")
    processed_note: Mapped[Note | None] = relationship("Note", foreign_keys=[processed_note_id])


# ConceptMastery, Flashcard, QuizAttempt — superseded by review_models.py
# (kept as comments for migration reference only)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    deadline_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("deadlines.id"))
    status: Mapped[str] = mapped_column(String(20), default="planning")


class UsageLog(Base):
    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = user_fk()
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # llm_tokens | file_storage
    amount: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)  # bug, feedback, feature
    message: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessingJob(Base):
    """Durable background job tracking for file uploads and other async work."""
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # file_processing, note_generation, etc.
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)  # file_id, note_id, etc.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, running, completed, failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
