"""Align concept_mastery.introduced_at with its SQLAlchemy model default.

The ConceptMastery model declares
    introduced_at: ... server_default=func.now()
but the live column was created WITHOUT that default (migration drift). The
model's server_default has no effect on a column that lacks it, so any insert
path that relies on the DB default (e.g. the unique-constraint probe in
test_critical.py, direct ORM inserts) hits a NOT NULL violation. Add the
real column default so schema matches the model.

Revision ID: 0a1b2c3d4e5f
Revises: 6b98032179c7
Create Date: 2026-09-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0a1b2c3d4e5f"
down_revision = "6b98032179c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "concept_mastery",
        "introduced_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "concept_mastery",
        "introduced_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )