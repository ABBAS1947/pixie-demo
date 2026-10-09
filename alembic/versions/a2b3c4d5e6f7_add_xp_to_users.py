"""add xp ledger to users (ranks progression)

Revision ID: a2b3c4d5e6f7
Revises: 9f1c2b3d4e5f
Create Date: 2026-09-14
"""

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "9f1c2b3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "xp",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "xp")
