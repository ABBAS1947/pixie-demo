"""Add concurrency integrity for legacy lesson turns."""
from alembic import op
from sqlalchemy import text
revision = 'f8b0c1d2e3f4'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None

def upgrade():
    duplicate = op.get_bind().execute(text("""SELECT 1 FROM turn_events
      GROUP BY lesson_id,turn_no HAVING count(*)>1 LIMIT 1""")).first()
    if duplicate:
        raise RuntimeError('turn_events contains duplicate lesson/turn rows; review and reconcile before applying f8b0c1d2e3f4')
    op.create_unique_constraint('uq_turn_events_lesson_turn', 'turn_events', ['lesson_id', 'turn_no'])

def downgrade():
    op.drop_constraint('uq_turn_events_lesson_turn', 'turn_events', type_='unique')
