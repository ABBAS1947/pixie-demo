"""merge_heads

Revision ID: cb1e193e230a
Revises: a1b2c3d4e5f6, c1d2e3f4a5b6
Create Date: 2026-08-21 00:02:39.498048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb1e193e230a'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'c1d2e3f4a5b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
