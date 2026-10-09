"""Add file metadata (title, description, subject) and folders table.

Revision ID: c1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "c1d2e3f4a5b6"
down_revision = "b0dfd8023352"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Folders table
    op.create_table(
        "folders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # File metadata columns
    op.add_column("files", sa.Column("title", sa.String(500), nullable=True))
    op.add_column("files", sa.Column("description", sa.Text, nullable=True))
    op.add_column("files", sa.Column("subject", sa.String(255), nullable=True))
    op.add_column("files", sa.Column("folder_id", UUID(as_uuid=True), sa.ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True))


def downgrade() -> None:
    op.drop_column("files", "folder_id")
    op.drop_column("files", "subject")
    op.drop_column("files", "description")
    op.drop_column("files", "title")
    op.drop_table("folders")
