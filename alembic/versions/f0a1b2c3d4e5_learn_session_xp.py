"""Award one XP once for each completed Learn lesson.

Revision ID: f0a1b2c3d4e5
Revises: fc3d4e5f6a7b
"""
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "fc3d4e5f6a7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE lesson_xp_events (
            lesson_id uuid PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            amount integer NOT NULL CHECK (amount = 1),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (lesson_id, user_id)
        )
    """)
    op.execute("CREATE INDEX lesson_xp_events_owner ON lesson_xp_events(user_id, created_at DESC)")


def downgrade() -> None:
    raise RuntimeError(
        "Learn XP receipts cannot be discarded by downgrade. "
        "Restore a verified backup or roll forward."
    )
