"""add updated_at to notes (last-edited sort for the notebook)

Revision ID: f7a9c2e1d4b8
Revises: de538e4fdaa1
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a9c2e1d4b8"
down_revision = "de538e4fdaa1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notes",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("notes", "updated_at")
