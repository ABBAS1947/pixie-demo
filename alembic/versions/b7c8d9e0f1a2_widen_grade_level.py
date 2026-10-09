"""widen users.grade_level to 50 (grouped wizard values exceed 20)

Revision ID: b7c8d9e0f1a2
Revises: a2b3c4d5e6f7
Create Date: 2026-09-14
"""

import sqlalchemy as sa
from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "grade_level", existing_type=sa.String(20), type_=sa.String(50))


def downgrade() -> None:
    op.alter_column("users", "grade_level", existing_type=sa.String(50), type_=sa.String(20))
