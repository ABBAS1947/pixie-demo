"""review system — concepts, mastery, flashcards, quizzes

Revision ID: a1b2c3d4e5f6
Revises: f7a9c2e1d4b8
Create Date: 2026-08-16
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f7a9c2e1d4b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. concepts (new table) ───────────────────────────────────────────
    op.create_table(
        "concepts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "course_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id"),
            nullable=True,
        ),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "source_note_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ivfflat index on concepts.embedding — 10 lists is fine for small datasets
    op.execute(
        "CREATE INDEX ix_concepts_embedding ON concepts "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )

    # ── 2. concept_mastery — ALTER existing table ─────────────────────────
    # Add new columns
    op.add_column(
        "concept_mastery",
        sa.Column(
            "concept_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id"),
            nullable=True,  # temporarily nullable for data migration
            index=True,
        ),
    )
    op.add_column(
        "concept_mastery",
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # Drop the old concept (string) column and its unique constraint
    op.drop_constraint(
        "uq_concept_mastery_user_concept", "concept_mastery", type_="unique"
    )
    op.drop_column("concept_mastery", "concept")

    # Add new unique constraint on (user_id, concept_id)
    op.create_unique_constraint(
        "uq_concept_mastery_user_concept_v2",
        "concept_mastery",
        ["user_id", "concept_id"],
    )

    # ── 3. mastery_history (new table) ────────────────────────────────────
    op.create_table(
        "mastery_history",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "concept_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id"),
            nullable=False,
        ),
        sa.Column(
            "old_confidence", sa.Numeric(3, 2), nullable=False
        ),
        sa.Column(
            "new_confidence", sa.Numeric(3, 2), nullable=False
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "attempt_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source IN ('quiz_attempt','recheck')", name="ck_mastery_history_source"
        ),
    )
    op.create_index(
        "ix_mastery_history_user_concept_created",
        "mastery_history",
        ["user_id", "concept_id", "created_at"],
    )

    # ── 4. flashcards — ALTER existing table ──────────────────────────────
    op.add_column(
        "flashcards",
        sa.Column(
            "concept_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id"),
            nullable=True,  # temporarily nullable
            index=True,
        ),
    )
    op.add_column(
        "flashcards",
        sa.Column(
            "format",
            sa.Text(),
            nullable=False,
            server_default="short_answer",
        ),
    )
    op.add_column(
        "flashcards",
        sa.Column("options", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "flashcards",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_check_constraint(
        "ck_flashcards_format",
        "flashcards",
        "format IN ('mcq','short_answer')",
    )
    op.create_index(
        "ix_flashcards_user_concept",
        "flashcards",
        ["user_id", "concept_id"],
    )

    # ── 5. quiz_sessions (new table) ──────────────────────────────────────
    op.create_table(
        "quiz_sessions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "course_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id"),
            nullable=True,
        ),
        sa.Column("kind", sa.Text(), nullable=False, server_default="quiz"),
        sa.Column("composition", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("score", sa.Numeric(4, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('quiz','recheck')", name="ck_quiz_sessions_kind"
        ),
        sa.CheckConstraint(
            "status IN ('active','completed')", name="ck_quiz_sessions_status"
        ),
    )

    # ── 6. quiz_items (new table) ─────────────────────────────────────────
    op.create_table(
        "quiz_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "quiz_session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quiz_sessions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "flashcard_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flashcards.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )

    # ── 7. quiz_attempts — ALTER existing table ───────────────────────────
    op.add_column(
        "quiz_attempts",
        sa.Column(
            "quiz_item_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quiz_items.id"),
            nullable=True,  # temporarily nullable
        ),
    )
    op.add_column(
        "quiz_attempts",
        sa.Column(
            "concept_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id"),
            nullable=True,  # temporarily nullable
        ),
    )
    op.add_column(
        "quiz_attempts",
        sa.Column("response", sa.Text(), nullable=True),
    )
    op.add_column(
        "quiz_attempts",
        sa.Column("score", sa.Numeric(3, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "quiz_attempts",
        sa.Column("feedback", sa.Text(), nullable=True),
    )
    op.add_column(
        "quiz_attempts",
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default="quiz_attempt",
        ),
    )
    op.create_check_constraint(
        "ck_quiz_attempts_source_v2",
        "quiz_attempts",
        "source IN ('quiz_attempt','recheck')",
    )


def downgrade() -> None:
    # ── 7. quiz_attempts — revert ALTERs ──────────────────────────────────
    op.drop_constraint("ck_quiz_attempts_source_v2", "quiz_attempts", type_="check")
    op.drop_column("quiz_attempts", "source")
    op.drop_column("quiz_attempts", "feedback")
    op.drop_column("quiz_attempts", "score")
    op.drop_column("quiz_attempts", "response")
    op.drop_column("quiz_attempts", "concept_id")
    op.drop_column("quiz_attempts", "quiz_item_id")

    # ── 6. quiz_items ─────────────────────────────────────────────────────
    op.drop_table("quiz_items")

    # ── 5. quiz_sessions ──────────────────────────────────────────────────
    op.drop_table("quiz_sessions")

    # ── 4. flashcards — revert ALTERs ─────────────────────────────────────
    op.drop_index("ix_flashcards_user_concept", table_name="flashcards")
    op.drop_constraint("ck_flashcards_format", "flashcards", type_="check")
    op.drop_column("flashcards", "created_at")
    op.drop_column("flashcards", "options")
    op.drop_column("flashcards", "format")
    op.drop_column("flashcards", "concept_id")

    # ── 3. mastery_history ────────────────────────────────────────────────
    op.drop_index("ix_mastery_history_user_concept_created", table_name="mastery_history")
    op.drop_table("mastery_history")

    # ── 2. concept_mastery — revert ALTERs ────────────────────────────────
    op.drop_constraint(
        "uq_concept_mastery_user_concept_v2", "concept_mastery", type_="unique"
    )
    op.add_column(
        "concept_mastery",
        sa.Column("concept", sa.String(500), nullable=False),
    )
    op.drop_column("concept_mastery", "signal_count")
    op.drop_column("concept_mastery", "concept_id")
    op.create_unique_constraint(
        "uq_concept_mastery_user_concept",
        "concept_mastery",
        ["user_id", "concept"],
    )

    # ── 1. concepts ───────────────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS ix_concepts_embedding")
    op.drop_table("concepts")
