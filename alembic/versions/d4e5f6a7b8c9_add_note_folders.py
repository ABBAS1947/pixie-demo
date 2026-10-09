"""Add folders dedicated to notes.

Revision ID: d4e5f6a7b8c9
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "d4e5f6a7b8c9"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_folders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", name="uq_note_folders_user_name"),
    )
    op.create_index("ix_note_folders_user_id", "note_folders", ["user_id"])
    op.add_column("notes", sa.Column("folder_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_notes_folder_id", "notes", ["folder_id"])
    op.create_foreign_key("fk_notes_folder_id", "notes", "note_folders", ["folder_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_notes_folder_id", "notes", type_="foreignkey")
    op.drop_index("ix_notes_folder_id", table_name="notes")
    op.drop_column("notes", "folder_id")
    op.drop_index("ix_note_folders_user_id", table_name="note_folders")
    op.drop_table("note_folders")
