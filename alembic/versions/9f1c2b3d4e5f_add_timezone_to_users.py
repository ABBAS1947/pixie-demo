"""add timezone to users (student-local streak days)

Revision ID: 9f1c2b3d4e5f
Revises: 787078d8a86d
Create Date: 2026-09-14
"""

import sqlalchemy as sa
from alembic import op

revision = "9f1c2b3d4e5f"
down_revision = "787078d8a86d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "timezone",
            sa.String(64),
            server_default="UTC",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "timezone")
