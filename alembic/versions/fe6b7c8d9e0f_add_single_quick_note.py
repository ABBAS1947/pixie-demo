"""Store one sticky note per user and preserve existing quick items."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "fe6b7c8d9e0f"
down_revision = "fe5a6b7c8d9e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quick_notes",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("checklist", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.execute("""
        INSERT INTO quick_notes (user_id, body, checklist, updated_at)
        SELECT user_id,
               COALESCE(string_agg(content, E'\n\n' ORDER BY updated_at DESC, created_at DESC, id::text)
                        FILTER (WHERE kind = 'note'), ''),
               COALESCE(jsonb_agg(jsonb_build_object(
                   'id', id::text, 'text', content, 'checked', completed
               ) ORDER BY updated_at DESC, created_at DESC, id::text)
                        FILTER (WHERE kind = 'task'), '[]'::jsonb),
               COALESCE(max(updated_at), now())
        FROM quick_items
        GROUP BY user_id
    """)


def downgrade() -> None:
    raise RuntimeError("Quick notes contain user data and this migration is forward-only")
