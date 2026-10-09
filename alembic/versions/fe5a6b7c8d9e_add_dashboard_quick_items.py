"""Add private dashboard quick notes and tasks."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "fe5a6b7c8d9e"
down_revision = "fd4e5f6a7b8c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quick_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("content", sa.String(length=500), nullable=False),
        sa.Column("completed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint("kind IN ('note','task')", name="ck_quick_items_kind"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quick_items_user_id"), "quick_items", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_quick_items_user_id"), table_name="quick_items")
    op.drop_table("quick_items")
