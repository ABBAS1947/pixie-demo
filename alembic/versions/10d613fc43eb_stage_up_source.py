"""stage_up source

Revision ID: 10d613fc43eb
Revises: 4e1d8a4b7dbb
Create Date: 2026-09-12 16:15:19.033095

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10d613fc43eb'
down_revision: Union[str, Sequence[str], None] = '4e1d8a4b7dbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate cannot detect CHECK changes; hand-written.
    op.drop_constraint("ck_mastery_history_source", "mastery_history")
    op.create_check_constraint(
        "ck_mastery_history_source",
        "mastery_history",
        "source IN ('quiz_attempt','recheck','stage_up')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_mastery_history_source", "mastery_history")
    op.create_check_constraint(
        "ck_mastery_history_source",
        "mastery_history",
        "source IN ('quiz_attempt','recheck')",
    )
